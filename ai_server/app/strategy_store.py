"""MySQL에 생성 기획안과 출력 문서를 영구 보관하는 저장소 계층입니다.

브라우저 localStorage는 개인 PC에만 남기 때문에, 팀이 함께 보는 기획안 기록에는
사용하지 않습니다. 이 모듈은 MySQL에는 기획안 JSON과 파일 경로를, 로컬 서버에는
Word·PowerPoint 파일을 저장합니다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_DIRECTORY = PROJECT_ROOT / 'storage' / 'strategy_documents'


def _connect():
    """.env의 MySQL 전용 계정으로 연결합니다. 비밀번호는 로그에 남기지 않습니다."""
    try:
        import pymysql
    except ModuleNotFoundError as exc:
        raise RuntimeError('PyMySQL이 설치되지 않았습니다. requirements.txt를 설치해 주세요.') from exc

    password = os.getenv('MYSQL_PASSWORD', '').strip()
    if not password:
        raise RuntimeError('MYSQL_PASSWORD가 설정되지 않았습니다.')
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', '127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'tourism_app'),
        password=password,
        database=os.getenv('MYSQL_DATABASE', 'tourism_strategy'),
        charset='utf8mb4',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def initialize_strategy_store() -> None:
    """서버 시작 시 필요한 테이블과 로컬 문서 폴더를 한 번 준비합니다."""
    DOCUMENT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    report_sql = '''
        CREATE TABLE IF NOT EXISTS strategy_reports (
            report_id VARCHAR(64) PRIMARY KEY,
            region_code VARCHAR(20) NOT NULL,
            region_name VARCHAR(120) NOT NULL,
            title VARCHAR(300) NOT NULL,
            summary TEXT NOT NULL,
            report_json JSON NOT NULL,
            word_path VARCHAR(500) NULL,
            ppt_path VARCHAR(500) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_strategy_reports_created_at (created_at),
            INDEX idx_strategy_reports_region_code (region_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    '''
    job_sql = '''
        CREATE TABLE IF NOT EXISTS strategy_report_jobs (
            job_id VARCHAR(64) PRIMARY KEY,
            region_code VARCHAR(20) NOT NULL,
            region_name VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL,
            message VARCHAR(500) NOT NULL,
            error TEXT NOT NULL,
            request_json JSON NULL,
            had_transient_references BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_strategy_jobs_status (status),
            INDEX idx_strategy_jobs_updated_at (updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    '''
    # 기획안의 목표와 실제 관측값을 섞지 않기 위한 최소 측정 저장소입니다.
    # 전국 데이터 schema를 아직 적용하지 않은 개발 DB에서도 기획안 저장과 함께 동작합니다.
    measurement_baseline_sql = '''
        CREATE TABLE IF NOT EXISTS strategy_measurement_baseline (
            report_id VARCHAR(64) NOT NULL,
            region_code VARCHAR(10) NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            baseline_month CHAR(7) NOT NULL,
            observed_value DECIMAL(24,4) NOT NULL,
            unit VARCHAR(40) NOT NULL,
            source_references_json JSON NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (report_id, metric_name),
            KEY ix_measurement_baseline_region (region_code, baseline_month)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    '''
    measurement_followup_sql = '''
        CREATE TABLE IF NOT EXISTS strategy_measurement_followup (
            followup_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            report_id VARCHAR(64) NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            observed_month CHAR(7) NOT NULL,
            observed_value DECIMAL(24,4) NOT NULL,
            unit VARCHAR(40) NOT NULL,
            source_references_json JSON NOT NULL,
            recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_measurement_followup (report_id, metric_name, observed_month)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(report_sql)
            cursor.execute(job_sql)
            cursor.execute(measurement_baseline_sql)
            cursor.execute(measurement_followup_sql)


def save_strategy_job(
    job_id: str,
    region_code: str,
    region_name: str,
    status: str,
    message: str,
    *,
    error: str = '',
    request_payload: dict[str, Any] | None = None,
    had_transient_references: bool = False,
) -> None:
    """작업 상태를 MySQL에 저장해 브라우저 이동과 AI 서버 재시작 뒤에도 조회하게 합니다.

    첨부 본문은 저장 금지 원칙을 지키기 위해 request_payload에 포함하지 않습니다.
    """
    values = {
        'job_id': job_id,
        'region_code': region_code,
        'region_name': region_name,
        'status': status,
        'message': message,
        'error': error,
        'request_json': json.dumps(request_payload, ensure_ascii=False, default=str) if request_payload is not None else None,
        'had_transient_references': had_transient_references,
    }
    sql = '''
        INSERT INTO strategy_report_jobs (
            job_id, region_code, region_name, status, message, error,
            request_json, had_transient_references
        ) VALUES (
            %(job_id)s, %(region_code)s, %(region_name)s, %(status)s, %(message)s, %(error)s,
            %(request_json)s, %(had_transient_references)s
        )
        ON DUPLICATE KEY UPDATE
            status=VALUES(status), message=VALUES(message), error=VALUES(error),
            request_json=COALESCE(VALUES(request_json), request_json),
            had_transient_references=VALUES(had_transient_references),
            updated_at=CURRENT_TIMESTAMP
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, values)


def update_strategy_job_state(job_id: str, status: str, message: str, error: str = '') -> None:
    """진행 단계만 갱신합니다. 최초 요청 조건은 그대로 유지합니다."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE strategy_report_jobs SET status=%s, message=%s, error=%s WHERE job_id=%s',
                (status, message, error, job_id),
            )


