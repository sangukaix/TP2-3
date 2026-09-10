"""발표용 TP2-3 프로젝트 구조·실행 흐름 탐색기."""

from __future__ import annotations

import html
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys

import streamlit as st

EXPLORER_ROOT = Path(__file__).resolve().parent
if str(EXPLORER_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPLORER_ROOT))

from tree_core import PROJECT_ROOT, build_tree_text, path_role, scan_project  # noqa: E402

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ai_server.ml.module_usage import GUIDES, build_module_usage  # noqa: E402


st.set_page_config(page_title='TP2-3 구조 지도', page_icon='🧭', layout='wide', initial_sidebar_state='collapsed')

st.markdown(
    '''
    <style>
    .stApp { background: #f4f7fa; }
    .block-container { max-width: 1540px; padding: 1.35rem 1.45rem 2.3rem; }
    .map-hero { padding: 1.2rem 1.45rem; border: 1px solid #d9e4ed; border-radius: 14px; background: #fff; }
    .map-hero h1 { margin: 0; color: #193d5d; font-size: 2.05rem; letter-spacing: -.04em; }
    .map-hero p { margin: .55rem 0 0; color: #637889; font-size: 1.06rem; line-height: 1.65; }
    .map-hero b { color: #197d99; }
    .map-caption { margin: .9rem 0 1.15rem; color: #637889; font-size: 1rem; line-height: 1.55; }
    .function-tree { padding: .85rem; border: 1px solid #d7e3eb; border-radius: 12px; background: #fff; }
    .function-tree h3 { margin: 0 0 .35rem; color: #244c68; font-size: 1.15rem; }
    .function-tree p { margin: 0 0 .9rem; color: #718492; font-size: .9rem; line-height: 1.55; }
    .tree-root { margin: .9rem 0 .55rem; color: #6c7d89; font-family: monospace; font-size: .9rem; }
    .tree-row { margin: .22rem 0; padding: .42rem .5rem; border-radius: 6px; color: #597080; font-family: monospace; font-size: .84rem; line-height: 1.45; }
    .tree-row.is-current { color: #0f6985; background: #dff4f8; font-weight: 800; box-shadow: inset 3px 0 #1e9bbb; }
    .tree-path { overflow-wrap: anywhere; }
    .feature-heading { margin: .15rem 0 .55rem; color: #244c68; font-size: 1.1rem; font-weight: 800; }
    .feature-caption { margin: 0 0 .7rem; color: #718492; font-size: .92rem; }
    .flow-panel { padding: 1rem; border: 1px solid #d7e3eb; border-radius: 12px; background: #fff; }
    .flow-panel h2 { margin: 0; color: #244c68; font-size: 1.25rem; }
    .flow-panel > p { margin: .4rem 0 .95rem; color: #718492; font-size: .94rem; line-height: 1.5; }
    .flow-heading { display: flex; align-items: center; justify-content: space-between; gap: .6rem; margin-bottom: .8rem; }
    .flow-heading h2 { margin: 0; }
    .flow-count { flex: 0 0 auto; padding: .22rem .52rem; border-radius: 999px; color: #176d87; background: #e2f5f8; font-size: .88rem; font-weight: 800; }
    .flow-rail { display: grid; gap: .2rem; padding: .35rem .15rem .85rem; }
    .flow-step { min-width: 0; max-width: none; padding: .72rem .8rem; border: 1px solid #d4e2ea; border-radius: 10px; background: #fbfdfe; }
    .flow-step.is-focus { border-color: #1597b7; background: #effbfc; box-shadow: 0 0 0 3px #20a0bb22; }
    .flow-step.is-done { opacity: .72; }
    .flow-step small { color: #1987a2; font-weight: 800; font-size: .75rem; }
    .flow-step b { display: block; margin: .26rem 0; color: #274c65; font-size: .92rem; line-height: 1.35; }
    .flow-step span { display: block; color: #738694; font-size: .76rem; line-height: 1.45; }
    .flow-arrow { display: grid; min-height: 22px; place-items: center; color: #9bb1bd; font-size: 1.35rem; }
    .flow-arrow.is-moving { color: #1597b7; animation: moving-arrow 1.1s ease-in-out infinite; }
    @keyframes moving-arrow { 0%,100% { transform: translateY(0); opacity: .4; } 50% { transform: translateY(5px); opacity: 1; } }
    .stage-card { padding: .9rem 1rem; border-left: 4px solid #1998b7; border-radius: 9px; background: #f6fcfd; }
    .stage-card h3 { margin: 0 0 .65rem; color: #214b67; font-size: 1.18rem; }
    .stage-card p { margin: .55rem 0; color: #536d7d; font-size: .98rem; line-height: 1.6; }
    .stage-card b { color: #315c74; }
    .path-chip { display: inline-block; margin: .15rem 0; padding: .28rem .45rem; border-radius: 5px; color: #176d87; background: #dff3f7; font-family: monospace; font-size: .82rem; overflow-wrap: anywhere; }
    .stage-next { margin-top: .55rem !important; padding-top: .55rem; border-top: 1px solid #d7eaee; }
    .detail-intro { margin: .1rem 0 .75rem; color: #587080; font-size: .95rem; line-height: 1.6; }
    .detail-block { margin: .65rem 0; padding: .72rem .82rem; border-left: 3px solid #9bcfda; border-radius: 0 8px 8px 0; background: #f8fbfc; }
    .detail-block h4 { margin: 0 0 .3rem; color: #244c68; font-size: 1rem; }
    .detail-block p { margin: 0; color: #526d7d; font-size: .96rem; line-height: 1.62; }
    .fit-explainer { margin: .35rem 0 1rem; padding: .9rem; border: 1px solid #cce4e9; border-radius: 10px; background: #f4fbfc; }
    .fit-explainer h4 { margin: 0 0 .3rem; color: #174f68; font-size: 1.07rem; }
    .fit-explainer > p { margin: 0 0 .8rem; color: #526d7d; font-size: .95rem; line-height: 1.55; }
    .fit-diagram { display: grid; grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr); align-items: stretch; gap: .45rem; }
    .fit-node { min-width: 0; padding: .62rem; border: 1px solid #c9e1e7; border-radius: 8px; background: #fff; }
    .fit-node b { display: block; margin-bottom: .28rem; color: #1f5871; font-size: .94rem; }
    .fit-node span { display: block; color: #597280; font-size: .84rem; line-height: 1.48; }
    .fit-node.is-decision { border-color: #55afc2; background: #e4f6f8; }
    .fit-arrow { display: grid; place-items: center; color: #168eac; font-size: 1.25rem; font-weight: 800; }
    .fit-checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; margin-top: .65rem; }
    .fit-check { padding: .58rem .65rem; border-radius: 7px; background: #fff; color: #536d7d; font-size: .87rem; line-height: 1.48; }
    .fit-check b { color: #244c68; }
    .fit-caution { margin: .68rem 0 0 !important; padding: .58rem .65rem; border-radius: 7px; color: #765820 !important; background: #fff6dc; font-size: .9rem !important; }
    @media (max-width: 900px) { .fit-diagram { grid-template-columns: 1fr; } .fit-arrow { transform: rotate(90deg); min-height: 20px; } .fit-checks { grid-template-columns: 1fr; } }
    .tree-help { padding: .85rem 1rem; border-radius: 9px; color: #617887; background: #edf4f7; font-size: .96rem; line-height: 1.6; }
    .folder-browser-title { margin: .85rem 0 .45rem; color: #244c68; font-size: 1.08rem; font-weight: 800; }
    .project-tree { padding: 1rem; border: 1px solid #d7e3eb; border-radius: 12px; background: #fff; }
    .project-tree h3 { margin: 0 0 .3rem; color: #244c68; font-size: 1.15rem; }
    .project-tree p { margin: 0 0 .8rem; color: #718492; font-size: .9rem; line-height: 1.55; }
    .project-tree-root { margin: .2rem 0 .45rem; color: #315c74; font-family: monospace; font-size: .95rem; font-weight: 800; }
    .project-file-row { margin: .15rem 0; padding: .34rem .48rem; border-radius: 6px; color: #597080; font-family: monospace; font-size: .84rem; line-height: 1.45; overflow-wrap: anywhere; }
    .project-file-row.is-current { color: #0f6985; background: #dff4f8; font-weight: 800; box-shadow: inset 3px 0 #1e9bbb; }
    div[data-testid="stColumn"]:has(.sticky-detail), div[data-testid="stColumn"]:has(.sticky-tree) { position: sticky; top: .7rem; align-self: flex-start; }
    div[data-testid="stButton"] button { justify-content: flex-start; border-color: #d6e4eb; color: #385b70; background: #fff; font-size: .95rem; }
    div[data-testid="stButton"] button[kind="primary"] { border-color: #168eac; color: #fff; background: #168eac; }
    /* 설명 밀도를 높이고 제목보다 구조와 계약이 먼저 읽히게 합니다. */
    .stApp { font-size: 14px; }
    .block-container { max-width: 1660px; padding: .8rem 1.15rem 1.6rem; }
    .map-hero { padding: .8rem 1rem; border-radius: 10px; }
    .map-hero h1 { font-size: 1.45rem; letter-spacing: -.025em; }
    .map-hero p { margin-top: .3rem; font-size: .88rem; line-height: 1.5; }
    .map-caption { margin: .45rem 0 .7rem; font-size: .82rem; line-height: 1.45; }
    .feature-heading { margin: .15rem 0 .22rem; font-size: .98rem; }
    .feature-caption { margin-bottom: .45rem; font-size: .8rem; }
    div[data-testid="stButton"] button { min-height: 2.15rem; padding: .35rem .55rem; font-size: .82rem; }
    div[data-testid="stTabs"] button[role="tab"] { font-size: .84rem; font-weight: 750; }
    .system-overview { margin: 0 0 .7rem; padding: .72rem .82rem; border: 1px solid #d6e3ea; border-radius: 10px; background: #fff; }
    .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-bottom: .55rem; }
    .section-head h2 { margin: 0; color: #244c68; font-size: 1rem; }
    .section-head p { margin: 0; color: #758894; font-size: .75rem; }
    .system-flow { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .55rem; }
    .system-node { position: relative; min-width: 0; padding: .62rem .68rem; border: 1px solid #d7e3ea; border-radius: 8px; background: #f9fbfc; }
    .system-node:not(:last-child)::after { content: '›'; position: absolute; z-index: 2; top: 50%; right: -.43rem; width: .3rem; color: #18a0bc; font-size: 1.2rem; font-weight: 900; transform: translateY(-55%); }
    .system-node small { display: block; color: #16839e; font-size: .67rem; font-weight: 800; letter-spacing: .04em; }
    .system-node b { display: block; margin: .16rem 0 .22rem; color: #234a64; font-size: .83rem; }
    .system-node span { display: block; color: #607786; font-size: .74rem; line-height: 1.42; }
    .system-rule { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: .4rem; margin-top: .5rem; }
    .system-rule div { padding: .38rem .48rem; border-radius: 6px; background: #eef6f8; color: #557080; font-size: .7rem; line-height: 1.35; }
    .system-rule b { color: #24526a; }
    .flow-panel { padding: .72rem; border-radius: 9px; }
    .flow-panel h2 { font-size: .98rem; }
    .flow-heading { margin-bottom: .45rem; }
    .flow-count { font-size: .72rem; }
    .flow-rail { gap: .08rem; padding: .2rem 0 .45rem; }
    .flow-step { padding: .48rem .58rem; border-radius: 7px; }
    .flow-step small { font-size: .64rem; }
    .flow-step b { margin: .12rem 0; font-size: .78rem; }
    .flow-step span { font-size: .66rem; line-height: 1.35; }
    .flow-arrow { min-height: 15px; font-size: .95rem; }
    .stage-contract { padding: .76rem .82rem; border: 1px solid #cfe1e8; border-radius: 10px; background: #fff; }
    .stage-contract-header { display: flex; align-items: center; gap: .5rem; margin-bottom: .52rem; }
    .stage-number { flex: 0 0 auto; padding: .2rem .42rem; border-radius: 5px; color: #fff; background: #168eac; font-size: .68rem; font-weight: 850; }
    .stage-contract h2 { margin: 0; color: #214b67; font-size: 1.03rem; }
    .contract-flow { display: grid; grid-template-columns: minmax(0,1fr) 20px minmax(0,1.15fr) 20px minmax(0,1fr); align-items: stretch; }
    .contract-node { min-width: 0; padding: .55rem .62rem; border-radius: 7px; background: #f5f9fb; }
    .contract-node.is-code { background: #eaf7f9; }
    .contract-node small { display: block; margin-bottom: .2rem; color: #17839d; font-size: .65rem; font-weight: 850; }
    .contract-node b { display: block; color: #294f68; font-size: .77rem; line-height: 1.4; }
    .contract-node span { display: block; margin-top: .2rem; color: #667c89; font-size: .72rem; line-height: 1.4; overflow-wrap: anywhere; }
    .contract-arrow { display: grid; place-items: center; color: #1b9bb6; font-weight: 900; }
    .processing-note { margin: .48rem 0 0; color: #526f7f; font-size: .76rem; line-height: 1.45; }
    .processing-note b { color: #28556e; }
    code { padding: .08rem .25rem; border-radius: 4px; color: #176c84; background: #eaf4f7; font-size: .88em; overflow-wrap: anywhere; }
    .detail-title { margin: .72rem 0 .3rem; color: #244c68; font-size: .9rem; font-weight: 820; }
    .detail-intro { margin: 0 0 .48rem; padding: .45rem .55rem; border-radius: 6px; background: #eef4f7; font-size: .76rem; line-height: 1.46; }
    .detail-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .46rem; }
    .detail-block { margin: 0; padding: .56rem .62rem; border-left-width: 2px; border-radius: 6px; }
    .detail-block h4 { margin-bottom: .2rem; font-size: .76rem; }
    .detail-block p { font-size: .76rem; line-height: 1.52; }
    .function-tree { padding: .68rem; border-radius: 9px; }
    .function-tree h3 { font-size: .88rem; }
    .function-tree p { margin-bottom: .55rem; font-size: .7rem; }
    .tree-root { margin: .5rem 0 .3rem; font-size: .74rem; }
    .tree-row { margin: .1rem 0; padding: .3rem .38rem; font-size: .68rem; line-height: 1.35; }
    .fit-explainer { margin: .55rem 0; padding: .65rem; }
    .fit-explainer h4 { font-size: .84rem; }
    .fit-explainer > p { margin-bottom: .55rem; font-size: .72rem; line-height: 1.45; }
    .fit-node { padding: .48rem; }
    .fit-node b { font-size: .72rem; }
    .fit-node span, .fit-check { font-size: .68rem; }
    .fit-caution { font-size: .7rem !important; }
    .tree-help { padding: .58rem .68rem; font-size: .76rem; }
    .project-tree h3 { font-size: .95rem; }
    .project-tree p { font-size: .76rem; }
    .project-file-row { font-size: .72rem; }
    @media (max-width: 1050px) {
      .system-flow { grid-template-columns: 1fr 1fr; }
      .system-node::after { display: none; }
      .system-rule { grid-template-columns: 1fr 1fr; }
      .contract-flow { grid-template-columns: 1fr; gap: .3rem; }
      .contract-arrow { transform: rotate(90deg); min-height: 12px; }
      .detail-grid { grid-template-columns: 1fr; }
    }
    </style>
    ''',
    unsafe_allow_html=True,
)


