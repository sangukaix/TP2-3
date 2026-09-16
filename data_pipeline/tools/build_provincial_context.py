"""Local immutable province ZIP snapshot -> CSV -> optional MySQL context only.

Never registers provinces as planning regions or changes district facts/models.
Run from repository root with --apply to import the validated bundle.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .import_mysql_bundle import _connect, _execute_schema, mysql_config_from_env

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'data/source_snapshots/provincial_tourism_20260916'
OUTPUT = ROOT / 'data/processed/provincial_tourism'
REFERENCE = ROOT / 'data/processed/nationwide/materialized_region_reference/official_municipality_codes.csv'
FIELDS = ['province_code', 'province_name', 'year_month', 'metric_name', 'metric_value', 'unit',
          'source_id', 'source_file', 'source_member', 'source_sha256', 'source_row_number']
# Exact names only: nationwide-average and cumulative (연인원) files are not interchangeable.
TABLES = {
    ('숙박_체류시간', '순 방문자 수 및 숙박 비율.csv'): [
        ('visitors', '순 방문자수', '명', 1), ('lodging_rate_pct', '숙박자 비율', '%', 1)],
    ('숙박_체류시간', '평균 숙박일.csv'): [('lodging_nights', '평균 숙박일수', '일', 1)],
    ('관광소비', '관광소비 추이_외지인.csv'): [('spending_krw', '소비액(천원)', '원', 1000)],
}


def decoded_name(name: str) -> str:
    try:
        return name.encode('cp437').decode('cp949')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def province_codes() -> dict[str, str]:
    with REFERENCE.open(encoding='utf-8-sig', newline='') as stream:
        result = {r['province_name']: r['region_code'][:2] for r in csv.DictReader(stream)}
    # Autonomous city has no municipality row in this official municipality reference.
    # Standard administrative province code, kept out of the district planning catalog.
    result['세종특별자치시'] = '36'
    return result


def build(snapshot: Path = SNAPSHOT, output: Path = OUTPUT) -> dict:
    manifest = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
    codes = province_codes()
    values: dict[tuple, dict] = {}
    skipped = set()
    for entry in manifest['files']:
        rel = Path(entry['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Invalid snapshot member path')
        data = (snapshot / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'Snapshot hash mismatch: {rel}')
        province = rel.parts[0]
        if province not in codes:
            skipped.add(province)
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                name = decoded_name(member.filename).strip()
                specs = TABLES.get((rel.parts[1], name))
                if not specs:
                    continue
                raw = archive.read(member)
                try:
                    body = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    body = raw.decode('cp949')
                source_id = 'province:' + hashlib.sha256((entry['path'] + entry['sha256'] + name).encode()).hexdigest()[:24]
                for index, row in enumerate(csv.DictReader(io.StringIO(body)), 2):
                    if '업종대분류명' in row and row['업종대분류명'].strip() != '전체':
                        continue
                    month = row['기준연월'].strip()
                    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])', month):
                        raise ValueError(f'Invalid month: {rel} {month}')
                    for metric, column, unit, factor in specs:
                        value = Decimal(row[column].replace(',', '').strip()) * factor
                        if not value.is_finite() or value < 0 or (unit == '%' and value > 100):
                            raise ValueError(f'Invalid value: {rel} {column}')
                        key = (codes[province], month, metric)
                        if key in values and Decimal(values[key]['metric_value']) != value:
                            raise ValueError(f'Conflicting province observation: {key}')
                        values.setdefault(key, dict(zip(FIELDS, [codes[province], province, month, metric,
                            format(value, 'f'), unit, source_id, rel.as_posix(), name, entry['sha256'], index])))
    rows = [values[key] for key in sorted(values)]
    if not rows:
        raise ValueError('No province observations found')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'monthly_context.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {'row_count': len(rows), 'snapshot_zip_count': manifest['file_count'],
        'province_count': len({r['province_code'] for r in rows}),
        'period_start': min(r['year_month'] for r in rows), 'period_end': max(r['year_month'] for r in rows),
        'metrics': sorted({r['metric_name'] for r in rows}), 'excluded_folder_names': sorted(skipped),
        'source_url': 'https://datalab.visitkorea.or.kr/',
        'use': '상위 시도 관측 맥락만 사용. 시군구 생성 대상/ML/수치 fact를 변경하지 않음',
        'provinces': {name: sum(r['province_name'] == name for r in rows) for name in sorted({r['province_name'] for r in rows})}}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def import_mysql(output: Path = OUTPUT) -> int:
    with (output / 'monthly_context.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    with _connect(mysql_config_from_env()) as connection:
        with connection.cursor() as cursor:
            _execute_schema(cursor, ROOT / 'database/mysql/005_provincial_tourism_context.sql')
            columns = ','.join(f'`{field}`' for field in FIELDS)
            updates = ','.join(f'`{field}`=VALUES(`{field}`)' for field in FIELDS if field not in {'province_code', 'year_month', 'metric_name'})
            cursor.executemany(f'INSERT INTO provincial_tourism_monthly_context ({columns}) '
                f'VALUES ({",".join(["%s"] * len(FIELDS))}) ON DUPLICATE KEY UPDATE {updates}',
                [tuple(r[field] for field in FIELDS) for r in rows])
        connection.commit()
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    summary = build()
    if args.apply:
        summary['mysql_rows_written'] = import_mysql()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