def read_strategy_job(job_id: str) -> dict[str, Any] | None:
    """메모리에 없는 작업을 MySQL에서 복구해 상태 조회에 사용합니다."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM strategy_report_jobs WHERE job_id=%s', (job_id,))
            row = cursor.fetchone()
    if not row:
        return None
    request_value = row.get('request_json')
    if isinstance(request_value, str):
        request_value = json.loads(request_value)
    return {
        'job_id': row['job_id'],
        'region_code': row['region_code'],
        'region_name': row['region_name'],
        'status': row['status'],
        'message': row['message'],
        'error': row['error'] or '',
        'request': request_value,
        'had_transient_references': bool(row['had_transient_references']),
    }


def list_interrupted_strategy_jobs() -> list[dict[str, Any]]:
    """서버 종료 당시 queued/running이던 작업만 오래된 순서로 반환합니다."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM strategy_report_jobs WHERE status IN ('queued', 'running') ORDER BY created_at ASC"
            )
            rows = cursor.fetchall()
    jobs: list[dict[str, Any]] = []
    for row in rows:
        request_value = row.get('request_json')
        if isinstance(request_value, str):
            request_value = json.loads(request_value)
        jobs.append({
            'job_id': row['job_id'], 'region_code': row['region_code'], 'region_name': row['region_name'],
            'status': row['status'], 'message': row['message'], 'error': row['error'] or '',
            'request': request_value, 'had_transient_references': bool(row['had_transient_references']),
        })
    return jobs


