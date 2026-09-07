"""Re-export the existing successful Wonju report; no paid API or LLM generation."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from ai_server.app.runtime_env import load_project_env
from ai_server.app.proposal_evidence import enrich_source_names,build_reference_estimate
from ai_server.app.proposal_presentation import create_strategy_proposal_presentation
OUT=Path(__file__).resolve().parent
report=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
enriched=enrich_source_names(report,load_project_env(ROOT))
(OUT/'enriched.json').write_text(json.dumps(enriched,ensure_ascii=False,indent=2),encoding='utf-8')
dest=ROOT/'storage/previews/원주시_관광전략기획안_실제데이터_수정본.pptx'
dest.write_bytes(create_strategy_proposal_presentation(enriched).getvalue())
print(json.dumps({'output':str(dest),'source_resolution':enriched.get('document_source_resolution'),
 'resolved':sum(bool(s.get('source_file_name')) for s in enriched['evidence_sources']),
 'estimate':build_reference_estimate(enriched)['total_krw']},ensure_ascii=False))