FLOW_DEFINITIONS = {
    '지역 대시보드 보기': [
        ('01', '지역을 선택', '사용자가 시도·시군구를 고르고 지표를 보려 합니다.', 'frontend/src/pages/TourismDashboardPage.jsx', '선택한 지역 코드와 화면 상태를 준비합니다.', 'API 요청으로 이동'),
        ('02', '요청을 보냄', '브라우저가 지역별 지표·지도·전망을 요청합니다.', 'frontend/src/api/dashboardApi.js', 'React의 요청 함수를 통해 두 FastAPI 서버로 연결합니다.', 'Backend와 AI Server가 응답'),
        ('03', '일반 데이터를 처리', '지도의 경계·기본 업무 데이터를 준비합니다.', 'backend/app/main.py', '일반 Backend가 REST API를 제공합니다.', 'AI 분석 결과 조회'),
        ('04', '분석 결과를 조회', '관측 지표와 저장 모델 기반 전망을 가져옵니다.', 'ai_server/app/main.py', 'AI Server가 ML·데이터 서비스를 조합합니다.', '대시보드 화면 갱신'),
        ('05', '화면에 표시', '사용자가 지도·카드·월별 차트를 확인합니다.', 'frontend/src/pages/TourismDashboardPage.jsx', '받은 응답을 다시 시각화합니다.', '완료'),
    ],
    '기획서 생성': [
        ('01', '사업 조건 입력', '사용자가 예산·기간·자원·제약을 입력한 뒤 “기획안 생성”을 누릅니다.', 'frontend/src/pages/TourismPlanningPage.jsx', '화면이 입력값과 지역 코드로 생성 요청을 준비합니다.', '생성 요청 등록'),
        ('02', '생성 요청 등록', '브라우저가 오래 걸리는 AI 작업을 백그라운드 작업으로 요청합니다.', 'frontend/src/api/dashboardApi.js', '요청 함수가 기획서 Job 생성 API와 상태 조회 API를 호출합니다.', 'AI Server 진입'),
        ('03', 'Job을 시작', 'AI Server가 작업 번호를 만들고 생성 과정을 시작합니다.', 'ai_server/app/main.py', 'FastAPI가 최신 데이터 여부를 확인하고 백그라운드 작업을 등록합니다.', '근거 수집 시작'),
        ('04', '병렬 조사 시작', '근거 조사와 공식 사례 조사를 동시에 시작합니다.', 'ai_server/app/agents/report_orchestrator.py', '오케스트레이터가 두 Agent를 병렬 실행하고 결과를 하나의 근거 팩으로 합칩니다.', '근거·사례 결과 결합'),
        ('05', '지역 근거 수집', '선택 지역의 관측값·전망·공식 문서 근거를 모읍니다.', 'ai_server/app/agents/evidence_agent.py', 'Evidence Agent가 기획에 쓸 수 있는 검증된 근거를 준비합니다.', '공식 사례 결과와 결합'),
        ('06', '공식 사례 조사', '비슷한 관광사업의 운영 방식과 적용 조건을 찾습니다.', 'ai_server/app/agents/case_study_agent.py', 'Case Scout Agent가 공식 사례만 조사합니다.', '지역 적합성 판단'),
        ('07', '지역 적합성 판단', '사례를 지금 선택한 지역에서 쓸 수 있는지 비교합니다.', 'ai_server/app/agents/transferability_agent.py', 'Transferability Agent가 적용·제외 조건을 정리합니다.', '기획안 작성'),
        ('08', '기획안 작성', '근거와 조건을 바탕으로 실행 가능한 기획안을 만듭니다.', 'ai_server/app/agents/planner_agent.py', 'Planner Agent가 구조화된 기획안 JSON을 작성합니다.', '품질 검수'),
        ('09', '품질 검수', '출처·수치·기간·실행 가능성을 독립적으로 확인합니다.', 'ai_server/app/agents/reviewer_agent.py', 'Reviewer Agent가 근거 없는 내용과 오류를 걸러냅니다.', '결과 저장·표시'),
        ('10', '결과 저장·표시', '완성된 기획서를 화면에서 보고 저장·문서 출력합니다.', 'frontend/src/pages/TourismStrategyPage.jsx', '작업 결과를 받아 기획서 화면과 Word·PPT 출력으로 연결합니다.', '완료'),
    ],
    '기획서 수정·출력': [
        ('01', '기획서 열기', '생성된 기획서를 화면에서 검토합니다.', 'frontend/src/pages/TourismStrategyPage.jsx', '저장된 기획안과 검수 상태를 화면에 표시합니다.', '저장 또는 출력 요청'),
        ('02', '저장·출력 요청', '사용자가 저장하거나 Word·PowerPoint 출력을 누릅니다.', 'frontend/src/api/dashboardApi.js', '보고서 저장·문서 다운로드 API를 호출합니다.', 'AI Server 처리'),
        ('03', '보고서·문서 처리', 'AI Server가 MySQL의 기획서를 읽고 문서를 렌더링합니다.', 'ai_server/app/main.py', '저장소와 문서 생성기를 연결해 결과 파일을 반환합니다.', '사용자 다운로드'),
        ('04', '문서 사용', '사용자가 최종 기획안을 내려받아 발표·업무에 사용합니다.', 'frontend/src/pages/TourismStrategyPage.jsx', '화면이 다운로드 상태를 알려 줍니다.', '완료'),
    ],
    'AI 챗봇 질문': [
        ('01', '질문 입력', '사용자가 지역 또는 기획서 화면에서 질문합니다.', 'frontend/src/components/TourismAssistant.jsx', '현재 화면의 지역·기획서 맥락을 함께 준비합니다.', 'API 요청'),
        ('02', '대화 요청', '브라우저가 질문과 화면 맥락을 AI Server에 보냅니다.', 'frontend/src/api/dashboardApi.js', '요청 함수를 통해 안전한 서버 API를 호출합니다.', '허용 근거 구성'),
        ('03', '근거 맥락 구성', '답변에 사용할 검증된 snapshot과 출처만 묶습니다.', 'ai_server/app/llm/chat_context.py', '임의 DB·파일이 아닌 허용된 읽기 전용 근거를 사용합니다.', '응답 생성'),
        ('04', '답변 생성', '설명·조사·수정 제안 중 질문 유형에 맞춰 응답합니다.', 'ai_server/app/agents/chat_assistant_agent.py', '구조화된 답변과 출처를 만듭니다.', '화면 반영'),
        ('05', '답변과 출처 표시', '사용자가 답변을 확인하고 수정안 적용 여부를 결정합니다.', 'frontend/src/components/WorkspaceAssistantPanel.jsx', '자동 변경 없이 사용자가 최종 적용을 선택합니다.', '완료'),
    ],
    '관리자 구조 탭': [
        ('01', '마지막 탭 선택', '관리자 학습 메뉴의 마지막 “전체 구조” 탭을 누릅니다.', 'frontend/src/pages/MlTest/LearningSectionNav.jsx', '탭이 /project-tree 주소로 이동합니다.', 'React 라우팅'),
        ('02', '탐색기 페이지 표시', 'React가 Streamlit 탐색기를 담는 페이지를 보여 줍니다.', 'frontend/src/pages/ProjectTreePage.jsx', 'iframe으로 읽기 전용 구조 지도를 표시합니다.', '구조 지도 탐색'),
        ('03', '기능 흐름 탐색', '발표자가 기능을 누르고 파일 이동 순서를 따라갑니다.', 'project_tree_explorer/app.py', '현재 프로젝트를 읽기만 하여 트리·화살표·설명을 만듭니다.', '완료'),
    ],
}


