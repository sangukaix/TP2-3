"""Persist material readiness; recheck input changes, not elapsed audit age."""
import json
import hashlib
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH=ROOT/'storage/region_readiness_audit.json'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def file_signature(entry):
    """Local file inventory detects replacement/removal without loading models."""
    paths = [entry.raw_path, ROOT/'artifacts/ml'/entry.region_code,
             ROOT/'data/rag/official_case_studies.jsonl',
             ROOT/'data/rag/official_reference_documents.jsonl']
    records = []
    for path in paths:
        if not path.exists():
            records.append((str(path.relative_to(ROOT)), 'missing'))
            continue
        for item in sorted(path.rglob('*')) if path.is_dir() else [path]:
            if item.is_file():
                stat = item.stat()
                records.append((str(item.relative_to(ROOT)), stat.st_size, stat.st_mtime_ns))
    return _digest([asdict(entry), records])


def sql_signatures():
    """One bounded read for all regions; detects removed/changed SQL inputs."""
    import pymysql
    from .runtime_env import load_project_env
    env = load_project_env(ROOT)
    with pymysql.connect(host=env.get('MYSQL_HOST') or '127.0.0.1',
                         port=int(env.get('MYSQL_PORT') or 3306),
                         user=env.get('MYSQL_USER') or 'tourism_app',
                         password=env.get('MYSQL_PASSWORD') or '',
                         database=env.get('MYSQL_DATABASE') or 'tourism_strategy',
                         charset='utf8mb4', connect_timeout=3, read_timeout=5,
                         cursorclass=pymysql.cursors.DictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT rpc.*, dr.province_name, dr.local_hierarchy_name FROM regional_planning_context rpc JOIN dim_region dr ON dr.region_code=rpc.region_code ORDER BY rpc.region_code')
            contexts = cur.fetchall()
            cur.execute('SELECT peer.*, dr.province_name, dr.local_hierarchy_name FROM regional_peer_comparison peer JOIN dim_region dr ON dr.region_code=peer.peer_region_code ORDER BY peer.region_code,peer.peer_rank')
            peers = {}
            for row in cur.fetchall(): peers.setdefault(str(row['region_code']), []).append(row)
    return {str(row['region_code']): _digest([row, peers[str(row['region_code'])]])
            for row in contexts if peers.get(str(row['region_code']))}

def read_audit():
    try:
        data=json.loads(AUDIT_PATH.read_text(encoding='utf-8'))
        from ..ml.region_catalog import list_region_data_catalog
        from ..ml.data_freshness import assess_data_freshness
        entries = {e.region_code:e for e in list_region_data_catalog()}
        try:
            sql = sql_signatures()
            data['sql_ready'] = True
        except Exception:
            sql = {}; data['sql_ready'] = False
        for row in data['regions']:
            code = row['region_code']
            reason = None
            if code not in entries: reason = '지역 등록 확인 필요'
            elif not row.get('input_signature'): reason = '자료 점검 갱신 필요'
            elif row['input_signature'] != file_signature(entries[code]): reason = '원자료·모델 변경 후 점검 필요'
            elif not data['sql_ready']: reason = 'SQL 연결 확인 필요'
            elif not sql.get(code): reason = 'SQL 지역 비교 자료 확인 필요'
            elif row.get('sql_signature') != sql[code]: reason = 'SQL 자료 변경 후 점검 필요'
            elif not assess_data_freshness((row.get('details') or {}).get('latest_observed_month')).can_generate:
                reason = '최신 월별 자료 갱신 필요'
            if reason:
                row['data_ready'] = False
                row['readiness_reason'] = reason
        data['status'] = 'completed'
        return data
    except (OSError,ValueError,KeyError,TypeError):
        return {'regions':[], 'checked_at':None,'status':'not_checked'}

def readiness_for(code):
    return next((r for r in read_audit()['regions'] if r['region_code']==code),{})
