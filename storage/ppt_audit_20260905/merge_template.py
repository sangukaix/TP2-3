"""OPC copy: keep eight original slides and every original theme byte unchanged.

Only artifact-tool-authored slides 5,8,9,11 and their chart/table dependencies
are copied. No slide drawing or python-pptx authoring is performed here.
"""
from pathlib import Path, PurePosixPath
import posixpath
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as E
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
SOURCE=ROOT/'ai_server/app/templates/tourism_strategy_12_slide_template.pptx'
DEST=SOURCE.with_name('tourism_strategy_12_slide_template_v6.pptx')
R='http://schemas.openxmlformats.org/package/2006/relationships'
T='http://schemas.openxmlformats.org/package/2006/content-types'
def relpath(p):
    return str(PurePosixPath(p).parent/'_rels'/(PurePosixPath(p).name+'.rels'))
with ZipFile(SOURCE) as old, ZipFile(OUT/'artifact_template.pptx') as new:
    parts={n:old.read(n) for n in old.namelist()}
    content=E.fromstring(parts['[Content_Types].xml'])
    types=E.fromstring(new.read('[Content_Types].xml'))
    mapped={}
    def copy(part):
        part=part.lstrip('/')
        if part in mapped: return mapped[part]
        dest='ppt/audit_v6/'+part.removeprefix('ppt/')
        mapped[part]=dest
        parts[dest]=new.read(part)
        for t in types:
            if t.get('PartName')=='/'+part:
                E.SubElement(content,'{'+T+'}Override',PartName='/'+dest,ContentType=t.get('ContentType'))
        rp=relpath(part)
        if rp in new.namelist():
            rs=E.fromstring(new.read(rp))
            for r in rs:
                if r.get('TargetMode')=='External': continue
                target=posixpath.normpath(posixpath.join(posixpath.dirname(part),r.get('Target')))
                if target.startswith('/'):target=target[1:]
                copied=copy(target.lstrip('/'))
                r.set('Target',posixpath.relpath(copied,posixpath.dirname(dest)))
            parts[relpath(dest)]=E.tostring(rs,encoding='utf-8',xml_declaration=True)
        return dest
    for i in (5,8,9,11):
        part=f'ppt/slides/slide{i}.xml'
        oldrels=E.fromstring(old.read(relpath(part)))
        oldlayout=next(r.get('Target') for r in oldrels if r.get('Type','').endswith('/slideLayout'))
        rs=E.fromstring(new.read(relpath(part)))
        for r in list(rs):
            typ=r.get('Type','')
            if typ.endswith('/slideLayout'):
                r.set('Target',oldlayout)
            elif typ.endswith('/notesSlide'):
                rs.remove(r)
            elif r.get('TargetMode')!='External':
                target=posixpath.normpath(posixpath.join('ppt/slides',r.get('Target')))
                copied=copy(target)
                r.set('Target',posixpath.relpath(copied,'ppt/slides'))
        parts[part]=new.read(part)
        parts[relpath(part)]=E.tostring(rs,encoding='utf-8',xml_declaration=True)
    exts={t.get('Extension') for t in content if t.tag.endswith('Default')}
    for t in types:
        if t.tag.endswith('Default') and t.get('Extension') not in exts:
            content.append(t);exts.add(t.get('Extension'))
    parts['[Content_Types].xml']=E.tostring(content,encoding='utf-8',xml_declaration=True)
    with ZipFile(DEST,'w',ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
    assert all(parts[n]==old.read(n) for n in old.namelist() if n.startswith('ppt/theme/'))
    assert all(parts[f'ppt/slides/slide{i}.xml']==old.read(f'ppt/slides/slide{i}.xml') for i in (1,2,3,4,6,7,10,12))
print(DEST)