# 화면에 코드를 노출하지 않으면서도 발표자가 실제 호출·입출력·책임 경계를 설명할 수 있게,
# 현재 구현에서 확인한 함수와 HTTP 계약을 단계별로 정리합니다.
STAGE_DETAILS = {
    '지역 대시보드 보기:01': ('핵심 함수', '`useWorkspaceRegionData()`와 `chooseRegion()`이 선택 지역 코드를 공통 작업공간 상태에 반영합니다.', '전달 데이터', '선택한 `region_code`와 `region_name`입니다. 지역 선택 자체는 서버 저장이 아니라 현재 브라우저 작업공간 상태를 바꿉니다.', '다음 결과', '페이지가 지역 코드별 대시보드·지도·전망 요청을 다시 시작합니다.'),
    '지역 대시보드 보기:02': ('핵심 함수', '`getAiRegionDashboard(regionCode, regionName)`가 `/ai/v1/demo/{regionCode}/dashboard?region_name=…`에 GET 요청을 보냅니다. 지도에는 `getSidoBoundaries()`·`getSigunguBoundaries()`가 별도 GET 요청을 보냅니다.', '전달 데이터', 'URL 경로에는 지역 코드, query string에는 지역명이 들어갑니다. 요청 본문이나 OpenAI 키는 브라우저에 없습니다.', '다음 결과', '지표 카드·월별 추세·예측·지도 경계에 필요한 JSON이 각각 돌아옵니다.'),
    '지역 대시보드 보기:03': ('핵심 함수', 'Backend의 FastAPI route가 행정구역 GeoJSON 경계와 일반 REST 응답을 제공합니다.', '전달 데이터', '시도 코드 또는 시군구 코드만 받아 해당 경계 데이터를 돌려줍니다.', '다음 결과', '프런트엔드는 지도 레이어를 만들고, AI Server 응답은 분석 카드에 사용됩니다.'),
    '지역 대시보드 보기:04': ('핵심 함수', '`read_region_dashboard()`가 `build_region_dashboard()` 또는 등록된 지역의 저장 ML 모델 경로를 사용합니다.', '전달 데이터', '지역 코드·지역명으로 실제 월별 관측 자료와 저장된 Joblib 모델을 찾습니다.', '다음 결과', '최신 관측월, 전월 비교, 월별 추세, 다음 달 예측을 담은 `DashboardResponse`를 반환합니다.'),
    '지역 대시보드 보기:05': ('핵심 함수', '`TourismDashboardPage`의 상태 갱신과 차트·지도 컴포넌트 렌더링입니다.', '전달 데이터', '서버 JSON을 React state에 보관합니다. 수치를 브라우저에서 다시 계산하거나 AI로 만들지 않습니다.', '다음 결과', '사용자는 같은 지역의 지도·핵심 지표·추세·예측을 한 화면에서 확인합니다.'),
    '기획서 생성:01': ('핵심 함수', '`PlanningForm.generate()`가 `validatePlanningBrief()`와 `savePlanningDraft()`를 먼저 실행합니다.', '전달 데이터', '지역명과 `planning_brief`를 준비합니다. brief에는 KPI 2개, 예산 범위·상한, 일정, 시설·인력, 제약, 현장 맥락·선호, 참고문서 텍스트(최대 3개)가 들어갈 수 있습니다.', '사전 확인', '`getStrategyGenerationReadiness()`로 마지막 확정 관측월과 ML 재학습 필요 여부를 확인합니다. 최신성이 불충분하면 생성 버튼이 막힙니다.', '다음 결과', '검증된 조건만 `startAiStrategyReportJob()`으로 전달하고, 성공 시 작업 ID를 브라우저에 저장한 뒤 `/strategy`로 이동합니다.'),
    '기획서 생성:02': ('핵심 함수', '`startAiStrategyReportJob(regionCode, options)`와 이후 상태 조회용 `getAiStrategyReportJob(regionCode, jobId)`입니다.', 'API 요청', '`POST /ai/v1/demo/{region_code}/strategy-report/jobs`에 JSON `{ region_name, planning_brief }`를 보냅니다. `Content-Type`은 `application/json`입니다.', '중요한 경계', '첨부 파일 원본은 보내지 않습니다. 앞 단계의 `uploadPlanningReference()`가 2MB 이하 자료에서 추출한 텍스트만 brief에 들어갑니다.', '다음 결과', '서버는 HTTP 202와 `job_id`, 지역, 상태, 메시지를 즉시 돌려주고, 프런트는 화면 이동 뒤 이 ID로 진행 상태를 조회합니다.'),
    '기획서 생성:03': ('핵심 함수', 'FastAPI의 `start_region_strategy_report_job()`이 `build_region_snapshot()`과 `_raise_if_strategy_generation_is_stale()`를 호출합니다.', '서버 처리', '지역 코드와 brief의 지역 코드가 같은지 검사하고, 실제 원자료 snapshot을 만든 뒤 UUID 작업 ID를 생성합니다.', '저장 방식', '`save_strategy_job()`에는 재시작용 조건만 저장합니다. 참고문서 본문은 제거하고 “첨부가 있었음”만 남깁니다.', '다음 결과', '`asyncio.create_task(_run_strategy_report_job(...))`로 긴 작업을 HTTP 요청과 분리합니다. 그래서 사용자가 화면을 옮겨도 작업은 서버에서 계속됩니다.'),
    '기획서 생성:04': ('핵심 함수', '`orchestrate_strategy_report()`가 `build_planning_ml_evidence()`를 실행한 뒤 `EvidenceAgent`와 `CaseStudyAgent`를 `asyncio.gather()`로 병렬 실행합니다.', '입력 데이터', '지역 snapshot에는 관측 월별 값·지역명·기간이 있고, ML evidence에는 저장 모델의 전망·전망 기간 정책이 더해집니다.', '정확한 동작', 'Evidence Agent는 공식 관측·허용 문서 근거를 수집하고, Case Scout는 `official_case_studies.jsonl` 및 허용 공식 출처에서 사례를 수집합니다. 캐시가 유효하면 재사용합니다.', '다음 결과', '근거 팩에 snapshot, ML 분석, 공식 출처 목록, 사례 카드, 조사 공백을 모아 적합성 판단으로 전달합니다.'),
    '기획서 생성:05': ('핵심 함수', '`EvidenceAgent`와 오케스트레이터의 `_collect_evidence()`입니다.', '입력 데이터', '지역 snapshot, ML 전망, 사용자가 적은 사업 조건을 받습니다.', '정확한 동작', '공식 관측·허용 문서 근거를 수집하고, 재사용 가능한 결과는 캐시에서 읽을 수 있습니다. 이 단계는 사례 조사와 동시에 실행됩니다.', '다음 결과', '공식 수치·문서 출처·조사 공백을 근거 팩에 넣어 사례 결과와 결합합니다.'),
    '기획서 생성:06': ('핵심 함수', '`CaseStudyAgent.collect()`와 오케스트레이터의 `_collect_case_studies()`입니다.', '입력 데이터', '지역 snapshot과 사용자가 적은 사업 조건을 받아 필요한 사례 유형과 조사 관점을 정합니다.', '정확한 동작', '검수된 사례 카드부터 읽고, 근거가 부족할 때만 허용 도메인에서 보강 조사를 시도합니다. 일반 웹 크롤링은 사용하지 않습니다.', '다음 결과', '사례별 source ID, 운영 방식, 적용 조건, 출처 URL을 `benchmark_cases`로 근거 팩에 합칩니다.'),
    '기획서 생성:07': ('핵심 함수', '`TransferabilityAgent.assess(evidence_pack=…)`입니다. 이 함수는 수치 예측을 새로 계산하지 않고, 앞 단계에서 확정된 근거를 “선택 지역에서 시험 가능한 사업 후보”로 비교합니다.', '입력 데이터', '`evidence_pack`에는 `region_code`·지역명·분석 기간, 실제 월별 snapshot, ML 분석, 사용자가 입력한 예산·기간·인력·제약, `benchmark_cases`, 공식 `sources`, 조사 공백(`research_gaps`)이 들어갑니다. 사례 카드에는 source ID·운영 방식·대상·기간·성과 정의·위험·URL이 보존됩니다.', '사례를 보는 순서', 'Case Scout가 이미 선택 지역 → 같은 시도 → 타시도 유사 지역 → 전국 운영 원리 순으로 후보를 구성합니다. 다만 같은 시도 사례만 보지 않고 타시도·전국 사례도 함께 비교해 특정 지역의 사례가 과도하게 유리해지는 것을 막습니다.', 'LLM의 구조화 출력', '모델은 자유 형식 글이 아니라 최대 3개의 `design_candidates`, 사례별 `fit_score`·`evidence_score`·적용 방법·제외 위험·검증 계획, 선택 후보 ID, `ready` 또는 `needs_evidence`, 그리고 시범사업 요약을 정해진 JSON 스키마로 반환합니다.', '검증 규칙', '후보가 2개 미만이거나 작동 원리가 같음, 선택 지역 지표 source ID가 없음, 존재하지 않는 사례 ID 인용, 타지역 사업 범위를 그대로 복사, 수량×단가 없는 예산, 기준기간·원자료·비교집단이 빠진 측정 계획은 코드 검증에서 오류가 됩니다.', '판단 결과', '`ready`는 “효과가 보장됐다”가 아니라, 현재 근거로 조건부 시범사업 초안을 쓸 수 있다는 뜻입니다. `needs_evidence`면 무엇을 추가 확인해야 하는지 남기며, 필요한 경우 사례 보강 후 한 번 재검토합니다.', '다음 결과', '후보 검증을 통과해야 Planner가 시작합니다. 보완 뒤에도 위 계약을 통과하지 못하면 Planner와 유료 검수는 시작하지 않고 오류로 끝나므로, 근거 없는 기획서 본문을 만들지 않습니다.'),
    '기획서 생성:08': ('핵심 함수', '`PlannerAgent.write(evidence_pack)`입니다.', '입력 데이터', '검증된 근거 팩과 적합성 판단을 받으며, 후보 선정 JSON은 Planner가 마음대로 바꾸지 못합니다.', '정확한 동작', '선택된 사업의 문제·해결 방법·예산 기준·KPI·3~6개월 실행 단계·기대 효과를 보고서 스키마에 맞춘 구조화 JSON으로 작성합니다.', '다음 결과', '초안은 결정적 사전 점검(`build_plan_quality_precheck`)과 Reviewer Agent로 넘어갑니다.'),
    '기획서 생성:09': ('핵심 함수', '`ReviewerAgent.review()`와 `merge_quality_precheck()`입니다.', '입력 데이터', '근거 팩, Planner 초안, 수치·출처·필수 항목을 확인하는 결정적 사전 점검 결과를 받습니다.', '정확한 동작', '승인되지 않으면 Planner에 1회 수정 피드백을 주고 재검수합니다. 검수 연결이 실패해도 초안을 “승인됨”으로 바꾸지 않습니다.', '다음 결과', '검수 상태·이슈·점수·trace가 포함된 보고서가 Job 완료 처리와 저장 단계로 전달됩니다.'),
    '기획서 생성:10': ('핵심 함수', '`_persist_completed_strategy_report()`가 `save_strategy_report()`, `save_strategy_measurement_baseline()`, `write_document()`를 호출합니다.', '저장 데이터', '구조화 기획안은 MySQL에, 생성 당시 실제 관측 기준값은 성과 측정용으로 별도 저장합니다. Word와 PPT는 서버 문서 저장소에 준비합니다.', '화면 처리', '`TourismStrategyPage`는 저장한 `job_id`로 `getAiStrategyReportJob()`을 반복 조회해 완료 보고서·검수 상태를 표시합니다.', '다음 결과', '사용자는 기획안을 검토·저장하고 이미 준비된 Word/PPT를 내려받을 수 있습니다.'),
    '기획서 수정·출력:01': ('핵심 함수', '`getStoredStrategyReport(reportId)`와 전략 화면의 상태 복원 로직입니다.', '전달 데이터', 'URL 또는 브라우저에 남아 있는 `report_id`·`job_id`와 지역 코드를 사용합니다.', '다음 결과', 'MySQL의 구조화 기획안, 검수 상태, 저장 메시지를 읽어 화면에 표시합니다.'),
    '기획서 수정·출력:02': ('핵심 함수', '수정 저장은 `saveStoredStrategyReport()`, 다운로드는 `downloadStoredStrategyDocument()`입니다.', 'API 요청', '저장은 `PUT /ai/v1/strategy-reports/{reportId}?region_code=…`에 수정된 보고서 JSON을 보냅니다. 출력은 `GET /documents/docx` 또는 `/documents/pptx`로 Blob을 받습니다.', '다음 결과', '사용자가 명시적으로 저장한 수정만 MySQL 원문에 반영되고, 파일은 브라우저 다운로드로 전달됩니다.'),
    '기획서 수정·출력:03': ('핵심 함수', '`update_saved_strategy_report()`·`download_saved_strategy_document()`·`_render_strategy_document()`입니다.', '서버 처리', '문서가 이미 있으면 `read_document()`로 재사용하고, 없을 때만 `create_strategy_proposal_document()` 또는 `create_strategy_proposal_presentation()`을 실행합니다.', '다음 결과', 'FastAPI가 적절한 MIME type과 attachment 파일명으로 Word/PPT bytes를 StreamingResponse로 반환합니다.'),
    '기획서 수정·출력:04': ('핵심 함수', '브라우저의 Blob 다운로드 처리와 전략 화면의 다운로드 상태 표시입니다.', '다음 결과', '사용자는 원문을 저장한 뒤 문서 파일을 내려받습니다. 브라우저가 파일을 자동으로 공용 RAG·ML 학습 자료에 넣지는 않습니다.'),
    'AI 챗봇 질문:01': ('핵심 함수', '`TourismAssistant`의 메시지 입력 처리입니다.', '전달 데이터', '질문 문자열, 선택 지역의 코드·이름, 현재 기획서 및 대화 이력을 준비합니다. 질문은 서버 스키마의 최대 길이 제한을 따릅니다.', '다음 결과', '입력 내용이 `chatWithTourismAssistant()` 호출로 넘어갑니다.'),
    'AI 챗봇 질문:02': ('핵심 함수', '`chatWithTourismAssistant(regionCode, options)`입니다.', 'API 요청', '`POST /ai/v1/demo/{region_code}/assistant-chat`에 `application/json`으로 질문·지역명·현재 기획서 맥락을 보냅니다.', '보안 경계', '브라우저는 OpenAI 키·DB 비밀번호를 갖지 않으며, API 오류는 서버의 안전한 메시지로만 표시합니다.'),
    'AI 챗봇 질문:03': ('핵심 함수', '`pack_report()`·`revision_report()`·`unpack_report()`입니다.', '정확한 동작', '현재 기획안을 대화에 필요한 제한된 형태로 포장하고, 검증된 snapshot과 허용 근거만 챗봇 컨텍스트에 넣습니다.', '다음 결과', '챗봇은 임의 DB·파일을 읽지 않고 준비된 컨텍스트만 근거로 답변을 만듭니다.'),
    'AI 챗봇 질문:04': ('핵심 함수', 'FastAPI의 `chat_with_tourism_assistant()`와 `chat_assistant_agent`입니다.', '정확한 동작', '질문 유형에 따라 설명·조사·수정 제안을 구조화해 만들고, 답변에 사용한 출처를 함께 반환합니다.', '다음 결과', '자동 저장이 아닌 “적용 가능한 수정안”과 답변을 화면에 보냅니다.'),
    'AI 챗봇 질문:05': ('핵심 함수', '`WorkspaceAssistantPanel`과 전략 화면의 적용 버튼입니다.', '다음 결과', '사용자는 답변·출처·수정 제안을 보고 적용 여부를 결정합니다. 사용자가 저장을 누르기 전에는 MySQL 원문이 바뀌지 않습니다.'),
    '관리자 구조 탭:01': ('핵심 함수', '`LearningSectionNav`의 링크 렌더링입니다.', '전달 데이터', '마지막 탭은 `/project-tree` 경로를 가리킵니다.', '다음 결과', 'React App의 라우팅 조건이 구조 지도 페이지를 선택합니다.'),
    '관리자 구조 탭:02': ('핵심 함수', '`ProjectTreePage`가 iframe `src`를 `VITE_PROJECT_TREE_URL` 또는 현재 React와 같은 호스트의 `8501` 포트로 설정합니다.', '다음 결과', 'React 페이지 안에 읽기 전용 Streamlit 구조 지도가 표시됩니다. LAN 접속에서도 개발 PC의 탐색기를 가리킵니다.'),
    '관리자 구조 탭:03': ('핵심 함수', '`scan_project()`와 `build_tree_text()`입니다.', '정확한 동작', '프로젝트 파일을 읽기만 하고, 기본적으로 `node_modules`·가상환경·캐시·빌드 결과는 접습니다. `.env`와 API 키 내용은 표시하지 않습니다.', '다음 결과', '기능별 단계와 실제 파일 위치를 발표자가 안전하게 탐색할 수 있습니다.'),
}


