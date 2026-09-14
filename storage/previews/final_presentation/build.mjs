import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import { applyPresentationChartFont, finalizePresentation } from 'file:///C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations/container_tools/artifact_tool_utils.mjs';

const ROOT='C:/Users/Admin/mbca/TP2-3';
const DIR=path.join(ROOT,'storage/previews/final_presentation');
const OUT=path.join(ROOT,'output/presentation');
const SKILL='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const C={paper:'#F7F6F1',ink:'#153E43',teal:'#167D85',lime:'#D5EB72',muted:'#61747A',line:'#B8CBC9',pale:'#E8EFEC',white:'#FFFFFF',orange:'#D66F32'};
const FONT='Malgun Gothic';
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const narrative=[];
function text(s,t,x,y,w,h,size=25,color=C.ink,bold=false){
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=t;sh.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none'};return sh;
}
function rect(s,x,y,w,h,fill=C.pale,line='none') {return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:line==='none'?0:1}});}
function rule(s,x,y,w,color=C.line){rect(s,x,y,w,1,color);}
function arrow(s,x,y,w=40,vertical=false,color=C.teal){return s.shapes.add({geometry:vertical?'downArrow':'rightArrow',position:{left:x,top:y,width:vertical?20:w,height:vertical?w:18},fill:color,line:{fill:'none',width:0}});}
function box(s,title,body,x,y,w,h=110,fill=C.pale){rect(s,x,y,w,h,fill);text(s,title,x+18,y+15,w-36,38,25,C.ink,true);if(body)text(s,body,x+18,y+54,w-36,h-59,20,C.muted);}
function slide(title,section='SYSTEM',dark=false){
 const s=deck.slides.add();s.background.fill=dark?C.ink:C.paper;
 const n=deck.slides.items.length;
 text(s,'OLIGO-K',56,24,150,26,15,dark?C.lime:C.teal,true);
 text(s,title,56,78,1168,65,40,dark?C.white:C.ink,true);
 text(s,section,56,678,800,22,13,dark?C.line:C.muted);
 text(s,String(n).padStart(2,'0')+' / 30',1138,678,90,22,14,dark?C.line:C.muted);
 return s;
}
function note(s,body,sources=[]){
 const n=deck.slides.items.indexOf(s)+1;
 const value=body+'\n\n[구현 근거]\n'+sources.map(x=>x.startsWith('http')?x:ROOT+'/'+x).join('\n');
 s.speakerNotes.textFrame.setText(value);narrative.push({slide:n,notes:value});
}
function foot(s,t,dark=false){text(s,t,56,626,1168,40,17,dark?C.line:C.muted);}
function table(s,values,widths,{x=56,y=185,w=1168,h=380,size=22}={}){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.borders.assign({fill:C.paper,width:2,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.ink:r%2?C.white:C.pale;
  cell.text.style={typeface:FONT,fontSize:size,color:r===0?C.white:C.ink,bold:r===0||c===0,autoFit:'none'};
 }
 t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{left:13,right:13,top:10,bottom:10},anchor:'center'});
 return t;
}
async function picture(s,file,x,y,w,h,alt){s.images.add({blob:new Uint8Array(await fs.readFile(file)),contentType:'image/png',fit:'contain',position:{left:x,top:y,width:w,height:h},alt});}
function columns(s,entries,y=190){
 const gap=48,w=(1168-gap*(entries.length-1))/entries.length;
 entries.forEach((e,i)=>{const x=56+i*(w+gap);text(s,e[0],x,y,w,55,28,C.teal,true);rule(s,x,y+64,w);text(s,e[1],x,y+90,w,240,25);});
}