def save_strategy_report(report_id: str, region_code: str, report: dict[str, Any]) -> None:
    """완료된 AI 기획안 한 건을 저장하거나, 챗봇 수정본으로 갱신합니다."""
    strategy = (report.get('strategies') or [{}])[0]
    values = {
        'report_id': report_id,
        'region_code': region_code,
        'region_name': str(report.get('region_name') or '선택 지역'),
        'title': str(strategy.get('title') or '관광 전략 기획안'),
        'summary': str(report.get('summary') or ''),
        'report_json': json.dumps(report, ensure_ascii=False, default=str),
    }
    sql = '''
        INSERT INTO strategy_reports (report_id, region_code, region_name, title, summary, report_json)
        VALUES (%(report_id)s, %(region_code)s, %(region_name)s, %(title)s, %(summary)s, %(report_json)s)
        ON DUPLICATE KEY UPDATE
            region_name=VALUES(region_name), title=VALUES(title), summary=VALUES(summary),
            report_json=VALUES(report_json), updated_at=CURRENT_TIMESTAMP
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, values)


def _number_from_display(value: Any) -> float | None:
    """대시보드 표시용 '1,234명'을 저장 가능한 숫자로 바꿉니다.

    이 함수는 화면 문구를 다시 계산하지 않습니다. 생성에 사용한 snapshot의 관측값을
    그대로 baseline으로 보관하기 위한 변환만 담당합니다.
    """
    match = re.search(r'-?[\d,]+(?:\.\d+)?', str(value or ''))
    return float(match.group(0).replace(',', '')) if match else None


def _measurement_source_references(snapshot: dict[str, Any], source_label: str) -> list[dict[str, str]]:
    """기준값의 원자료 문구와, 있을 때만 전국 비교의 공식 출처 URL을 함께 보존합니다."""
    references: list[dict[str, str]] = [{'kind': 'regional_raw_snapshot', 'reference': source_label}]
    nationwide = snapshot.get('nationwide_comparison') or {}
    if nationwide.get('available'):
        for source in nationwide.get('source_records') or []:
            references.append({
                'kind': 'nationwide_official_dataset',
                'reference': str(source.get('source_id') or ''),
                'url': str(source.get('source_url') or ''),
            })
    return references


def save_strategy_measurement_baseline(report_id: str, region_code: str, snapshot: dict[str, Any]) -> int:
    """생성 시점의 실제 관측값을 기획안별 baseline으로 저장합니다.

    예측치·사용자 목표·LLM의 기대효과 문장은 넣지 않습니다. 이후 follow-up과 비교할
    수 있는 원자료 관측값만 저장해 정책 성과를 과장하지 않도록 합니다.
    """
    latest_month = str(snapshot.get('latest_month') or '')
    if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', latest_month):
        return 0
    metric_specs = {
        '월간 순 방문자 수': ('monthly_unique_visitors', '명'),
        '월간 외지인 관광소비 총액': ('monthly_tourism_spend', '원'),
        '외지인 숙박 방문 비율': ('overnight_ratio', '%'),
        '외지인 평균 숙박일수': ('average_stay_days', '일'),
    }
    rows: list[dict[str, Any]] = []
    for observation in snapshot.get('observations') or []:
        spec = metric_specs.get(str(observation.get('metric') or ''))
        value = _number_from_display(observation.get('value'))
        if not spec or value is None:
            continue
        rows.append({
            'report_id': report_id,
            'region_code': region_code,
            'metric_name': spec[0],
            'baseline_month': latest_month,
            'observed_value': value,
            'unit': spec[1],
            'source_references_json': json.dumps(
                _measurement_source_references(snapshot, str(observation.get('source') or '')),
                ensure_ascii=False,
            ),
        })
    if not rows:
        return 0
    sql = '''
        INSERT INTO strategy_measurement_baseline (
            report_id, region_code, metric_name, baseline_month, observed_value, unit, source_references_json
        ) VALUES (
            %(report_id)s, %(region_code)s, %(metric_name)s, %(baseline_month)s,
            %(observed_value)s, %(unit)s, %(source_references_json)s
        ) ON DUPLICATE KEY UPDATE
            baseline_month=VALUES(baseline_month), observed_value=VALUES(observed_value), unit=VALUES(unit),
            source_references_json=VALUES(source_references_json)
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(sql, rows)
    return len(rows)