# 기존 단계·본문·현재 파일 트리 레이아웃에 ML 설명 데이터만 연결합니다.
_ml_guides = {key: build_module_usage(key) for key in GUIDES}
_ml_steps = _ml_guides['visitors']['steps']
FLOW_DEFINITIONS['ML 결과 → 전략'] = [
    (f'{index + 1:02d}', step['title'],
     '공식 월별 지표 7개를 입력합니다.' if index == 0 else _ml_steps[index - 1]['output'],
     step['file'], step['detail'], step['output'])
    for index, step in enumerate(_ml_steps)
]
for _index, _step in enumerate(_ml_steps):
    _detail = ['핵심 함수', f"`{_step['function']}`", '실제 처리', _step['detail'],
               '전달 결과', f"`{_step['output']}`"]
    if _index in {1, 3, 6}:
        for _key, _guide in _ml_guides.items():
            _detail.extend([f"{_guide['role']} · {_key}", _guide['steps'][_index]['detail']])
    if _index == 4:
        for _key, _guide in _ml_guides.items():
            _detail.extend([f"{_guide['role']} → {_guide['research_group']}", _guide['interpretation']])
    if _index == 5:
        for _key, _guide in _ml_guides.items():
            _detail.extend([f"{_guide['role']} · 조건부 해석 예시", _guide['example']])
    _detail.extend(['해석 범위', _ml_guides['visitors']['limit']])
    STAGE_DETAILS[f'ML 결과 → 전략:{_index + 1:02d}'] = tuple(_detail)


