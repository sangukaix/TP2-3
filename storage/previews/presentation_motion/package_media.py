from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import runpy
p=Path(__file__).parent
# Reuse the existing targeted formatting repair on this new candidate only.
repair=(p.parent/'final_presentation/repair_package.py').read_text(encoding='utf-8')
exec(compile(repair,str(p/'repair_package.py'),'exec'),{'__file__':str(p/'repair_package.py')})
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
with ZipFile(p/'candidate.pptx') as z: parts={n:z.read(n) for n in z.namelist()}
slide=E.fromstring(parts['ppt/slides/slide4.xml'])
pics=slide.findall('.//p:pic',ns)
matches=pics
assert len(matches)==1,[(q.find('p:nvPicPr/p:cNvPr',ns).attrib) for q in pics]
matches[0].find('p:nvPicPr/p:cNvPr',ns).set('descr','Homepage four-step animation; 16 second loop; illustrative homepage demo values')
rid=matches[0].find('.//a:blip',ns).get('{'+ns['r']+'}embed')
rels=E.fromstring(parts['ppt/slides/_rels/slide4.xml.rels'])
rel=[r for r in rels if r.get('Id')==rid][0]
rel.set('Target','../media/home_workflow.gif')
parts['ppt/slides/_rels/slide4.xml.rels']=E.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
parts['ppt/slides/slide4.xml']=E.tostring(slide,xml_declaration=True,encoding='UTF-8',standalone=True)
types=E.fromstring(parts['[Content_Types].xml'])
if not any(e.get('Extension')=='gif' for e in types):
 E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',Extension='gif',ContentType='image/gif')
parts['[Content_Types].xml']=E.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
parts['ppt/media/home_workflow.gif']=(p/'home_workflow.gif').read_bytes()
with ZipFile(p/'candidate.pptx','w',ZIP_DEFLATED) as z:
 for n,data in parts.items():z.writestr(n,data)
print('Embedded original captured GIF in slide 4')
