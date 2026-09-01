"""MySQL에 생성 기획안과 출력 문서를 영구 보관하는 저장소 계층입니다.

브라우저 localStorage는 개인 PC에만 남기 때문에, 팀이 함께 보는 기획안 기록에는
사용하지 않습니다. 이 모듈은 MySQL에는 기획안 JSON과 파일 경로를, 로컬 서버에는
Word·PowerPoint 파일을 저장합니다.
"""

from __future__ import annotations

import json
import os
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
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(report_sql)
            cursor.execute(job_sql)


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