def select_flow(name: str) -> None:
    st.session_state.flow_name = name
    st.session_state.flow_step = 0
    st.session_state.tree_open_dir = str(PurePosixPath(FLOW_DEFINITIONS[name][0][3]).parent)


def move_step(delta: int) -> None:
    flow = FLOW_DEFINITIONS[st.session_state.flow_name]
    step = max(0, min(len(flow) - 1, st.session_state.flow_step + delta))
    st.session_state.flow_step = step
    st.session_state.tree_open_dir = str(PurePosixPath(flow[step][3]).parent)


def open_folder(path: str) -> None:
    st.session_state.tree_open_dir = path


def toggle_tree_folder(path: str) -> None:
    opened = set(st.session_state.get('expanded_tree_folders', set()))
    if path in opened:
        opened.remove(path)
    else:
        opened.add(path)
    st.session_state.expanded_tree_folders = opened


def keep_active_tree_path_open(active_path: str) -> None:
    opened = set(st.session_state.get('expanded_tree_folders', set()))
    current = ''
    for part in PurePosixPath(active_path).parts[:-1]:
        current = f'{current}/{part}'.strip('/')
        opened.add(current)
    st.session_state.expanded_tree_folders = opened


def render_project_tree(entries, active_path: str) -> None:
    """최상위 구조는 유지하고, 현재·이전에 지나간 경로만 펼치는 발표용 트리입니다."""
    keep_active_tree_path_open(active_path)
    opened = set(st.session_state.expanded_tree_folders)
    children_by_parent: dict[str, list] = {}
    for entry in entries:
        parent = str(PurePosixPath(entry.relative_path).parent)
        parent = '' if parent == '.' else parent
        children_by_parent.setdefault(parent, []).append(entry)

    def children(parent: str):
        return sorted(children_by_parent.get(parent, []), key=lambda item: (not item.is_dir, item.relative_path.casefold()))

    def render_branch(parent: str, depth: int = 0) -> None:
        prefix = '　' * depth
        for entry in children(parent):
            name = PurePosixPath(entry.relative_path).name
            if entry.is_dir:
                is_open = entry.relative_path in opened
                marker = '▾' if is_open else '▸'
                st.button(
                    f'{prefix}{marker} 📁 {name}', key=f'tree-toggle-{entry.relative_path}',
                    use_container_width=True, on_click=toggle_tree_folder, args=(entry.relative_path,),
                )
                if is_open:
                    render_branch(entry.relative_path, depth + 1)
            else:
                is_current = entry.relative_path == active_path
                marker = '  ← 현재 단계' if is_current else ''
                css = ' is-current' if is_current else ''
                st.markdown(
                    f'<div class="project-file-row{css}">{prefix}　📄 {html.escape(name)}{marker}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown('<section class="project-tree"><h3>전체 프로젝트 트리</h3><p>폴더를 누르면 열고 닫을 수 있습니다. 현재 단계와 이미 지나간 경로는 유지해, 전체 구조 안에서 파일 위치를 계속 보여 줍니다.</p><div class="project-tree-root">TP2-3/</div>', unsafe_allow_html=True)
    render_branch('')
    st.markdown('</section>', unsafe_allow_html=True)


def render_feature_switcher(flow_name: str) -> None:
    st.markdown('<div class="feature-heading">발표할 기능 선택</div><p class="feature-caption">기능을 고르면 아래의 실행 흐름·현재 파일 위치·상세 설명이 함께 바뀝니다.</p>', unsafe_allow_html=True)
    names = list(FLOW_DEFINITIONS)
    selected = st.selectbox('살펴볼 기능', names, index=names.index(flow_name))
    if selected != flow_name:
        select_flow(selected)
        st.rerun()


def render_active_path_tree(active_path: str) -> None:
    st.markdown('<section class="function-tree"><h3>담당 파일과 주변 구조</h3><p>현재 담당 파일은 강조하고, 같은 폴더의 파일과 역할을 함께 표시합니다.</p>', unsafe_allow_html=True)
    parts = PurePosixPath(active_path).parts
    st.markdown('<div class="tree-root">TP2-3/</div>', unsafe_allow_html=True)
    for depth, part in enumerate(parts):
        prefix = '│   ' * depth
        is_file = depth == len(parts) - 1
        marker = ' ← 현재 단계' if is_file else ''
        css = ' is-current' if is_file else ''
        icon = '└──' if is_file else '├──'
        st.markdown(f'<div class="tree-row{css}">{prefix}{icon} <span class="tree-path">{html.escape(part)}{marker}</span></div>', unsafe_allow_html=True)
    st.markdown('</section>', unsafe_allow_html=True)
    parent = (PROJECT_ROOT / active_path).parent
    if parent.is_dir():
        siblings = sorted((p for p in parent.iterdir() if p.is_file() and p.suffix in {'.py', '.jsx', '.js', '.css', '.ts', '.tsx'}),
                          key=lambda p: (p.name != parts[-1], p.name))
        st.caption('같은 폴더 · 파일별 역할')
        for sibling in siblings[:9]:
            relative = sibling.relative_to(PROJECT_ROOT).as_posix()
            info = path_role(relative)
            selected = relative == active_path
            css = ' is-current' if selected else ''
            st.markdown(f'<div class="tree-neighbor{css}"><b>{"● " if selected else "├─ "}{html.escape(sibling.name)}</b><span>{html.escape(info["role"])}</span></div>', unsafe_allow_html=True)
        if len(siblings) > 9:
            with st.expander(f'나머지 파일 {len(siblings) - 9}개'):
                for sibling in siblings[9:]:
                    st.text(sibling.name)


def render_folder_browser(entries, active_path: str) -> None:
    all_folders = {'', *(entry.relative_path for entry in entries if entry.is_dir)}
    open_dir = st.session_state.get('tree_open_dir', str(PurePosixPath(active_path).parent))
    if open_dir not in all_folders:
        open_dir = ''
        st.session_state.tree_open_dir = open_dir

    def direct_children(folder: str):
        prefix = f'{folder}/' if folder else ''
        children = []
        for entry in entries:
            if not entry.relative_path.startswith(prefix):
                continue
            remainder = entry.relative_path[len(prefix):]
            if '/' not in remainder:
                children.append(entry)
        return sorted(children, key=lambda item: (not item.is_dir, item.relative_path.casefold()))

    st.markdown('<div class="folder-browser-title">현재 폴더를 열어 보기</div>', unsafe_allow_html=True)
    crumb_paths = ['']
    current = ''
    for part in PurePosixPath(open_dir).parts:
        current = f'{current}/{part}'.strip('/')
        crumb_paths.append(current)
    crumb_columns = st.columns(min(len(crumb_paths), 4))
    for index, path in enumerate(crumb_paths[-4:]):
        label = 'TP2-3' if not path else PurePosixPath(path).name
        with crumb_columns[index]:
            st.button(label, key=f'crumb-{index}-{path}', use_container_width=True, on_click=open_folder, args=(path,))

    st.caption(f'열린 위치: TP2-3/{open_dir}' if open_dir else '열린 위치: TP2-3/')
    for entry in direct_children(open_dir):
        name = PurePosixPath(entry.relative_path).name
        if entry.is_dir:
            st.button(f'📁 {name}', key=f'folder-{entry.relative_path}', use_container_width=True, on_click=open_folder, args=(entry.relative_path,))
        else:
            active = entry.relative_path == active_path
            suffix = '  ← 현재 단계' if active else ''
            css = ' is-current' if active else ''
            st.markdown(f'<div class="tree-row{css}">📄 <span class="tree-path">{html.escape(name)}{suffix}</span></div>', unsafe_allow_html=True)


def render_flow(flow: list[tuple[str, str, str, str, str, str]], focus: int) -> None:
    rendered: list[str] = []
    for index, (number, title, _, path, _, _) in enumerate(flow):
        classes = ' is-focus' if index == focus else (' is-done' if index < focus else '')
        rendered.append(f'<div id="flow-step-{html.escape(number)}" class="flow-step{classes}"><small>{html.escape(number)} 단계</small><b>{html.escape(title)}</b><span>{html.escape(path)}</span></div>')
        if index < len(flow) - 1:
            arrow_class = ' is-moving' if index == focus else ''
            rendered.append(f'<div class="flow-arrow{arrow_class}">↓</div>')
    st.markdown(f'<div class="flow-rail">{"".join(rendered)}</div>', unsafe_allow_html=True)


def _format_detail(value: str) -> str:
    """설명 안의 `함수명`·`필드명`을 안전한 코드 칩으로 표시합니다."""
    escaped = html.escape(value)
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)


