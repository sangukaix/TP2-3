"""Read-only audit results. Green means verified, never a future-success promise."""
import json
from datetime import datetime, timezone
from pathlib import Path

AUDIT_PATH=Path(__file__).resolve().parents[2]/'storage/region_readiness_audit.json'

def read_audit():
    try:
        data=json.loads(AUDIT_PATH.read_text(encoding='utf-8'))
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(data['checked_at'])).total_seconds()
        if not 0<=age<86400:raise ValueError('expired')
        return data
    except (OSError,ValueError,KeyError,TypeError):
        return {'regions':[], 'checked_at':None,'status':'not_checked'}

def readiness_for(code):
    return next((r for r in read_audit()['regions'] if r['region_code']==code),{})
