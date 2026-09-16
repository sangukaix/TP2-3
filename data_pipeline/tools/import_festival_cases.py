"""Materialize team festival CSVs without changing monthly facts or ML models.

python -m data_pipeline.tools.import_festival_cases --source <local folder> --apply
Subsequent imports use the permanent local snapshot; no network share is needed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from .import_mysql_bundle import _connect, mysql_config_from_env
from ai_server.app.case_scope import PROVINCE_ALIASES, _location_parts

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/source_snapshots/festivals_20260820'
OUTPUT = ROOT / 'data/processed/festival_cases'
URL = 'https://datalab.visitkorea.or.kr/'
VERSION = 'festival-csv-v1'
TYPES = {'annual': '연도별 방문자 추이', 'indicators': '문화관광축제 주요 지표',
         'audience': '성_연령별 내국인 방문자', 'destinations': '목적지 검색순위'}


def read_csv(path):
    return list(csv.DictReader(path.read_text(encoding='utf-8-sig').splitlines()))


def number(value):
    if value in (None, '', 'N/A'):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid nonnegative festival observation')
    return value


def changes(before, after):
    result = {'before_year': before['year'], 'after_year': after['year'],
              'before_days': before['days'], 'after_days': after['days']}
    for key in ('total', 'outside', 'daily', 'outside_daily'):
        old, new = before[key], after[key]
        result[key] = {'before': old, 'after': new, 'difference': new-old,
                       'change_pct': (new/old-1)*100 if old else None}
    return result


def materialize(source: Path = RAW, output: Path = OUTPUT):
    if not source.is_dir() or not any(source.rglob('*.csv')):
        raise ValueError('Local festival source CSVs are missing; existing catalog is unchanged')
    RAW.mkdir(parents=True, exist_ok=True)
    # Copy only downloaded data/image assets, preserving bytes and refusing overwrite.
    for path in source.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in ('.csv', '.png'):
            continue
        dest = RAW / path.relative_to(source)
        data = path.read_bytes()
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError(f'Immutable raw snapshot conflict: {dest.name}')
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    reference = read_csv(ROOT / 'data/processed/nationwide/materialized_region_reference/official_municipality_codes.csv')
    regions = {}
    for row in reference:
        regions[_location_parts(row['official_full_name'])] = row
    registry, sources = [], []
    normalized = {k: [] for k in TYPES}
    for folder in sorted(p for p in RAW.iterdir() if p.is_dir()):
        tables, table_sources = {}, {}
        for kind, suffix in TYPES.items():
            paths = list(folder.glob('*_'+suffix+'.csv'))
            if len(paths) > 1:
                raise ValueError(f'Ambiguous table: {folder.name}/{kind}')
            if not paths:
                continue
            path = paths[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            sid = 'festival-file:'+digest[:20]
            tables[kind] = read_csv(path)
            table_sources[kind] = {'source_id': sid, 'file_name': path.name, 'sha256': digest,
                                   'relative_path': path.relative_to(ROOT).as_posix(), 'source_url': URL,
                                   'downloaded_at': '2026-08-20', 'provider': '한국관광 데이터랩',
                                   'provenance_status': 'team_download_exact_query_url_unrecorded'}
            sources.append(table_sources[kind])
        name = next((r['축제명'] for kind in ('annual', 'indicators') for r in tables.get(kind, []) if r.get('축제명')), None)
        if not name:
            raise ValueError('Festival name missing')
        fid = 'case:festival:'+hashlib.sha256(name.encode()).hexdigest()[:14]
        # Full province + municipality, never a bare ambiguous 시/군/구 name.
        addresses = Counter(_location_parts(' '.join(r['도로명주소'].split()[:2]))
                            for r in tables.get('destinations', []) if r.get('도로명주소'))
        dominant = addresses.most_common(1)
        address = dominant[0][0] if dominant else None
        region = regions.get(address) if address else None
        region_basis = '목적지 검색 CSV의 시도+시군구 최빈 주소; 행사장 행정경계 확정은 아님'
        if name == '세종축제':
            region = next((r for r in reference if r['region_code'] == '36110'), None)
            region_basis = '축제명에 명시된 세종특별자치시와 공식 지역코드 대조'
        annual = []
        for row in tables.get('annual', []):
            values = {'year': int(row['개최년도']), 'days': int(row['축체기간(일)']),
                      'total': number(row['(전체)방문자수']), 'local': number(row['(현지인)방문자수']),
                      'outside': number(row['(외지인)방문자수']), 'foreign': number(row['(외국인)방문자수'])}
            if values['days'] <= 0 or any(values[k] is None for k in ('total','local','outside','foreign')):
                raise ValueError(f'Incomplete annual observation: {name}')
            if abs(sum(values[k] for k in ('local','outside','foreign'))-values['total']) > 1:
                raise ValueError(f'Visitor total mismatch: {name}')
            values['daily'] = values['total']/values['days']
            values['outside_daily'] = values['outside']/values['days']
            values['outside_share_pct'] = values['outside']/values['total']*100 if values['total'] else None
            if abs(values['daily']-number(row['일평균 방문자수'])) > .001:
                raise ValueError(f'Daily count mismatch: {name}')
            annual.append(values)
        annual.sort(key=lambda r:r['year'])
        if len({r['year'] for r in annual}) != len(annual):
            raise ValueError(f'Duplicate annual observation: {name}')
        comparisons = [changes(a,b) for a,b in zip(annual,annual[1:]) if b['year']==a['year']+1]
        for kind, rows in tables.items():
            for row in rows:
                normalized[kind].append({'festival_id':fid,'region_code':region['region_code'] if region else '',
                                         'source_id':table_sources[kind]['source_id'],**row})
        registry.append({'festival_id':fid,'name':name,'region_code':region['region_code'] if region else None,
                         'region_name':region['official_full_name'] if region else '', 'region_basis':region_basis,
                         'address_coverage': dominant[0][1]/sum(addresses.values()) if dominant else None,
                         'annual':annual,'comparisons':comparisons,'sources':table_sources,
                         'audience':tables.get('audience',[]), 'indicators':tables.get('indicators',[]),
                         'destinations':tables.get('destinations',[]),
                         'eligible':bool(annual and region),
                         'scope':'축제 관측구역 방문 지표. 도시 전체·순증 관광객·입장권 실구매자 수가 아님.'})
    output.mkdir(parents=True, exist_ok=True)
    def write_csv(name, rows):
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with (output/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    for kind, rows in normalized.items():
        write_csv(kind+'.csv',rows)
    write_csv('sources.csv', sources)
    payload={'version':VERSION,'festivals':registry}
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode('utf-8')
    (output/'catalog.json').write_bytes(encoded)
    summary={'version':VERSION,'dataset_hash':hashlib.sha256(encoded).hexdigest(),
             'festival_count':len(registry),'eligible_count':sum(r['eligible'] for r in registry),
             'source_count':len(sources),'rows':{k:len(v) for k,v in normalized.items()},
             'unresolved':[r['name'] for r in registry if not r['eligible']]}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload,summary


def import_mysql(payload, summary):
    with _connect(mysql_config_from_env()) as connection:
        with connection.cursor() as cursor:
            schema=(ROOT/'database/mysql/004_festival_cases.sql').read_text(encoding='utf-8')
            cursor.execute(schema)
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.executemany('''INSERT INTO festival_case_catalog
                    (dataset_hash,festival_id,region_code,festival_name,payload_json)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json)''',
                    [(summary['dataset_hash'],r['festival_id'],r['region_code'],r['name'],
                      json.dumps(r,ensure_ascii=False)) for r in payload['festivals']])
                cursor.execute('SELECT COUNT(*) FROM festival_case_catalog WHERE dataset_hash=%s',(summary['dataset_hash'],))
                result=cursor.fetchone()
                count=next(iter(result.values())) if isinstance(result,dict) else result[0]
                if count!=len(payload['festivals']):
                    raise ValueError('MySQL row count mismatch')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return count


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=RAW)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    payload,summary=materialize(args.source)
    if args.apply:
        summary['mysql_rows']=import_mysql(payload,summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