def render_system_overview() -> None:
    """팀원이 세부 파일을 보기 전에 공유해야 할 전체 책임 경계를 보여 줍니다."""
    st.markdown(
        '''<section class="system-overview" aria-label="전체 시스템 처리 구조">
          <div class="section-head"><h2>서비스 전체 처리 구조</h2><p>사용자 입력부터 근거·예측·기획서까지의 책임 경계</p></div>
          <div class="system-flow">
            <div class="system-node"><small>01 · USER / UI</small><b>React + Vite · 5176</b><span>지역 선택, 조건 입력, 작업 상태 조회, 차트와 기획서 표시</span></div>
            <div class="system-node"><small>02 · API BOUNDARY</small><b>/api · /ai</b><span>지도·일반 업무는 Backend 8100, 분석·생성은 AI Server 8112로 분리</span></div>
            <div class="system-node"><small>03 · VERIFIED INPUT</small><b>MySQL · Joblib · RAG</b><span>관측 수치는 MySQL, 전망은 저장 ML, 공식 문서는 출처가 남는 RAG가 담당</span></div>
            <div class="system-node"><small>04 · AGENT PIPELINE</small><b>근거 → 사례 → 적용 → 작성 → 검수</b><span>Qwen 후보 비교, Gemma 본문 작성, 독립 최종 검수와 코드 품질 계약</span></div>
            <div class="system-node"><small>05 · RESULT</small><b>화면 · MySQL · Word/PPT</b><span>구조화 JSON과 검수 상태를 표시하고, 명시적 저장·출력 요청만 반영</span></div>
          </div>
          <div class="system-rule">
            <div><b>정확한 현재 수치</b><br>MySQL·검증 원자료</div>
            <div><b>미래 전망 수치</b><br>시간순 평가를 통과한 ML</div>
            <div><b>정책·사례 근거</b><br>URL·source ID가 남는 RAG</div>
            <div><b>설명과 전략</b><br>LLM 작성 + Reviewer 검수</div>
          </div>
        </section>''',
        unsafe_allow_html=True,
    )