def save_strategy_measurement_followup(
    report_id: str,
    metric_name: str,
    observed_month: str,
    observed_value: float,
    unit: str,
    source_references: list[dict[str, str]],
) -> None:
    """후속 실제 관측값을 기록합니다. 사용자 목표나 예상값은 이 함수로 저장하지 않습니다."""
    sql = '''
        INSERT INTO strategy_measurement_followup (
            report_id, metric_name, observed_month, observed_value, unit, source_references_json
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            observed_value=VALUES(observed_value), unit=VALUES(unit),
            source_references_json=VALUES(source_references_json), recorded_at=CURRENT_TIMESTAMP
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (
                report_id, metric_name, observed_month, observed_value, unit,
                json.dumps(source_references, ensure_ascii=False),
            ))


def list_strategy_measurements(report_id: str) -> dict[str, list[dict[str, Any]]]:
    """기획안별 baseline과 실제 follow-up을 분리해 반환합니다."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''SELECT metric_name, baseline_month, observed_value, unit, source_references_json
                   FROM strategy_measurement_baseline WHERE report_id=%s ORDER BY metric_name''',
                (report_id,),
            )
            baselines = cursor.fetchall()
            cursor.execute(
                '''SELECT metric_name, observed_month, observed_value, unit, source_references_json, recorded_at
                   FROM strategy_measurement_followup WHERE report_id=%s ORDER BY observed_month, metric_name''',
                (report_id,),
            )
            followups = cursor.fetchall()
    for row in [*baselines, *followups]:
        value = row.get('source_references_json')
        row['source_references'] = json.loads(value) if isinstance(value, str) else (value or [])
        row.pop('source_references_json', None)
        if row.get('recorded_at'):
            row['recorded_at'] = row['recorded_at'].isoformat()
    return {'baselines': baselines, 'followups': followups}


def list_strategy_reports() -> list[dict[str, Any]]:
    """게시판에 필요한 가벼운 목록만 최신 생성일 순으로 반환합니다."""
    sql = '''
        SELECT report_id, region_code, region_name, title, summary, created_at, word_path, ppt_path
        FROM strategy_reports ORDER BY created_at DESC
    '''
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    return [
        {
            'entryId': row['report_id'], 'regionCode': row['region_code'], 'regionName': row['region_name'],
            'title': row['title'], 'summary': row['summary'], 'savedAt': row['created_at'].isoformat(),
            'wordReady': bool(row['word_path'] and Path(row['word_path']).exists()),
            'pptReady': bool(row['ppt_path'] and Path(row['ppt_path']).exists()),
        }
        for row in rows
    ]


def read_strategy_report(report_id: str) -> dict[str, Any] | None:
    """게시판에서 제목을 눌렀을 때 MySQL의 원본 기획안 JSON을 읽습니다."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT report_json FROM strategy_reports WHERE report_id=%s', (report_id,))
            row = cursor.fetchone()
    if not row:
        return None
    value = row['report_json']
    return json.loads(value) if isinstance(value, str) else value


def write_document(report_id: str, file_format: str, content: bytes) -> Path:
    """생성된 Word/PPT 파일을 로컬 서버에 한 번 저장하고 DB에 경로를 기록합니다."""
    if file_format not in {'docx', 'pptx'}:
        raise ValueError('지원하지 않는 문서 형식입니다.')
    DOCUMENT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = DOCUMENT_DIRECTORY / f'{report_id}.{file_format}'
    path.write_bytes(content)
    column = 'word_path' if file_format == 'docx' else 'ppt_path'
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'UPDATE strategy_reports SET {column}=%s WHERE report_id=%s', (str(path), report_id))
    return path


def read_document(report_id: str, file_format: str) -> bytes | None:
    """저장된 파일이 있으면 재생성하지 않고 그대로 내려보냅니다."""
    if file_format not in {'docx', 'pptx'}:
        return None
    column = 'word_path' if file_format == 'docx' else 'ppt_path'
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {column} FROM strategy_reports WHERE report_id=%s', (report_id,))
            row = cursor.fetchone()
    path = Path(row[column]) if row and row[column] else None
    return path.read_bytes() if path and path.is_file() else None


def strategy_store_health() -> dict[str, str]:
    """운영 점검용으로 DB 연결과 테이블 준비 상태를 확인합니다."""
    initialize_strategy_store()
    return {'status': 'ok', 'checked_at': datetime.now().isoformat(timespec='seconds')}
