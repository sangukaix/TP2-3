from pathlib import Path
import re
p=Path(__file__).parent
src=(p.parent/'final_presentation/build.mjs').read_text(encoding='utf-8')
extra=(p/'new_slides.txt').read_text(encoding='utf-8')
toc,demo,bridge=re.split(r'// INSERT_(?:TOC|DEMO|BRIDGE)\n',extra)[1:]
src=src.replace("const DIR=path.join(ROOT,'storage/previews/final_presentation');", "const BASE=path.join(ROOT,'storage/previews/final_presentation');\nconst DIR=path.join(ROOT,'storage/previews/presentation_motion');\nconst MOTION=DIR;\nconst headings=JSON.parse(await fs.readFile(path.join(DIR,'additions.json'),'utf8'));" )
src=src.replace("path.join(DIR,'assets/", "path.join(BASE,'assets/")
src=src.replace("path.join(DIR,'planning_current.png')", "path.join(MOTION,'planning.png')")
src=src.replace('// 02\n',toc+'\n// 02\n').replace('// 03\n',demo+'\n// 03\n').replace('// 04\n',bridge+'\n// 04\n')
src=src.replace("text(s,title,56,78,1168,65,40,dark?C.white:C.ink,true);", "const heading=headings.titles[n-1];\n if(heading===undefined)throw new Error('Missing heading '+n);\n text(s,heading,56,78,1168,65,36,dark?C.white:C.ink,true);\n const sectionId=Number(heading.match(/^([1-7])\\./)?.[1]||0);\n section=sectionId?sectionId+'. '+headings.sections[sectionId-1]:section;" )
src=src.replace("+' / 30'", "+' / 38'")
src=src[:src.index("if(process.argv.includes('--finalize'))")]
(p/'build.mjs').write_text(src,encoding='utf-8')
print('Prepared inherited deck with 8 added slides')