def render_stage_contract(
    *, number: str, title: str, visible: str, relative_path: str,
    processing: str, next_step: str, role: dict[str, str],
) -> None:
    """선택 단계의 입력·실행 주체·출력을 한 줄 계약으로 보여 줍니다."""
    st.markdown(
        f'''<section class="stage-contract">
          <div class="stage-contract-header"><span class="stage-number">STEP {html.escape(number)}</span><h2>{html.escape(title)}</h2></div>
          <div class="contract-flow">
            <div class="contract-node"><small>사용자·이전 단계에서 들어오는 것</small><b>{html.escape(visible)}</b></div>
            <div class="contract-arrow" aria-hidden="true">→</div>
            <div class="contract-node is-code"><small>책임 파일 · 계층</small><b>{html.escape(relative_path)}</b><span>{html.escape(role['layer'])} · {html.escape(role['role'])}</span></div>
            <div class="contract-arrow" aria-hidden="true">→</div>
            <div class="contract-node"><small>이 단계가 내보내는 결과</small><b>{html.escape(next_step)}</b></div>
          </div>
          <p class="processing-note"><b>이 파일 안에서 하는 일</b> · {html.escape(processing)}</p>
        </section>''',
        unsafe_allow_html=True,
    )


def render_stage_details(stage_detail: tuple[str, ...], *, show_transferability_explainer: bool) -> None:
    """각 단계의 실제 계약을 발표자가 항목별로 읽기 쉽게 표시합니다."""
    st.markdown('<div class="detail-title">함수 · 데이터 · 판단 기준</div><p class="detail-intro">실제 함수와 API 계약을 기준으로 설명합니다. 입력값, 처리 책임, 차단 조건과 반환값을 순서대로 확인하세요.</p>', unsafe_allow_html=True)
    if show_transferability_explainer:
        st.markdown(
            '''<section class="fit-explainer" aria-label="지역 적합성 판단 원리">
              <h4>지역 적합성 판단은 “타지역 사례를 복사하는 단계”가 아닙니다</h4>
              <p>선택 지역의 실제 병목과 사업 조건을 먼저 확인하고, 공식 사례의 운영 방식을 조건부 시범사업 후보로 바꾼 뒤, 근거가 충분할 때만 다음 작성 단계로 보냅니다.</p>
              <div class="fit-diagram">
                <div class="fit-node"><b>1. 지역 사실</b><span>관측 월별 지표, 전국·유사 지역 비교, ML 전망, 지역 공식 문서</span></div>
                <div class="fit-arrow" aria-hidden="true">→</div>
                <div class="fit-node"><b>2. 사례·제약</b><span>공식 사례 카드의 운영 방식·대상·조건·위험 + 예산·기간·인력 제약</span></div>
                <div class="fit-arrow" aria-hidden="true">→</div>
                <div class="fit-node"><b>3. 서로 다른 후보</b><span>예약·체류·소비 전환처럼 작동 원리가 다른 2~3개 후보를 비교</span></div>
                <div class="fit-arrow" aria-hidden="true">→</div>
                <div class="fit-node is-decision"><b>4. 조건부 결정</b><span>선택 이유·필수 조건·측정 설계·중단/확대 기준을 JSON으로 반환</span></div>
              </div>
              <div class="fit-checks">
                <div class="fit-check"><b>지역 근거 확인</b><br>각 후보는 사례 ID만이 아니라 선택 지역 또는 검증된 전국 비교의 source_id를 함께 연결해야 합니다.</div>
                <div class="fit-check"><b>사례 범위 확인</b><br>선택 지역 → 같은 시도 → 타시도 유사 지역 → 전국 운영 원리 순으로 비교하되, 전국 사례도 검토합니다.</div>
                <div class="fit-check"><b>실행 가능성 확인</b><br>예산은 수량×단가식, KPI는 기준기간·주기·원자료·비교집단을 갖춰야 합니다.</div>
                <div class="fit-check"><b>다음 단계 차단</b><br>사례 없음·출처 ID 불일치·후보 부족·지역 근거 누락 등은 Planner 실행 전에 오류로 멈춥니다.</div>
              </div>
              <p class="fit-caution"><b>중요:</b> 0~100 적합성·근거 점수는 비교 설명용 출력입니다. 점수 하나가 자동 승인하지 않으며, 실제 JSON 검증 규칙을 통과해야 기획안 작성으로 진행합니다.</p>
            </section>''',
            unsafe_allow_html=True,
        )
    detail_blocks = []
    for label, description in zip(stage_detail[::2], stage_detail[1::2]):
        detail_blocks.append(
            f'<section class="detail-block"><h4>{html.escape(label)}</h4><p>{_format_detail(description)}</p></section>'
        )
    st.markdown(f'<div class="detail-grid">{"".join(detail_blocks)}</div>', unsafe_allow_html=True)


