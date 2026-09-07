"""Read-only saved-report/PPT snapshot; no LLM calls."""
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
from xml.etree import ElementTree as ET
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
ID = '0d6c8644149a48149b47da7250965fbc'
with urlopen(f'http://127.0.0.1:8111/ai/v1/strategy-reports/{ID}',timeout=20) as r:
    report=json.load(r)
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with urlopen(f'http://127.0.0.1:8111/ai/v1/strategy-reports/{ID}/documents/pptx',timeout=120) as r:
    (OUT/'original.pptx').write_bytes(r.read())
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with ZipFile(ROOT/'ai_server/app/templates/tourism_strategy_12_slide_template.pptx') as z:
    dims=ET.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',ns).attrib
    slides=[]
    for i in range(1,13):
        xml=ET.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
        shapes=[]
        for s in xml.find('p:cSld/p:spTree',ns):
            nv=s.find('.//p:cNvPr',ns)
            if nv is None: continue
            shapes.append({'name':nv.get('name'),'text':'\n'.join(t.text or '' for t in s.findall('.//a:t',ns)), 'xml':ET.tostring(s,encoding='unicode')})
        slides.append(shapes)
(OUT/'source-layout.json').write_text(json.dumps({'dimensions':dims,'slides':slides},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'dimensions':dims,'slides':len(slides),'sources':len(report['evidence_sources'])}))
