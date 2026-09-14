"""Repair two exporter formatting gaps without changing native objects or data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

p=Path(__file__).with_name('candidate.pptx')
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
def tag(prefix,name):return '{'+ns[prefix]+'}'+name
with ZipFile(p) as z: contents={i.filename:(i,z.read(i.filename)) for i in z.infolist()}
for name,(info,data) in list(contents.items()):
    if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
        root=E.fromstring(data)
        for cell in root.findall('.//a:tcPr',ns):
            for side in ('lnL','lnR','lnT','lnB'):
                line=cell.find('a:'+side,ns)
                if line is None:line=E.SubElement(cell,tag('a',side))
                line.clear();line.set('w','9525')
                solid=E.SubElement(line,tag('a','solidFill'))
                E.SubElement(solid,tag('a','srgbClr'),val='B8CBC9')
                E.SubElement(line,tag('a','prstDash'),val='solid')
        contents[name]=(info,E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True))
    elif '/charts/chart' in name and name.endswith('.xml'):
        root=E.fromstring(data)
        for labels in root.findall('.//c:dLbls',ns):
            number=labels.find('c:numFmt',ns)
            if number is None:
                number=E.Element(tag('c','numFmt'));labels.insert(0,number)
            number.set('formatCode','0.00"%"');number.set('sourceLinked','0')
        contents[name]=(info,E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True))
with ZipFile(p,'w',ZIP_DEFLATED) as z:
    for info,data in contents.values():z.writestr(info,data)
print('Native table borders and chart precision repaired')