if 'flow_name' not in st.session_state:
    st.session_state.flow_name = '기획서 생성'
if 'flow_step' not in st.session_state:
    st.session_state.flow_step = 0

flow_name = st.session_state.flow_name
flow = FLOW_DEFINITIONS[flow_name]
focus = min(st.session_state.flow_step, len(flow) - 1)
st.session_state.flow_step = focus
number, title, visible, relative_path, processing, next_step = flow[focus]
role = path_role(relative_path)
if 'tree_open_dir' not in st.session_state:
    st.session_state.tree_open_dir = str(PurePosixPath(relative_path).parent)
stage_detail = STAGE_DETAILS.get(
    f'{flow_name}:{number}',
    ('핵심 함수', '현재 파일의 화면·서버 역할을 수행합니다.', '전달 데이터', '선택한 지역과 현재 화면 상태를 다음 단계에 전달합니다.', '다음 결과', next_step),
)

st.markdown('''<style>
.block-container { max-width: 1440px; padding: 1rem 1.5rem 2rem; }
.detail-grid { grid-template-columns: minmax(0, 1fr); gap: .8rem; }
.detail-block { padding: 1rem 1.1rem; background: white; border: 1px solid #dce6ed; border-left: 3px solid #57a9b9; }
.detail-block h4 { font-size: .94rem; margin-bottom: .45rem; }
.detail-block p { font-size: .94rem; line-height: 1.85; overflow-wrap: anywhere; }
.detail-title { font-size: 1rem; }
.detail-intro { font-size: .88rem; line-height: 1.65; }
.contract-flow { grid-template-columns: minmax(0, 1fr); gap: .45rem; }
.contract-arrow { display: none; }
.contract-node { padding: .7rem .85rem; }
.contract-node b { font-size: .87rem; overflow-wrap: anywhere; font-weight: 550; }
.contract-node small { font-size: .75rem; }
.stage-contract h2 { font-size: 1.2rem; }
.processing-note { display: none; }
.tree-row { font-size: .9rem; line-height: 1.7; overflow-wrap: anywhere; }
.tree-neighbor { padding: .65rem .75rem; margin-bottom: .35rem; border: 1px solid #dce6ed; border-radius: 7px; background: #fff; }
.tree-neighbor b { display: block; font: .8rem monospace; color: #315870; overflow-wrap: anywhere; }
.tree-neighbor span { display: block; margin-top: .35rem; font-size: .8rem; color: #617887; line-height: 1.6; }
.tree-neighbor.is-current { border-color: #57a9b9; background: #eaf7f9; }
div[data-testid="stColumn"]:has(> div .sticky-tree) { max-height: calc(100vh - 2rem); overflow-y: auto; }
div[data-testid="stColumn"]:has(.detail-grid) { position: static; max-height: none; overflow: visible; }
.fit-node span, .fit-check { font-size: .84rem; line-height: 1.7; }
div[data-testid="stRadio"] label p { font-size: .87rem; line-height: 1.55; }
div[data-testid="stRadio"] label { padding: .35rem 0; }
@media(max-width: 900px) {
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  div[data-testid="stColumn"] { min-width: 100% !important; flex-basis: 100% !important; }
  .block-container { padding: .8rem; }
}
</style>''', unsafe_allow_html=True)
st.markdown('<section class="map-hero"><h1>프로젝트 구조 지도</h1><p><b>기능 선택 → 단계 선택 → 처리 과정 확인</b> 순서로 읽으세요. ML은 지표를 선택해 같은 과정을 따라갈 수 있습니다.</p></section>', unsafe_allow_html=True)
st.markdown('<p class="map-caption">상단은 서비스 전체 책임 경계, 아래는 기능별 실행 계약입니다. 전체 파일 목록은 별도 탭에서 확인할 수 있습니다.</p>', unsafe_allow_html=True)
with st.expander('서비스 전체 흐름 · React / API / 데이터 / AI', expanded=False):
    render_system_overview()

flow_tab, tree_tab = st.tabs(['기능별 실행 구조', '전체 파일 트리'])
with flow_tab:
    render_feature_switcher(flow_name)
    left, content = st.columns([1, 3.4], gap='large')
    with left:
        st.markdown(f'<section class="flow-panel"><div class="flow-heading"><h2>{html.escape(flow_name)}</h2><span class="flow-count">{focus + 1} / {len(flow)}</span></div>', unsafe_allow_html=True)
        previous, following = st.columns(2)
        with previous:
            st.button('← 이전', use_container_width=True, disabled=focus == 0, on_click=move_step, args=(-1,))
        with following:
            st.button('다음 →', use_container_width=True, disabled=focus == len(flow) - 1, on_click=move_step, args=(1,))
        chosen_step = st.radio('바로 이동할 단계', range(len(flow)), index=focus,
                               format_func=lambda i: f'{flow[i][0]}  {flow[i][1]}',
                               key=f'stage-picker-{flow_name}-{focus}')
        if chosen_step != focus:
            move_step(chosen_step - focus)
            st.rerun()
        st.markdown('</section>', unsafe_allow_html=True)

    with content:
        if flow_name == 'ML 결과 → 전략':
            metric = st.selectbox('설명할 ML 지표', list(_ml_guides),
                                  format_func=lambda key: f'{_ml_guides[key]["role"]} · {key}', key='ml-guide-target')
            guide = _ml_guides[metric]
            step = guide['steps'][focus]
            relative_path, processing, next_step = step['file'], step['detail'], step['output']
            visible = f'공식 월별 표 · {metric}' if focus == 0 else guide['steps'][focus - 1]['output']
            role = path_role(relative_path)
            stage_detail = ('호출 함수', f'`{step["function"]}`', '어떻게 처리하는가', step['detail'],
                            '다음에 전달하는 값', f'`{step["output"]}`', '이 지표의 전략 활용', guide['interpretation'],
                            '조건부 해석 예시', guide['example'], '해석 범위', guide['limit'])
        render_stage_contract(
            number=number, title=title, visible=visible, relative_path=relative_path,
            processing=processing, next_step=next_step, role=role,
        )
        explanation_column, path_column = st.columns([3, 2], gap='medium')
        with explanation_column:
            render_stage_details(
                stage_detail,
                show_transferability_explainer=(flow_name == '기획서 생성' and number == '07'),
            )
            if flow_name == 'ML 결과 → 전략':
                with st.expander('전체 호출 트리 펼치기'):
                    st.code(guide['tree'], language='text')
        with path_column:
            st.markdown('<div class="sticky-tree"></div>', unsafe_allow_html=True)
            render_active_path_tree(relative_path)

with tree_tab:
    st.markdown('<div class="tree-help"><b>전체 파일 트리</b>에서 폴더를 열어 실제 위치를 확인할 수 있습니다. 선택한 실행 단계의 상위 폴더는 자동으로 열리고, 담당 파일에는 “현재 단계”가 표시됩니다.</div>', unsafe_allow_html=True)
    include_generated = st.checkbox('의존성·캐시 폴더까지 포함', value=False, help='기본값은 node_modules·가상환경·빌드 결과를 제외합니다.')
    entries = scan_project(include_generated=include_generated)
    render_project_tree(entries, relative_path)
    tree_text = build_tree_text(entries)
    st.download_button('tree.txt 다운로드', tree_text, file_name='tp2-3-tree.txt', mime='text/plain')

st.caption('읽기 전용 발표 도구 · 코드·.env 값·API 키는 표시하지 않음 · 현재 프로젝트 파일을 수정하지 않음')

