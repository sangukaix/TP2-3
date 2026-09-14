import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root))
# Application dependencies already installed in the project; bundled runtime is
# used for artifact generation, with no package installation or global changes.
sys.path.append(str(root/'backend/.venv/Lib/site-packages'))
from ai_server.app.proposal_presentation import create_strategy_proposal_presentation
from ai_server.app.proposal_document import create_strategy_proposal_document
r=json.loads((Path(__file__).parent/'original.json').read_text(encoding='utf-8'))
p=root/'output/jeju_revision_20260911';p.mkdir(exist_ok=True,parents=True)
for ext,fn in [('pptx',create_strategy_proposal_presentation),('docx',create_strategy_proposal_document)]:
    content=fn(r).getvalue()
    (p/('제주시_관광전략기획안_인포그래픽_v2.'+ext)).write_bytes(content)
    print(ext,len(content),flush=True)