// 01
{
 const s=slide('','FINAL PROJECT  /  2026.09');
 await picture(s,path.join(DIR,'assets/original_1_2.png'),0,0,1280,720,'사용자 제공 초안의 관광도시 콘셉트 이미지');
 text(s,'4조  2차 프로젝트',56,55,340,32,20,C.teal,true);
 text(s,'OLIGO-K',56,178,480,100,68,C.ink,true);
 text(s,'지역 관광사업\n기획서 생성\n웹서비스',56,285,420,178,35,C.ink,true);
 text(s,'공식 데이터와 사례 기반\n지자체 관광 기획 지원',56,490,368,90,23,C.muted);
 text(s,'서비스 · 데이터 · ML · AI · 구현 결과',56,635,680,35,20,C.ink);
 note(s,'OLIGO-K는 관광 담당자가 지역 현황과 타지역 운영 사례를 함께 검토하고 관광사업 아이디어를 문서로 만드는 웹서비스입니다. 오늘은 사용자 흐름, 실제 코드 구조, 숫자 예측, 근거 조사, 기획 생성, 결과물과 남은 검증을 설명합니다. 초기 기획 문서의 STAY-UP AI는 같은 프로젝트의 초기 명칭이며 현재 발표와 서비스는 OLIGO-K 표기를 사용합니다. 표지 이미지는 사용자 제공 초안의 콘셉트 일러스트이며 실제 관광지 사진으로 제시하지 않습니다.',['docs/PROJECT_BRIEF.md','frontend/src/components/WorkspaceShell.jsx']);
}
// 02
{
 const s=slide('관광사업 기획에서 연결이 필요한 업무','01  SERVICE');
 text(s,'지역에서 무엇을 더 운영하면\n관광 경험과 소비가 나아질까?',56,182,690,150,39,C.ink,true);
 text(s,'시군구 관광 담당자와 지역 관광사업자를 위한\n사례 기반 아이디어와 실행 초안',56,358,690,100,27,C.muted);
 text(s,'현재 업무',840,181,340,42,27,C.teal,true);
 text(s,'통계 확인\n타지역 사례 조사\n우리 지역에 맞게 기획\n목표·견적·문서 작성',840,246,355,255,27);
 rule(s,56,543,1168);
 text(s,'기대효과',56,569,170,39,24,C.teal,true);
 text(s,'조사 근거와 작성 과정을 한 화면에서 확인하고 재사용',252,569,930,45,27,C.ink,true);
 note(s,'서비스의 중심은 부족하다는 진단을 반복하는 것이 아니라, 공식 사례의 운영 방식을 참고해 우리 지역에서 실행할 아이디어를 제시하는 것입니다. 방문·숙박 지표가 낮다고 바로 특정 사업의 필요성이 입증되지는 않습니다. 담당자는 사례와 조건을 검토하고 시범 범위를 결정합니다. 업무 시간 단축이나 방문객 증가의 실제 성과는 아직 사용자 실험으로 측정하지 않았으므로 기대효과로 소개합니다. 초기 인구감소지역 문제의식에서 현재 등록된 도시·군·구의 관광 기획 지원으로 범위를 넓혔습니다.',['docs/PROJECT_BRIEF.md','docs/CONTEST_EVIDENCE.md','ai_server/app/agents/prompts.py']);
}
// 03
{
 const s=slide('지역 선택부터 기획서 출력까지','01  SERVICE');
 const labels=[['01 지역 선택','지역 현황\n자료 준비 확인'],['02 조건 입력','사업 방향·예산\n시작 월'],['03 생성·검토','공식 사례 비교\n기획안 작성'],['04 수정·출력','챗봇 조정·저장\nPPTX / DOCX']];
 labels.forEach((v,i)=>{const x=56+i*299;box(s,v[0],v[1],x,190,269,126,i===2?C.lime:C.pale);if(i<3)arrow(s,x+274,243,20);});
 await picture(s,path.join(DIR,'planning_current.png'),56,349,594,252,'2026-09-10 실제 기획 조건 입력 화면');
 text(s,'감당할 수 있는 입력만 받기',703,350,505,42,29,C.teal,true);
 text(s,'사업 방향 4종과 사례 기반 추천\n참고 예산은 총액 배분에 반영\n자원 300자 · 현장 메모 500자\n시작 월부터 3개월 시범 운영',703,410,500,188,24);
 note(s,'현재 입력은 guided_v1입니다. 네 가지 사업 방향은 소비·환급, 숙박·체류, 야간 관광, 재방문·관광주민증입니다. 사례 기반 추천을 선택할 수도 있습니다. 참고 예산은 입력 총액에 맞춘 견적 배분이지 그 금액으로 KPI를 달성한다는 보장이 아닙니다. 제외 조건은 야간 또는 환급 방식입니다. Pydantic이 값·길이·충돌을 검증하고 해당 조건에 맞는 공식 사례와 후보만 남깁니다. 실제 연결된 후보 수는 보고서마다 다르며 항상 4개를 생성하지 않습니다. 스크린샷은 2026-09-10 실행 중인 React 화면입니다.',['frontend/src/pages/TourismPlanningPage.jsx','frontend/src/features/planning/planningBrief.js','ai_server/app/planning_brief.py','ai_server/app/case_recommendation.py']);
}
// 04
{
 const s=slide('전체 서비스 구조','02  ARCHITECTURE');
 box(s,'React + Vite','지역 선택·분석\n기획·문서 화면',56,295,280,145,C.lime);
 box(s,'일반 Backend','FastAPI\n지도 경계 조회·캐시',427,180,345,125);
 box(s,'AI Server','FastAPI\n관광 데이터·생성 작업',427,397,345,125);
 arrow(s,354,244,50);arrow(s,354,446,50);
 text(s,'/api',357,206,80,30,19,C.teal,true);text(s,'/ai',359,409,75,30,19,C.teal,true);
 box(s,'VWorld','행정구역 경계',866,180,358,106);arrow(s,792,223,53);
 box(s,'데이터와 모델','MySQL · 원자료 · Joblib',866,336,358,106);arrow(s,792,376,53);
 box(s,'근거와 생성','공식 문서 · Qwen · Gemma\nOpenAI API',866,480,358,121);arrow(s,792,529,53);
 foot(s,'현재 개발 포트: React 5176 · Backend 8100 · AI 8112 · Streamlit 8501');
 note(s,'현재 일반 Backend는 주로 VWorld 지도 경계를 제공하고 관광 데이터 조회·MySQL·ML·LLM·저장·출력은 AI Server에 있습니다. React는 /api와 /ai를 각각 호출하며 Vite 개발 프록시가 두 서버에 전달합니다. 일반 Backend를 거쳐서만 AI Server에 가는 구조로 설명하면 틀립니다. start-dev.ps1과 vite.config.js의 현재 기본 포트는 8100, 8112입니다. 초기 설계의 8000/8001과 구분합니다. Streamlit 구조 탐색기는 별도 보조 서비스입니다. 운영 설계에서는 Nginx가 정적 React와 두 API를 라우팅하며 AWS 배포 완료는 아직 확인되지 않았습니다.',['frontend/vite.config.js','backend/app/main.py','ai_server/app/main.py','start-dev.ps1','docs/ARCHITECTURE.md']);
}
// 05
{
 const s=slide('React 페이지와 공통 컴포넌트','02  ARCHITECTURE');
 text(s,'src/main.jsx\n└─ App.jsx\n   ├─ routes.js\n   └─ lazy + Suspense\n      ├─ TourismDashboardPage\n      ├─ TourismPlanningPage\n      ├─ TourismStrategyPage\n      └─ SavedStrategyPlansBoardPage',56,188,635,377,25,C.ink);
 text(s,'공통 화면',771,185,415,43,29,C.teal,true);
 text(s,'WorkspaceShell\nRegionWorkspacePicker\nWorkspaceAssistantPanel',771,240,450,125,24);
 rule(s,771,391,453);
 text(s,'데이터 표시',771,419,420,40,29,C.teal,true);
 text(s,'Leaflet 지도 · Recharts 차트\nAPI 모듈과 입력 상태 관리',771,478,440,90,24);
 foot(s,'별도 React Router 패키지 없이 pathname을 해석하며, 페이지를 지연 로딩합니다.');
 note(s,'프런트엔드는 React 19와 Vite를 사용합니다. App.jsx는 window.location.pathname을 routes.resolveAppRoute에 넘겨 pageId를 찾고 해당 페이지를 lazy import합니다. Suspense가 대기 화면을 제공합니다. routes.js는 정규 경로, /diagnosis와 /proposal 같은 이전 주소 별칭, 알 수 없는 경로 처리를 담당합니다. 일반적인 React Router 구성으로 소개하지 않습니다. 공통 shell과 region picker가 지역 상태 및 페이지 이동을 묶고 assistant panel이 챗봇을 제공합니다. 입력 조건은 지역별로 브라우저 localStorage에 보관합니다. 지도는 Leaflet, 차트는 Recharts이며 서버의 숫자를 화면에 렌더링합니다. 팀 학습용 /ml-test, /openai-test, /react-test, /llm-control, /project-tree도 별도 lazy 페이지입니다.',['frontend/src/main.jsx','frontend/src/App.jsx','frontend/src/routes.js','frontend/src/components/WorkspaceShell.jsx','frontend/src/components/RegionWorkspacePicker.jsx','frontend/src/components/WorkspaceAssistantPanel.jsx','frontend/package.json']);
}
// 06
{
 const s=slide('오래 걸리는 생성 요청의 처리','02  ARCHITECTURE');
 table(s,[['순서','React / API','서버에서 처리하는 일'],['1 요청','POST strategy-report/jobs','입력 검사 후 job_id 반환'],['2 실행','_run_strategy_report_job','저장 모델 추론·Agent 순차 처리'],['3 조회','GET 작업 상태 · 3초 간격','status · message · progress_step 전달'],['4 결과','기획 화면에서 미리보기','결과와 검수 상태를 따로 보관'],['5 저장','사용자의 저장 요청','MySQL 보고서와 문서 파일 연결']],[120,425,623],{h:379,size:23});
 foot(s,'데이터 분석 / 공식사례 확인 / 기획안 생성 / 품질검토는 실제 실행 지점에서 갱신됩니다.');
 note(s,'긴 모델 작업을 하나의 브라우저 요청이 끝날 때까지 기다리게 하지 않습니다. 생성 API가 작업 ID를 반환하고 서버의 _run_strategy_report_job이 작업합니다. 화면은 3초 간격으로 상태를 조회합니다. generation_progress.py의 ContextVar 콜백이 orchestrator 실제 단계에서 진행 번호와 설명을 전달합니다. 완료된 파트는 채운 색, 진행 파트는 애니메이션으로 구분합니다. 다른 화면에 갔다 돌아오면 서버의 상태를 다시 읽습니다. 서버가 재시작되면 동일 생성이 자동으로 이어지는 분산 작업 큐는 아니며 중단 상태를 처리합니다. 명시적 저장과 자동 작업 상태 보관의 차이를 설명합니다.',['ai_server/app/main.py','ai_server/app/generation_progress.py','ai_server/app/strategy_store.py','frontend/src/pages/TourismStrategyPage.jsx']);
}
// 07
{
 const s=slide('공식 원자료의 수집과 전처리','03  DATA & ML');
 const ls=[['공식 다운로드','데이터랩 CSV · Excel · ZIP'],['표준 월별 표','지역코드 + 기준월 + 단위'],['검증·저장','processed · MySQL · 출처'],['학습·조회','지역별 ML · 대시보드']];
 ls.forEach((v,i)=>{box(s,v[0],v[1],56+i*299,187,269,124);if(i<3)arrow(s,331+i*299,240,18);});
 columns(s,[['원자료 보존','data/raw는 수정하지 않음\n코드로 변환 과정 재현\n결측·0·미집계 구분'],['서로 다른 외부 API','TourAPI: 관광지·주소·이미지\nVWorld: 지도 경계\nOpenAI: 조사·생성·검토'],['활용 범위','등록 지역 89개\n지역별 7개 예측 지표\n원자료와 MySQL을 함께 조회']],367);
 note(s,'한국관광 데이터랩은 공식 다운로드나 허용 API로 수집하며 사이트를 크롤링하지 않습니다. regional_datalab_data.py가 표준 CSV 또는 ZIP을 읽고 지역별 어댑터가 같은 월별 표 계약을 제공합니다. 지역명만으로 결합하지 않고 검증된 region_code와 year_month를 사용합니다. 단위가 천원인 원자료는 원 단위로 변환하고 방문·외지인·숙박 정의를 구분합니다. 원본은 보존하고 파생 파일과 SQL 적재를 재현합니다. 원자료 최신월은 대부분 2026-06, 강남은 2026-07입니다. 2026-09-10 준비도 기록의 89개는 등록·자료 점검 대상 수이며 전국 모든 시군구나 모두 우수한 예측이라는 뜻은 아닙니다.',['ai_server/ml/regional_datalab_data.py','ai_server/ml/standard_region_pipeline.py','ai_server/ml/validation.py','data_pipeline/tools/import_mysql_bundle.py','storage/region_readiness_audit.json']);
}
// 08
{
 const s=slide('MySQL의 핵심 데이터 관계','03  DATA & ML');
 box(s,'dim_region','PK region_code',56,182,305,101,C.lime);
 box(s,'fact_tourism_monthly','PK region_code + year_month',450,182,420,101);arrow(s,379,223,50);
 text(s,'1 : N',381,188,70,30,18,C.teal,true);
 box(s,'출처 추적','지표별 원자료 연결\ndata_source',941,182,283,155);arrow(s,884,222,38);
 box(s,'비교 맥락','regional_planning_context\nregional_peer_comparison',56,386,389,145);
 box(s,'기획 결과','strategy_reports\n본문 JSON · 지역 · 파일 경로',478,386,361,145);
 box(s,'생성·성과 기록','strategy_report_jobs\n사업 전후 측정 테이블',873,386,351,145);
 foot(s,'관측 수치·출처·기획 기록은 MySQL, 저장 모델은 Joblib, 생성 문서는 파일로 관리합니다.');
 note(s,'상단은 스키마의 주요 FK 관계를 단순화한 ERD입니다. 지역 한 개에 여러 월별 지표가 연결되고 지표별 출처 테이블에서 원자료를 추적합니다. 하단은 관광기획 맥락, peer 비교, 보고서, 작업 상태, 전후 측정 기록의 역할 묶음입니다. 하단의 모든 테이블이 물리적 FK로 직접 연결됐다는 뜻은 아닙니다. 전체 SQL에는 추가 적재·관광지·ML·전국보조지표 테이블이 있으나 발표에서는 생성 경로에 필요한 구조를 제시합니다. Joblib 메타데이터와 실제 서비스 예측 경로가 있으므로 DB의 ml_prediction 테이블을 모든 예측의 유일한 저장소라고 설명하지 않습니다.',['database/mysql/001_nationwide_tourism_data.sql','ai_server/app/strategy_store.py','ai_server/app/nationwide_context_store.py']);
}
// 09
{
 const s=slide('7개 ML 결과를 사용하는 위치','03  DATA & ML');
 table(s,[['예측 지표','비교·조사에 사용하는 의미','사용 위치'],['방문자 수','관심과 실제 방문 규모의 흐름','전망 그래프·KPI + 조사 입력'],['관광소비액','지역 소비 규모와 계절 흐름','전망 그래프·KPI + 조사 입력'],['숙박 방문 비율','숙박으로 이어지는 비중','숙박·체류 사례 조사'],['평균 숙박일수','숙박 방문자의 머무는 길이','연박·다음 날 프로그램 조사'],['평균 체류시간','지역에서 보내는 시간','체험·거점 연결 사례 조사'],['내비게이션 검색','목적지에 대한 관심','안내·예약·현장 이용 연결 조사'],['숙박 검색','숙박 목적지에 대한 관심','숙박 연계 운영 조건 조사']],[268,502,398],{y:178,h:407,size:21});
 foot(s,'검색 ≠ 방문·예약 완료. 나머지 5개 지표의 본문 반영은 선택 사업과 LLM의 작성 결과에 따라 달라집니다.');
 note(s,'7개 지표는 같은 모델 하나의 출력 7개라고만 설명하기보다 지역별로 각 Target의 모델 또는 기준선을 선택한다고 설명합니다. 방문자와 소비액은 서로의 시차 feature를 함께 쓰고 나머지 지표는 해당 지표 자체 시차와 계절성을 씁니다. 방문·소비는 최종 문서의 ML 그래프와 KPI 계산에 직접 들어갑니다. 5개 보조 지표는 관리자 차트와 저장 ml_analysis에 보존되며 조사 질문과 후보 설계 입력에 사용합니다. 모두가 최종 본문에 반드시 인용되는 것은 아닙니다. 예측을 LLM에 공급했다는 사실과 실제 답변의 인과적 기여도는 다릅니다. 프롬프트 입력, planning_decision, 출처, 본문을 함께 보아야 실제 반영을 설명할 수 있습니다.',['ai_server/ml/module_usage.py','ai_server/ml/gangnam_forecast.py','ai_server/ml/planning_evidence.py','ai_server/app/report_projection.py']);
}
// 10
{
 const s=slide('직접 학습하는 예측 모델과 평가 절차','03  DATA & ML');
 text(s,'입력: 1·3·12개월 전 값 + 예측월의 계절 정보',56,176,1168,49,29,C.teal,true);
 const a=[['학습','2025.01–11','과거 Target 11개월'],['모델 선택','2025.12–2026.02','Validation MAE 비교'],['최종 평가','2026.03–06','선택에 쓰지 않은 Test']];
 a.forEach((v,i)=>{box(s,v[0],v[1]+'\n'+v[2],56+i*397,267,371,152,i===1?C.lime:C.pale);if(i<2)arrow(s,432+i*397,334,18);});
 text(s,'후보',56,468,160,40,27,C.teal,true);
 text(s,'RandomForestRegressor / LinearRegression\n각 지표의 후보와 전년 동월 기준선을 비교',243,465,958,94,27);
 foot(s,'원주시 저장 모델 기준. 평가 이후 전체 관측 이력으로 최종 fit하고 Joblib·메타데이터를 저장합니다.');
 note(s,'원주 원자료는 2024-01부터 2026-06까지 30개월입니다. 12개월 시차가 필요해 지도학습 Target은 2025-01부터 시작합니다. evaluation.select_and_evaluate는 Validation 3개월 MAE로 후보와 계절 기준선을 선택하고 최근 4개월 Test로 선택 모델 성능을 평가합니다. Test를 보고 사후에 모델을 바꾸지 않습니다. 방문자·내비·숙박검색 후보는 RandomForestRegressor(n_estimators=300,max_depth=3,min_samples_leaf=2,random_state=42), 소비·숙박일수·숙박률·체류시간 후보는 LinearRegression입니다. 모든 Target에 두 회귀모델을 경쟁시키는 구조는 아닙니다. 월은 sin/cos로 계절성을 표현합니다. 기준선이 선택되면 회귀모델을 저장하지 않고 전년 동월 값을 사용합니다. 웹에서 생성할 때마다 재학습하지 않습니다.',['ai_server/ml/gangnam_forecast.py','ai_server/ml/evaluation.py','artifacts/ml/51130/demand_model.metadata.json','ai_server/ml/scripts/train_regions.py']);
}
// 11
{
 const s=slide('방문자 예측 성능은 지역별로 다릅니다','03  DATA & ML');
 const chart=s.charts.add('bar',{position:{left:56,top:190,width:732,height:400},categories:['강남구','원주시'],series:[{name:'선택 모델',values:[3.05,4.37],fill:C.teal},{name:'전년 동월 기준',values:[3.78,3.99],fill:'#A9C2BC'}],barOptions:{direction:'column',grouping:'clustered',gapWidth:120},hasLegend:true,legend:{position:'bottom'},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.00"%"'},yAxis:{min:0,max:5,majorUnit:1,numberFormatCode:'0.0"%"'},chartFill:C.paper,plotAreaFill:C.paper});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,'Test MAPE',844,180,348,49,28,C.teal,true);
 text(s,'강남구 3.05%\n기준선보다 낮은 오차',844,257,350,106,28,C.ink,true);
 text(s,'원주시 4.37%\n기준선 3.99%보다 높음',844,399,355,105,28,C.ink,true);
 foot(s,'강남 2026.04–07 / 원주 2026.03–06, 각각 4개월. 서로 다른 기간의 사례 비교이며 전국 평균이 아닙니다.');
 note(s,'수치는 활성 지역별 artifacts/ml/11680 및 51130의 demand_model.metadata.json에서 읽었습니다. 강남 방문자 선택 모델 Test MAE는 537,513.50명, 기준은 673,789명이며 MAPE는 3.05%, 3.78%입니다. 원주는 103,646.64명 대 92,238.25명, MAPE 4.37% 대 3.99%입니다. 원주 모델은 Validation에서는 우수했지만 Test에서는 기준선보다 나빴습니다. 이 결과를 숨기거나 모든 지역에서 모델이 우수하다고 발표하지 않습니다. MAPE는 100에서 빼서 정확도라고 표현하지 않습니다. Test가 4개월로 짧다는 점과 지역별 기간이 다르다는 점을 함께 설명합니다. 1~3개월 재귀 예측의 별도 평가도 metadata에 있으며 4~12개월은 탐색 전망입니다.',['artifacts/ml/11680/demand_model.metadata.json','artifacts/ml/51130/demand_model.metadata.json','ai_server/ml/evaluation.py','ai_server/ml/planning_evidence.py']);
}
// 12
{
 const s=slide('예측값이 기획안까지 전달되는 과정','03  DATA & ML',true);
 const flow=[['저장 모델 추론','pipeline.predict'],['수치·신호 묶음','planning_evidence.py'],['공식 사례 조사','research_questions'],['후보·본문 작성','Qwen 비교 / Gemma 작성']];
 flow.forEach((v,i)=>{box(s,v[0],v[1],56+i*299,202,269,120,i===1?C.lime:C.pale);if(i<3)arrow(s,331+i*299,253,18,false,C.lime);});
 text(s,'forecasts',56,381,320,40,27,C.lime,true);text(s,'월별 예측값·단위·기간\nget_ml_forecast로 조회',56,442,345,120,25,C.white);
 text(s,'signals',454,381,320,40,27,C.lime,true);text(s,'기간 합계·평균과 전년 비교\n모델 평가·신뢰도 전달',454,442,348,120,25,C.white);
 text(s,'research_questions',852,381,365,40,27,C.lime,true);text(s,'방문·검색 / 소비 / 숙박·체류\n세 묶음의 공식 조사 질문',852,442,358,120,25,C.white);
 foot(s,'예: 숙박검색과 숙박률의 흐름을 함께 보고 예약·숙박 연계 사례를 조사합니다. 사업 자동 확정 규칙은 아닙니다.',true);
 note(s,'report_orchestrator.orchestrate_strategy_report가 먼저 build_planning_ml_evidence를 호출합니다. 지역 registry에서 pipeline을 찾아 저장 모델을 로드하고 사업 기간에 필요한 월을 재귀 예측합니다. planning_evidence는 forecasts, signals, model_evaluations, research_questions를 만들고 snapshot.ml_analysis에 넣습니다. decision_facts가 집계 신호를 forecast_windows에 복사합니다. CaseStudyAgent는 세 묶음 질문을 RAG 검색어 및 허용된 웹 조사 입력에 반영합니다. 로컬 Agent에서는 local_agent._prefetch_required_evidence가 get_ml_forecast 등을 실행하고 도구 결과를 JSON 또는 무손실 표로 모델 메시지에 붙입니다. Qwen은 이 숫자와 사례를 비교하고 Gemma는 선정 판단을 받아 실행안을 씁니다. 숙박검색과 숙박률 예시는 해석 방법을 보여 주는 조건부 예시이지 실제 성동구의 확정 원인 분석이 아닙니다.',['ai_server/ml/planning_evidence.py','ai_server/app/agents/decision_facts.py','ai_server/app/agents/report_orchestrator.py','ai_server/app/agents/case_study_agent.py','ai_server/app/llm/local_agent.py','ai_server/app/llm/evidence_tools.py']);
}
// 13
{
 const s=slide('유사 지표 지역과 참고 사업을 찾는 방법','04  EVIDENCE & AGENTS');
 columns(s,[['① 관광지표로 비교 지역 탐색','최근 12개월 방문 규모의 로그값\n소비/방문 비율 · 숙박 비율\n평균 숙박일수\n\n표준화 후 유클리드 거리\n가까운 5개 지역 저장'],['② 공식 문서로 사업 연결','같은 시도·타시도·전국 사례 탐색\n운영 방식이 같은 사례 연결\n문서 등급과 source_id로 정렬\n\n예산서만 있는 후보 제외\n선택 조건과 제외 조건 적용']],180);
 rule(s,56,581,1168);
 foot(s,'지리·교통·주민 인구 유사성은 이 거리식에 없습니다. 7개 예측값으로 학습한 사업 추천 모델도 아닙니다.');
 note(s,'지역 peer와 기획 사례 연결은 서로 다른 단계입니다. data_pipeline/tools/build_planning_context.py의 build_peer_rows는 log1p(visitors_12m), spend_per_visitor_krw, overnight_ratio_avg_pct, avg_stay_days 네 값으로 z=(x-평균)/표준편차(ddof=0)를 계산합니다. 표준편차 0은 1로 대체하고 sqrt(sum((z_a-z_b)^2)) 거리로 자신을 뺀 상위 5지역을 저장합니다. 이는 관측 관광지표의 거리이며 감독학습 추천 모델이 아닙니다. 소비/방문 값도 동일 개인의 실제 객단가로 검증되지 않았습니다. case_scope는 같은 시도, 타시도 peer, 전국 운영 원리를 섞어 최대 8개 사례 카드를 구성합니다. case_recommendation.match_cases는 공식 URL과 operating_model이 있는 문서를 사업 방식에 맞추어 연결하고 예산 편성 문서를 제외합니다. 지리·교통·관광자원·인구의 유사성을 증명하는 알고리즘은 현재 없습니다.',['data_pipeline/tools/build_planning_context.py','ai_server/app/nationwide_context_store.py','ai_server/app/case_scope.py','ai_server/app/case_recommendation.py','ai_server/app/case_mechanism.py']);
}
// 14
{
 const s=slide('공식 근거 검색과 출처 추적','04  EVIDENCE & AGENTS');
 table(s,[['근거 경로','실제로 하는 일','현재 범위'],['검수 사례 카드','사업 운영·성과 기간·적용 조건 확인','JSONL 6건'],['공식 문서 RAG','지역·전국 사례 범위 안에서 키워드 검색','페이지 청크 24건 + 요약 3건'],['공식 웹 조사','필요한 공식 URL과 근거 보강','모드·캐시·예산에 따라 실행'],['Chroma 의미 검색','임베딩 검색 코드와 영속 저장 구조','현재 저장 임베딩 0건']],[253,575,340],{h:345,size:22});
 text(s,'source_id + URL + 페이지 + 원문 + 조회 기록',56,575,1168,45,30,C.teal,true);
 note(s,'2026-09-10 로컬 파일과 Chroma 저장소를 읽어 확인한 수량입니다. 6개 사례 카드, 24개 페이지 청크, 3개 요약을 합쳐 서로 다른 공식 문서 33개라고 말하면 안 됩니다. 동일 문서의 여러 페이지가 포함돼 있습니다. OfficialTourismRagStore.search의 local_only 경로는 유료 임베딩 없이 키워드로 검색합니다. Chroma 검색·임베딩 코드는 구현돼 있으나 저장 임베딩은 0개이므로 의미 검색이 운영 중이거나 평가 완료됐다고 발표하지 않습니다. Evidence/CaseStudy의 OpenAI 공식 웹 조사와 문서 검색은 서로 다른 근거 취득 경로입니다. source_id와 chunk_id로 같은 문서 여러 페이지를 보존하고 read_collected_source 조회 여부를 확인합니다. 월별 수치표 전체는 RAG에서 계산하지 않습니다.',['ai_server/app/rag_store.py','data/rag/official_case_studies.jsonl','data/rag/official_reference_chunks.jsonl','data/rag/official_reference_documents.jsonl','ai_server/app/llm/evidence_tools.py']);
}
// 15
{
 const s=slide('5개 Agent가 맡는 고정 작업 흐름','04  EVIDENCE & AGENTS',true);
 box(s,'Evidence','선택 지역의 관측·자원\n공식 근거',56,211,297,111);
 box(s,'CaseStudy','타지역의 운영 방식\n출처·성과 조건',56,375,297,111);
 arrow(s,371,284,37,false,C.lime);arrow(s,371,411,37,false,C.lime);
 box(s,'Transferability','Qwen\n후보 비교·선정',428,282,252,156,C.lime);
 box(s,'Planner','Gemma\n실행 기획안 작성',706,282,244,156);
 box(s,'Reviewer','코드 + Qwen\n통과본 OpenAI 검수',976,282,248,156);
 arrow(s,685,343,16,false,C.lime);arrow(s,955,343,16,false,C.lime);
 text(s,'자료 조사는 병행',56,526,313,40,25,C.white,true);
 text(s,'후보 보완 1회 / 본문 수정 1회 후 재검수',429,526,777,40,26,C.lime,true);
 foot(s,'Agent는 역할·입력·출력 계약을 가진 코드 모듈입니다. 임의로 행동하는 5명의 자율 실행자는 아닙니다.',true);
 note(s,'report_orchestrator.py가 전체 순서를 정합니다. 먼저 로컬 연결과 ML 기간을 확인한 뒤 asyncio.gather로 Evidence와 CaseStudy를 병행합니다. 두 결과를 evidence_pack으로 합쳐 Transferability에 전달하고, 선택 후보를 Planner에 전달합니다. 코드 검사와 Reviewer가 초안을 평가합니다. 필요한 경우 로컬 후보 보완과 본문 재작성 범위를 제한하고 재검수합니다. 로컬 검수 통과본만 기존 정책의 OpenAI 독립 최종 검수를 받습니다. Agent마다 항상 새 API 호출이 일어나는 것은 아니며 근거 캐시와 서버 도구의 재사용 경로가 있습니다. 코드의 Agent 3 같은 과거 주석 번호보다 실제 class와 orchestrator 호출을 기준으로 설명합니다.',['ai_server/app/agents/report_orchestrator.py','ai_server/app/agents/evidence_agent.py','ai_server/app/agents/case_study_agent.py','ai_server/app/agents/transferability_agent.py','ai_server/app/agents/planner_agent.py','ai_server/app/agents/reviewer_agent.py']);
}
// 16
{
 const s=slide('조사 Agent의 입력·도구·결과','04  EVIDENCE & AGENTS');
 table(s,[['계약','EvidenceAgent.collect','CaseStudyAgent.collect'],['역할','선택 지역의 공식 근거 조사 담당자','타지역 사업의 운영 방식 조사관'],['입력','region_code · snapshot · planning_brief','같은 입력 + ML research_questions'],['도구','TourAPI · 공식 문서 RAG · 허용 웹 조사','사례 레지스트리 · RAG · 허용 웹 조사'],['출력','지역 사실 · 관광자원 · source_id · URL','benchmark_cases · 운영 조건 · 성과 범위'],['다음 사용자','근거 묶음으로 결합\n후보 비교·본문 작성에 전달','같은 근거 묶음으로 전달']],[142,513,513],{y:178,h:394,size:21});
 foot(s,'프롬프트: EVIDENCE_RESEARCH_INSTRUCTIONS / CASE_STUDY_RESEARCH_INSTRUCTIONS');
 note(s,'페르소나는 역할을 정하는 시스템 지시문입니다. Evidence는 지역의 공식 관측과 관광자원을 검토하고 CaseStudy는 다른 곳에서 집행한 사업의 운영 방법, 비용, 대상, 성과 정의를 조사합니다. prompts.py에 두 역할의 지시가 있으며 collect가 서버 도구와 Router를 호출합니다. snapshot에는 관측값과 이미 계산한 ml_analysis가 분리돼 있습니다. planning_brief는 사용자 정보이므로 공식 관측값으로 취급하지 않습니다. CaseStudy는 기존 검수 사례를 재사용하고 research_questions로 검색 범위를 좁힙니다. 웹 검색 요약을 즉시 확정 성과로 인정하지 않고 공식 출처·수치 승인 상태를 확인합니다. Open API와 OpenAI API는 이름은 비슷하지만 역할이 다릅니다.',['ai_server/app/agents/evidence_agent.py','ai_server/app/agents/case_study_agent.py','ai_server/app/agents/prompts.py','ai_server/app/agent_learning_guide.py']);
}
// 17
{
 const s=slide('Qwen의 후보 비교와 Gemma의 본문 작성','04  EVIDENCE & AGENTS');
 columns(s,[['Qwen · 관광전략 기획자','TransferabilityAgent.assess\n\n지역 사실 + ML + 공식 사례\n사용자 조건으로 후보 비교\n\ndesign_candidates\nselected_candidate_id\n선정 사유·적용 조건'],['Gemma · 실행안 작성 담당자','PlannerAgent.write\n\n동일 근거 + 선택 후보를 받아\n하나의 실행 기획안 작성\n\n핵심 제안·이용 절차\n실행 단계·측정 계획\n본문과 연결 출처']],180);
 foot(s,'TRANSFERABILITY_SCHEMA와 report_schema로 JSON 형식을 고정하고, 후보·본문 사이의 출처 연결을 검사합니다.');
 note(s,'Qwen3:14b는 근거 묶음을 읽고 후보를 비교합니다. TRANSFERABILITY_SCHEMA에 후보 ID, 유형, 사례 ID, 실행 방식 등이 정의돼 있습니다. 이후 case_recommendation.constrain_decision이 입력 조건과 공식 운영 문서 연결을 다시 제한합니다. Qwen의 fit_score는 모델이 산출한 평가 서술용 점수이며 학습한 성공 확률로 제시하지 않습니다. Gemma4:26b는 _compact_evidence_for_planner가 선택 판단과 필요한 원문을 보존한 입력을 받아 본문 JSON을 씁니다. 수정 시에는 previous_draft와 quality_review_feedback을 같이 넘깁니다. 지원 사업 유형과 검수 사례 풀이 제한돼 있어 비슷한 환급·야간 기획이 반복될 수 있습니다. 다양한 공식 사례 확장과 실제 응답 비교가 후속 과제입니다.',['ai_server/app/agents/transferability_agent.py','ai_server/app/agents/planner_agent.py','ai_server/app/agents/prompts.py','ai_server/app/llm/local_prompts.py','ai_server/app/case_recommendation.py']);
}
// 18
{
 const s=slide('코드 검사와 모델 검토의 역할','04  EVIDENCE & AGENTS');
 columns(s,[['코드 검사','필수 항목·유형·기간\n출처 ID 연결·원문 조회\n예산 산식·목표 계산\n지원 조건·응답 Schema'],['Reviewer 검토','근거와 주장 대조\n사례 적용의 타당성\n실제 이용 절차·역할\n비용·측정 설계의 내용']],183);
 rule(s,56,478,1168);
 text(s,'issues + revision_instruction',56,510,558,42,29,C.teal,true);
 text(s,'Gemma 수정 · Qwen 재검수\n로컬 통과본의 OpenAI 최종 검수',679,504,530,100,27,C.ink,true);
 foot(s,'JSON 성공·검사 통과·파일 저장·사업 타당성은 서로 다른 확인 결과입니다.');
 note(s,'ReviewerAgent.review는 evidence_pack, draft_report, deterministic_precheck를 받습니다. REVIEW_SCHEMA는 approved, overall_score, dimension_scores, severity를 포함한 issues, revision_instruction을 정의합니다. 점수가 높다는 이유만으로 주요 오류를 무시하지 않습니다. 로컬 모드의 Reviewer는 Qwen이고 final_pass=True일 때 OpenAI final_reviewer 경로를 사용합니다. 사실·인과·현장 계약 조건은 단순 문자열 검사로 보증할 수 없습니다. 과거 원주 실험에서 필수 도구 조회와 JSON은 완료했지만 예산 편성 자체를 관광사업으로 제안하거나 타지역 조건을 복사하는 문제가 남았습니다. 이런 실측을 바탕으로 후보 계약·출처 전달·본문 재검수·문서 계산을 보완했습니다.',['ai_server/app/agents/reviewer_agent.py','ai_server/app/agents/report_orchestrator.py','ai_server/app/agents/planning_requirements.py','docs/LOCAL_CANDIDATE_REPLAY_20260908.md']);
}
// 19
{
 const s=slide('프롬프트와 읽기 전용 도구의 결합','04  EVIDENCE & AGENTS');
 box(s,'역할과 규칙','prompts.py / local_prompts.py',56,195,365,115);
 box(s,'요청 안의 근거 도구','EvidenceTools · 고정 함수 목록',457,195,365,115,C.lime);
 box(s,'구조화 응답','JSON Schema / Pydantic',858,195,366,115);
 arrow(s,430,244,20);arrow(s,831,244,20);
 table(s,[['도구 이름','반환하는 근거'],['get_region_metrics / compare_regions','관측값·동일 기간 peer 비교'],['get_ml_forecast','월별 전망·평가·기간 정책'],['get_case_comparison_matrix','공식 사례의 운영 방식과 조건'],['read_collected_source','source_id에 연결된 원문·페이지']],[568,600],{y:355,h:236,size:20});
 foot(s,'모델이 임의 SQL·파일·웹 명령을 실행하지 않습니다. 서버가 허용된 근거를 조회해 메시지로 전달합니다.');
 note(s,'local_agent는 고정된 TOOL_DEFINITIONS만 모델에 제공합니다. 도구 호출도 서버가 수행하며 read_task_section의 path는 파일 경로가 아니라 요청 JSON Pointer입니다. _prefetch_required_evidence가 필수 근거를 먼저 읽고, read_collected_source는 실제 source_id와 모든 관련 페이지 조회를 추적합니다. 수집 목록만 보고 원문을 읽었다고 간주하지 않습니다. LLMRequest는 task, instructions, input_payload, schema, max_output_tokens를 묶고 Router가 Provider를 결정합니다. Qwen과 Gemma의 Ollama 호출은 현재 think=False이며 별도의 fine-tuning을 실행하지 않았습니다. 문맥은 반복 JSON을 무손실 표로 압축하지만 원수치를 잘라내어 근거를 숨기지 않습니다.',['ai_server/app/llm/evidence_tools.py','ai_server/app/llm/local_agent.py','ai_server/app/llm/models.py','ai_server/app/llm/local_prompts.py','ai_server/app/llm/context_tables.py']);
}
// 20
{
 const s=slide('로컬 모델 우선 라우팅과 비용 관리','04  EVIDENCE & AGENTS',true);
 text(s,'LOCAL FIRST',56,178,770,70,53,C.lime,true);
 text(s,'Qwen3:14b',56,292,560,49,33,C.white,true);text(s,'후보 비교 · 설명 · 검토',56,354,560,50,27,C.line);
 text(s,'Gemma4:26b',56,456,560,49,33,C.white,true);text(s,'본문 작성 · 수정',56,518,560,50,27,C.line);
 text(s,'OpenAI API',751,294,442,49,33,C.white,true);
 text(s,'필요한 공식 조사와 최종 검수\n생성 1건당 최대 3회\n로컬 실패 시 자동 유료 전환 차단',751,356,455,165,26,C.line);
 foot(s,'Router의 실제 적용 경로를 agent_trace에 기록합니다. 호출 수 제한은 계정 전체 청구 상한과 다릅니다.',true);
 note(s,'2026-09-10 GET /ai/v1/llm/status의 mode는 local_first이고 Qwen과 Gemma의 Ollama 연결·태그는 active입니다. 이는 이번 발표 작업에서 새 장문 생성의 품질을 확인한 것은 아닙니다. effective_routes 기준으로 Qwen은 transferability와 reviewer, Gemma는 planner와 planner_revision을 담당합니다. OpenAI는 evidence, case_study, final_reviewer 등 허용 경로에 사용합니다. 실제 OpenAI 모델은 환경 설정으로 바뀌므로 발표 본문에 고정 모델명을 단정하지 않습니다. status의 active는 설정 확인과 연결 상태 수준이며 각 유료 모델 호출 성공을 뜻하지 않습니다. local_first 생성의 유료 호출 상한은 3회, student_budget은 최종 검수 1회입니다. 기본 로컬 요청 timeout은 1800초로 충분히 두되 출력·문맥·재시도 예산은 별도입니다. 실제 비용 절감률은 측정하지 않았습니다.',['ai_server/app/llm/router.py','ai_server/app/llm/ollama_provider.py','ai_server/app/llm/openai_provider.py','storage/llm_runtime_config.json']);
}
// 21
{
 const s=slide('ML 기준 전망과 계획 KPI의 계산','05  OUTPUT & VALIDATION');
 table(s,[['구분','수치를 만드는 주체','표현'],['관측값','공식 원자료 / MySQL','이미 확인된 기간의 수치'],['ML 기준 전망','저장 모델 또는 계절 기준선','과거 관광 흐름의 연장'],['목표 KPI','사례를 참고한 코드 규칙 + 사용자 조정','시범 운영을 위한 계획 가정']],[225,531,412],{y:178,h:226,size:22});
 text(s,'월별 방문 목표 = ML 방문 전망 × (1 + 단계별 목표율)',56,447,1168,46,29,C.teal,true);
 text(s,'추가 소비 목표 = 추가 방문 목표 × (ML 소비액 ÷ ML 방문자 수)',56,504,1168,46,27,C.ink,true);
 foot(s,'강진 참고 환급안 기본 목표: 25% × 80% = 최종월 20%. 80%는 계획 가정이며 인구 보정 계수가 아닙니다.');
 note(s,'idea_proposal.target_basis는 강진 환급 연결안의 기본 목표를 최종월 20%로 제안하고 다른 안은 초기 5%를 제안합니다. 사용자가 지정한 목표가 우선합니다. 강진군의회 2024-11-20 시정연설의 10월 말 관광객 약 248만명, 전년 대비 25%를 참고합니다. 248만/1.25=198.4만과 차이49.6만은 역산이며 별도 관측값이 아닙니다. 발표 실적은 반값여행과 축제의 동시기 성과여서 사업 단독 효과나 ML 전망 대비 증가율은 아닙니다. 80%는 단계 운영을 고려한 계획 계수로 통계적으로 학습하거나 인구로 계산하지 않았습니다. 3개월이면 최종율의 1/3,2/3,3/3을 적용합니다. 소비/방문 비율을 추가 방문에 그대로 곱하면 같은 월의 방문·소비 증가율이 같아지는 것이 수학적으로 맞습니다. 이 비율은 동일 개인 표본의 실제 객단가가 아닙니다. 별도 소비 목표를 지정하면 독립 목표율을 사용합니다.',['ai_server/app/idea_proposal.py','ai_server/app/report_projection.py','https://clik.nanet.go.kr/minutes/viewer.do?DOCID=CLIKC3524169218564260&collection=minutes']);
}
// 22
{
 const s=slide('견적 예시의 규모와 금액 산식','05  OUTPUT & VALIDATION');
 text(s,'성동구 3개월 예시',56,176,690,42,29,C.teal,true);
 text(s,'추가 방문 목표 2,635,826 × 시범 담당 비중 1%\n운영 수량 26,359건으로 올림',56,229,1168,85,29,C.ink,true);
 table(s,[['항목','계산 방법','예상 금액'],['여행비 환급 지원','26,359건 × 50,000원','1,317,950,000원'],['운영·정산','1,055인일 × 150,000원','158,250,000원'],['시스템·홍보·집계','800만 + 500만 + 300만원','16,000,000원'],['예비비 / 합계','소계의 10% / 소계 + 예비비','149,220,000 / 1,641,420,000원']],[270,488,410],{y:345,h:252,size:20});
 foot(s,'1%·단가·인일은 계획 가정입니다. 참고 예산을 입력하면 총액 안에서 항목 비중을 재배분합니다.');
 note(s,'예시 숫자는 storage/previews/seongdong_updated_20260910.json의 출력용 검토본에서 가져왔습니다. build_reference_estimate는 사업기간의 목표와 기준 전망 차이 합계를 계산하고 1%의 시범 담당 비중을 적용해 수량을 올림합니다. 운영 인일=max(월20인일×3, ceil(26,359/25))=1,055입니다. 환급 건당5만원, 인일15만원, 기존 시스템 설정800만원, 홍보500만원, 성과집계300만원은 공식 견적서의 관측 단가가 아니라 운영 예산 가정입니다. 1%는 직접 관리할 참여량 배분이며 전환율 예측이 아닙니다. 이 시범 수량이 지역 전체20% 증가를 달성한다는 인과모형은 없습니다. 참고 총액이 입력되면 scale_estimate가 비중 재배분을 하고 수량·단가 확정으로 보이지 않게 분리합니다. 예산은 실제 계약 금액과 다를 수 있습니다.',['ai_server/app/proposal_evidence.py','ai_server/app/idea_proposal.py','storage/previews/seongdong_updated_20260910.json']);
}
// 23
{
 const s=slide('성동구 기획안의 근거와 적용 예시','05  OUTPUT & VALIDATION');
 await picture(s,path.join(ROOT,'storage/previews/seongdong_final_render/슬라이드5.PNG'),56,186,648,378,'성동구 생성 문서의 공식 지역 참고 사례 슬라이드');
 text(s,'공식 사례',757,185,440,42,29,C.teal,true);
 text(s,'강진 반값여행\n지출 증빙 확인 후 지원\n지역 내 혜택 재사용 구조',757,244,448,126,25);
 text(s,'성동구 초안에 적용',757,416,451,42,29,C.teal,true);
 text(s,'참여 상점·대상·지급 조건 설계\n신청·승인·지급·사용 기록으로\n시범 운영 결과 확인',757,473,449,118,24);
 foot(s,'사례의 운영 원리를 가져온 기획 예시입니다. 사진은 해당 사례 또는 명시된 유사 사업 참고 이미지입니다.');
 note(s,'사용자가 실제로 생성한 성동구 보고서를 기반으로 만든 문서 예시입니다. 원본 저장 보고서 ID는 101c9de52d664800986c815fd5b66917입니다. 기존 공식 관측과 ML 전망을 보존하고 승인된 공통 문서 규칙을 적용한 출력용 검토본을 보여 줍니다. 새로운 LLM이 이번 발표를 위해 사업을 다시 설계한 것은 아닙니다. 강진 사례의 사업 운영 방식과 성동구 기획의 실행 방식 연결을 함수로 확인합니다. 성동구와 강진의 지리·인구가 같다는 증명은 없습니다. 상품권 발행과 지급 시점, 참여처 조건은 담당자의 현장 검토가 필요한 실행 요소입니다. 참고 사례 슬라이드에 있는 실제 사진·포스터와 출처 캡션은 생성 문서의 규칙을 유지합니다.',['storage/previews/seongdong_updated_20260910.json','ai_server/app/case_recommendation.py','ai_server/app/proposal_layout_v10.py','ai_server/app/case_images.py']);
}
// 24
{
 const s=slide('같은 보고서 데이터로 만드는 PPTX와 Word','05  OUTPUT & VALIDATION');
 await picture(s,path.join(ROOT,'storage/previews/seongdong_final_render/슬라이드8.PNG'),56,212,729,407,'성동구 출력 문서의 ML 전망과 목표 KPI');
 await picture(s,path.join(ROOT,'storage/previews/seongdong_word_render/checked-1.png'),858,170,366,465,'성동구 Word 기획서 첫 페이지');
 text(s,'PPTX  /  시각 중심의 발표 자료',56,170,743,39,27,C.teal,true);
 foot(s,'prepare_idea_report와 report_projection의 공통 수치·목표·견적을 두 문서에 반영합니다.');
 note(s,'Word와 PowerPoint를 LLM이 각자 임의로 만드는 구조가 아닙니다. 생성 JSON을 prepare_idea_report로 정리하고 report_projection이 사업 기간에 맞는 저장 전망과 목표 시리즈를 선택합니다. proposal_document가 Word를, proposal_presentation_v4 및 연결된 layout 버전이 PPTX를 렌더링합니다. PPT는 3개 참고 사례, 선택 근거, 실행 가이드, ML/KPI, 목표 근거, 견적과 출처를 포함합니다. Word는 상세 실행 내용과 표를 제공합니다. strategy_store는 보고서 입력 지문과 render_version으로 캐시 유효성을 확인하므로 템플릿이 바뀌면 출력도 갱신합니다. 화면은 실제 2026-09-10 검토 출력본에서 가져왔습니다. 보고서 저장 여부와 품질 승인 여부는 분리합니다.',['ai_server/app/idea_proposal.py','ai_server/app/report_projection.py','ai_server/app/proposal_document.py','ai_server/app/proposal_presentation_v4.py','ai_server/app/strategy_store.py']);
}
// 25
{
 const s=slide('챗봇은 현재 기획안의 조정을 지원합니다','05  OUTPUT & VALIDATION');
 columns(s,[['조정할 수 있는 내용','목표 KPI 증가율\n예상 견적 총액\n소개·홍보 문장\n참여 범위와 실행 단계'],['보존하는 근거','공식 관측값\n저장 ML 전망\n공식 사례의 발표 수치\n원래 출처와 검수 기록']],183);
 rule(s,56,473,1168);
 text(s,'“방문 목표 10%로 수정해줘”',56,510,650,47,30,C.teal,true);
 text(s,'허용된 report_patch\n미리보기 적용 후 저장',815,499,409,89,27,C.ink,true);
 foot(s,'신축 빌딩·공원 요청은 범위를 안내하고 실제로 근거가 연결된 후보 목록을 보여 줍니다.');
 note(s,'idea_proposal.bounded_chat_reply가 명시적 수치 수정과 범위 밖 신축 요청을 로컬 규칙으로 우선 처리합니다. 방문 목표는0~20%, 소비 목표는0~30% 범위이며 견적은 현재 계약과 상한을 검사합니다. 숫자 수정에 항상 LLM을 호출할 필요는 없습니다. 나머지 설명·문장 수정은 Qwen/Gemma의 제한된 JSON 경로를 사용합니다. 프런트의 applyReportPatch는 허용된 부분만 반영하며 관측과 ML을 사용자 지시로 바꾸지 않습니다. 현재 연결된 후보 수를 계산해 안내하므로 모든 보고서에 총4개라고 하드코딩하지 않습니다. 기획안 수정이 완료된 후 사용자에게 저장을 요청하고 원래 근거와 변경된 계획 가정을 구분합니다.',['ai_server/app/idea_proposal.py','frontend/src/features/planning/applyReportPatch.js','frontend/src/components/TourismAssistant.jsx','ai_server/app/agents/chat_assistant_agent.py']);
}
// 26
{
 const s=slide('실제 오류를 바탕으로 보완한 부분','05  OUTPUT & VALIDATION');
 table(s,[['발견한 문제','시스템에서 보완한 방법','확인 범위'],['로컬 모델 연결·지연','유료 조사 전 사전 확인 / 넉넉한 로컬 대기','연결 상태와 오류 단계 표시'],['길어진 근거·출처 누락','무손실 표 / 필수 원문 사전 조회 / Schema','수치·ID·페이지 전달 검사'],['예산서 자체를 사업으로 제안','운영 방식 연결 / 예산 문서 후보 제외','후보 계약과 실제 내용 대조'],['지역마다 같은 견적','추가 방문 목표 연동 수량·산식','합계와 가정 여부 검사'],['PPT 줄 넘침·숫자 불일치','공통 계산 / 줄바꿈·표 폭·캡션 높이 조정','실제 PowerPoint·Word 렌더 확인']],[325,539,304],{h:380,size:21});
 foot(s,'관련 문서·목표·견적 회귀 39개와 프런트 lint/build의 기존 통과 기록이 있습니다. 기획 품질 승인의 대체는 아닙니다.');
 note(s,'2026-09-08 원주 실제 Qwen 보완에서는 검사 건수가 감소했어도 이용 절차와 사례 해석 오류가 남아 품질 미달로 기록했습니다. 이를 테스트 통과로 덮지 않았습니다. 2026-09-10에는 공통 문서·견적·목표 수정 관련 선택 회귀39개, 프런트 lint와 production build 통과를 기록했습니다. 이는 해당 변경 범위의 기존 실행 결과이며 이번 발표 제작에서 전체 테스트를 다시 실행했다는 주장은 아닙니다. 실제 생성은 지역·근거·모델응답에 따라 달라지므로 모든89지역의 기획 품질이 검증 완료된 것으로 발표하지 않습니다. 로컬 응답 안정성, 연결, 출처 전달, 수치 계산, 디자인은 서로 다른 검증 대상입니다.',['docs/DECISIONS.md','docs/LOCAL_CANDIDATE_REPLAY_20260908.md','ai_server/test_proposal_evidence.py','ai_server/test_visitor_linked_spending.py','ai_server/test_idea_proposal.py','frontend/package.json']);
}
// 27
{
 const s=slide('개발 실행과 운영 보안','06  DELIVERY & NEXT');
 columns(s,[['현재 개발 환경','start-dev.ps1로 서비스 실행\nReact 5176 / Backend 8100\nAI 8112 / Streamlit 8501\n\n모델 연결과 자료 준비 확인\n관리 화면에서 trace 확인'],['운영 전 점검','서버에서만 API 키 사용\nLLM 설정 변경 관리자 토큰\n허용 도메인·도구·입력 길이 제한\n\nNginx·HTTPS·접근 제어\n백업·로그·사용량·재시작 점검']],180);
 foot(s,'AWS EC2 + Nginx는 배포 설계입니다. 외부 운영 URL의 배포·부하 검증 완료를 주장하지 않습니다.');
 note(s,'프런트에 OpenAI 키나 DB 비밀번호를 보내지 않고 .env에서 서버가 읽습니다. LLM 설정 변경 API는 관리자 토큰을 요구합니다. 제한된 도구와 공식 URL 검사가 있지만 모든 공격이 차단된다는 보안 인증은 아닙니다. 운영 전에는 보고서 API의 접근 통제, 사용자 정보 최소 수집, CORS·HTTPS·환경별 설정, 파일·DB 백업, 작업 재시작과 로그 보관을 점검해야 합니다. 로컬 모델은 노트북의 Ollama 서비스에 연결되며 네트워크와 모델 가동 상태가 필요합니다. 현재 API health가 응답하고 등록 태그가 active인 것은 실행 준비 증거이지 응답 시간 SLA가 아닙니다. start-dev 스크립트를 사용하며 매번 수동으로 다른 임시 포트를 켜는 방식으로 설명하지 않습니다.',['start-dev.ps1','frontend/vite.config.js','backend/app/config.py','ai_server/app/main.py','ai_server/app/llm/router.py','docs/ARCHITECTURE.md']);
}
// 28
{
 const s=slide('구현 결과와 팀의 설명 자료','06  DELIVERY & NEXT');
 text(s,'89',56,189,370,110,75,C.teal,true);text(s,'등록·자료 점검 지역',56,317,370,43,26,C.ink,true);
 text(s,'7',470,189,320,110,75,C.teal,true);text(s,'예측 지표',470,317,320,43,26,C.ink,true);
 text(s,'5',882,189,320,110,75,C.teal,true);text(s,'고정 역할 Agent',882,317,340,43,26,C.ink,true);
 rule(s,56,398,1168);
 text(s,'서비스 산출물',56,438,528,43,29,C.teal,true);text(s,'지역 대시보드 · 기획·저장·챗봇\nPPTX·DOCX · 모델·평가 메타데이터',56,499,579,96,25);
 text(s,'팀 학습·유지보수',686,438,526,43,29,C.teal,true);text(s,'ML·Agent·React 설명 화면\nStreamlit 전체 구조 · API·결정 기록',686,499,539,96,25);
 note(s,'89는 storage/region_readiness_audit.json의2026-09-10 등록지역 점검 기록입니다. 89개 모두 data_ready지만 전체 실생성·품질 승인 완료 지역이라는 수치는 아닙니다. 7은 Target 수이고5는 고정 역할 모듈 수입니다. 저장 기록은 이번 조회8건이었지만 개발 중 계속 바뀌는 값이고 사용자 성과지표가 아니므로 주요 성과 숫자에서 제외했습니다. 관리자 /ml-test는 모델별 feature·평가·호출 경로를 metadata에서 읽고 module_usage.py가 설명을 연결합니다. /openai-test와 /react-test는 Agent와 React 구조 설명을 제공합니다. /project-tree는 Streamlit 전체 구조 탐색기를 연결합니다. 발표 산출물로 코드·설계·ERD·API·모델 평가·프롬프트·문서 출력·시연 흐름을 제시하고 미실행 Fine-tuning 결과를 만들어 넣지 않습니다.',['storage/region_readiness_audit.json','ai_server/ml/module_usage.py','ai_server/app/agent_learning_guide.py','ai_server/app/project_learning_catalog.py','project_tree_explorer/app.py','docs/API_DRAFT.md','docs/DECISIONS.md']);
}
// 29
{
 const s=slide('다음 단계의 검증과 개발 계획','06  DELIVERY & NEXT');
 table(s,[['우선순위','진행할 작업','확인할 결과'],['1 기획 품질','여러 지역·별도 평가 입력으로 실제 생성 비교','이용 절차·사례 연결\n내용의 반복성'],['2 근거 확장','운영 방식이 다양한 공식 사례 확보','유사성 변수·성과 기간·근거 범위'],['3 모델 개선','최신 데이터 반영과 기준선 재비교','동일 기간 오차\n재귀 전망 안정성'],['4 사용자 평가','담당자 검토와 소규모 시범 운영','유용성·수정량·업무 시간\n실제 성과'],['5 운영 배포','Nginx·접근 제어·모니터링·백업','외부 접속·오류 복구·부하·비용']],[238,584,346],{h:382,size:22});
 foot(s,'Fine-tuning은 검토 가능한 후속 선택지입니다. 현재 자체 LLM 학습이나 정책 인과효과 모델은 적용하지 않았습니다.');
 note(s,'현재 구현의 장점과 개선 과제를 구체적으로 연결합니다. 첫째는 검사 건수만이 아니라 실제 응답의 이용 절차와 사례 해석을 여러 지역에서 평가하는 것입니다. 둘째는 지리·접근성·관광자원·사업 강도·예산·성과 정의를 같은 기준으로 비교할 공식 데이터와 다양한 운영 사례를 확보하는 것입니다. 셋째는 시간순 평가와 기준선 비교를 유지하며 새로운 원자료로 모델을 갱신하는 것입니다. 사용자 평가에서는 실제 참여자 수·질문·척도와 수정 시간을 기록해야 합니다. Fine-tuning을 하려면 원자료 PDF만 넣는 것이 아니라 근거·조건 입력과 사람이 검토한 좋은 답변 쌍이 필요하며 아직 실행·설치·비용을 승인받아 적용한 단계가 아닙니다. 교사의26번 항목이 요구한 개발 및 운영 계획, 기대효과, 피드백 반영을 이 페이지에 연결합니다.',['docs/IMPLEMENTATION_PLAN.md','docs/CONTEST_EVIDENCE.md','docs/LOCAL_FIRST_QUALITY_PLAN.md','docs/DATA_AND_AI_RULES.md']);
}
// 30
{
 const s=slide('시연과 질의응답','06  DEMO',true);
 text(s,'OLIGO-K',56,191,800,95,68,C.lime,true);
 text(s,'공식 데이터와 사례로\n관광사업 아이디어를 구체화합니다',56,321,1125,125,40,C.white,true);
 text(s,'시연 순서',56,523,204,43,27,C.lime,true);
 text(s,'지역 현황  /  입력 조건  /  저장 기획안  /  PPTX·Word',286,522,924,48,26,C.white);
 foot(s,'장문 생성 대기 중에는 저장된 성동구 결과와 관리자 ML·Agent 설명 화면을 함께 보여 줍니다.',true);
 note(s,'권장 시연은 약3~4분입니다. 1) /dashboard에서 지역을 선택하고 방문·소비 및 숙박 지표를 확인합니다. 2) /planning에서4종 사업 방향과 참고 예산,3개월 시범,제외 조건을 설명합니다. 3) 새 생성은 모델 연결과 데이터 준비가 확인된 경우만 시작하고 실제 단계가 움직이는 것을 보여 줍니다. 4) 긴 대기 중에는 /saved-plans의 성동구 저장 보고서를 열어 근거·목표·견적을 보여 줍니다. 5) 생성된 PPTX/Word를 열고 ML 기준과 계획 KPI, 출처를 대조합니다. 6) /ml-test 또는 /openai-test의 코드 경로를 보여 줍니다. 연결 장애가 나면 준비된 저장 문서로 시연하고 이를 방금 새로 생성한 결과라고 설명하지 않습니다. 예상 질문: LLM 자체 학습인가? 사전학습 모델을 사용하며 지역 ML만 별도 학습합니다. 유사지역은 어떻게 찾는가? 관측4지표 거리와 공식 운영 문서 매칭입니다. KPI는 예측 효과인가? 목표 가정입니다. 완전 무료인가? 제한된 OpenAI 호출이 있습니다. 품질이 모두 승인됐는가? 기능 구현과 실제 업무 타당성을 분리해 평가 중입니다.',['frontend/src/routes.js','docs/presentation_source.md','ai_server/ml/module_usage.py','ai_server/app/agent_learning_guide.py']);
}

await fs.mkdir(OUT,{recursive:true});
await fs.writeFile(path.join(DIR,'speaker_notes.json'),JSON.stringify(narrative,null,2));
const candidatePath=path.join(DIR,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
console.log('EXPORTED',deck.slides.items.length,candidatePath);
if(process.argv.includes('--finalize')) {
 const result=await finalizePresentation({workspaceDir:ROOT,candidatePath,finalPath:path.join(OUT,'OLIGO-K_최종발표_20260910.pptx'),pythonExecutable:path.join(ROOT,'backend/.venv/Scripts/python.exe'),integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:30,requiredNativeTableOwnerSlides:[6,9,14,16,19,21,22,26,29],requiredNativeChartOwnerSlides:[11],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(DIR,'validation.json')});console.log(JSON.stringify(result));
}
