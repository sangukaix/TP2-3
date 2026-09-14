from pathlib import Path
import json,re
p=Path(__file__).parent
source=(p.parent/'presentation_motion/build.mjs').read_text(encoding='utf-8')
chunks=re.split(r'(?=\{\n const s=slide\()',source)
prefix=chunks[0]
parts=chunks[1:]
last,end=parts[-1].split('\nawait fs.mkdir(OUT',1)
parts[-1]=last
end='\nawait fs.mkdir(OUT'+end
new=dict((m.group(1),m.group(2)) for m in re.finditer(r'@@(\w+)\n([\s\S]*?)(?=@@|\Z)',(p/'new_slides.txt').read_text(encoding='utf-8')))
seq=[1,2,3,4,5,'combined',10,'journey',*range(12,32),'execution','estimate',32,33,'admin_ml','admin_agents','admin_router',*range(34,39)]
assert len(seq)==40
old=json.loads((p.parent/'presentation_motion/additions.json').read_text(encoding='utf-8'))
titles=[]
names={'combined':'대시보드의 지역·지표·추세·소비','journey':'접속부터 기획서 다운로드까지','execution':'생성 문서의 실행 가이드와 KPI 근거','estimate':'생성 문서의 견적과 산출근거','admin_ml':'어드민 기능과 머신러닝 결과','admin_agents':'어드민의 Agent 역할·입력·도구','admin_router':'OpenAI·로컬 LLM 라우팅 설정'}
sections=old['sections'];sections[-1]='어드민·검증·운영'
counts={}
for i,item in enumerate(seq,1):
 if i<=2: titles.append(old['titles'][i-1]);continue
 section=1 if i<=4 else 2 if i<=8 else 3 if i<=11 else 4 if i<=17 else 5 if i<=25 else 6 if i<=32 else 7
 counts[section]=counts.get(section,0)+1
 name=names[item] if isinstance(item,str) else re.sub(r'^\d+\.\d+\s+','',old['titles'][item-1])
 titles.append(f'{section}.{counts[section]} {name}')
(p/'additions.json').write_text(json.dumps({'titles':titles,'sections':sections},ensure_ascii=False,indent=2),encoding='utf-8')
prefix=prefix.replace("const DIR=path.join(ROOT,'storage/previews/presentation_motion');","const DIR=path.join(ROOT,'storage/previews/presentation_revision');")
prefix=prefix.replace('const MOTION=DIR;',"const MOTION=path.join(ROOT,'storage/previews/presentation_motion');\nconst shortNotes=JSON.parse(await fs.readFile(path.join(DIR,'short_notes.json'),'utf8'));\nconst previousNotes=JSON.parse(await fs.readFile(path.join(MOTION,'speaker_notes.json'),'utf8'));\nconst combinedNotes=previousNotes.slice(5,9).map(n=>n.notes.split('\\n\\n[구현 근거]')[0]).join('\\n\\n');")
prefix=prefix.replace(" text(s,'OLIGO-K',56,24,150,26,15,dark?C.lime:C.teal,true);",'')
prefix=prefix.replace(" text(s,section,56,678,800,22,13,dark?C.line:C.muted);"," if(n>1)text(s,n===2?'발표 구성':section,56,25,1060,37,23,dark?C.lime:C.teal,true);")
prefix=prefix.replace("+' / 38'","+' / 40'")
prefix=prefix.replace("const value=body+'\\n\\n[구현 근거]\\n'", "if(!shortNotes[n-1])throw new Error('Missing concise script '+n);\n const value='[상세 발표 스크립트]\\n'+body+'\\n\\n[간소화 발표 스크립트]\\n'+shortNotes[n-1]+'\\n\\n[구현 근거]\\n'")
toc=parts[1]
toc=re.sub(r" const entries=\[.*?;\n", " const entries="+json.dumps([
['1. 서비스 개요','기획 목적 · 메인 4단계 모션','03–04'],['2. 실제 화면과 이용 흐름','대시보드 · 입력 · 생성 · 다운로드','05–08'],['3. 시스템 구조','React · API · 비동기 생성 작업','09–11'],['4. 데이터와 머신러닝','원자료 · MySQL · 7개 ML · 평가','12–17'],['5. 공식 근거와 AI Agent','유사지역 · RAG · 역할 · 모델 라우팅','18–25'],['6. 기획안과 문서 출력','계산 원리 · 실제 문서 · 챗봇 조정','26–32'],['7. 어드민·검증·운영','ML·Agent·Router 관리 · 검증 · 시연','33–40']],ensure_ascii=False)+";\n",toc)
toc=toc.replace('하단에는 섹션 이름과 전체 슬라이드 번호가 있습니다.','왼쪽 위에는 섹션 이름, 오른쪽 아래에는 전체 슬라이드 번호가 있습니다.')
parts[1]=toc
result=prefix+''.join(new[x] if isinstance(x,str) else parts[x-1] for x in seq)+end
result=result.replace("'ai_server/app/llm/runtime_config.py'","'storage/llm_runtime_config.json'")
(p/'build.mjs').write_text(result,encoding='utf-8')
print('Prepared',len(seq),'slides')
