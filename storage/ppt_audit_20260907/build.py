"""Offline export: saved ML, explicitly illustrative target rates."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from ai_server.app.proposal_presentation import create_strategy_proposal_presentation
report=json.loads((ROOT/'storage/ppt_audit_20260905/enriched.json').read_text(encoding='utf-8'))
OUT=ROOT/'storage/previews'
from contextlib import nullcontext
with nullcontext():
    for sample in (False,True):
        payload=copy.deepcopy(report)
        if sample:
            payload['execution_scenario']={'visitor_target_pct':2,'spending_target_pct':3}
            payload['layout_target_sample']=True
        path=OUT/('원주시_기획서_v9_목표비교_예시.pptx' if sample else '원주시_기획서_v9_저장데이터.pptx')
        path.write_bytes(create_strategy_proposal_presentation(payload).getvalue())
        print(path)
