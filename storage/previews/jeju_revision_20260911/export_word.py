import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
sys.path.append(str(Path('backend/.venv/Lib/site-packages').resolve()))
from ai_server.app.proposal_document import create_strategy_proposal_document
report=json.loads(Path('storage/previews/jeju_revision_20260911/original.json').read_text(encoding='utf-8'))
target=Path('output/jeju_revision_20260911/제주시_관광전략기획안_Word_최종.docx')
target.write_bytes(create_strategy_proposal_document(report).getvalue())
print(target, target.stat().st_size)
