# AI 전략 리포트·기획안 생성 설계

## 1. 사용자 흐름

```text
지원 지역 선택
  → 원본 ZIP 기반 대시보드 확인
  → AI 전략기획서 생성
  → 핵심 판단 · 월간 추세 · 단계별 집행 · 실행/미실행 목표 비교 확인
  → 기획안 다운로드(.docx / .pptx)
```

화면은 문제 확인, 솔루션, 집행 방법과 목표 규모를 함께 검토하도록 구성한다. 같은 내용은 Word 문서에서 회의·결재용 형식으로 다시 정리한다.

## 2. 폴더·기능 역할

```text
frontend/src/
├─ App.jsx                       # 리포트 UI·반응형 시나리오·다운로드 버튼
├─ App.css                       # 화면·차트·다운로드 영역 디자인
└─ api/dashboardApi.js           # AI 서버 요청과 .docx Blob 다운로드

ai_server/app/
├─ main.py                       # ZIP 계산, Pydantic 응답, FastAPI endpoint
├─ agents/
│  ├─ evidence_agent.py          # 원본·Open API·RAG·공식 웹 근거 수집
│  ├─ case_study_agent.py        # 전국 공식 성공사례·성과·예산·조건 수집
│  ├─ transferability_agent.py   # 사례의 지역 적합성과 시범사업 구조 평가
│  ├─ planner_agent.py           # 근거 패키지 기반 실행 기획안 작성
│  ├─ reviewer_agent.py          # 근거성·실행성·간결성 품질 검토
│  ├─ report_orchestrator.py     # 다섯 Agent 실행과 1회 재작성 제어
│  ├─ prompts.py                 # Agent별 프롬프트·페르소나 관리
│  └─ README.md                  # 역할·조정 방법·주의사항
├─ openai_responses.py           # Responses API 구조화 출력 공통 처리
├─ tourism_open_api.py           # 국문관광정보 지역 관광자원 조회
├─ rag_store.py                  # 영속형 ChromaDB 검색·색인
├─ proposal_document.py          # 검증된 JSON을 최대 5쪽 Word 문서와 PNG 그래프로 변환
├─ proposal_presentation.py      # 기존 endpoint가 유지하는 PowerPoint 함수 진입점
├─ proposal_presentation_v2.py   # 8장 실행기획서의 내용·슬라이드 순서
└─ presentation_theme.py         # PPT 공통 색·폰트·차트·공식 이미지 표현
```

## 3. Multi-Agent·OpenAI 설계

```text
Evidence Agent
  ├─ 데이터랩 ZIP 수치
  ├─ 한국관광공사 Open API 관광자원
  ├─ ChromaDB 지역 공식 문서 Top-k
  └─ 선택 지역 공식 도메인 웹 조사
        ↓ Evidence Pack
Case Scout Agent
  ├─ 검수된 공식 성공사례 카드·RAG
  └─ 전국 공식 평가·결산·예산·보도자료 웹 조사
        ↓ Benchmark Cases
Transferability Agent → 지역 적합성 점수·적용 조건·시범사업 구조
        ↓ Evidence Pack + 사례 평가
Planner Agent → 엄격한 JSON Schema 기획안
        ↓
Reviewer Agent → 6개 품질 차원·중대 오류 검사
        ↓
미달 시 Planner 1회 수정 → Reviewer 최종 검토
```

- 선택 지역 Evidence 수집과 전국 성공사례 수집은 서로 독립적으로 동시에 실행한다. 두 결과를 지역 적합성 평가로 연결한 뒤 하나의 Evidence Pack으로 합친다.
- 성공사례는 `사업 대상·운영 방식·공개 예산·관측 결과·측정 기간·적용 조건·위험`으로 구조화한다.
- 타 지역의 관측 성과는 선택 지역의 보장 효과로 사용하지 않으며, 실행 목표는 별도 시나리오로 표시한다.
- 동일 지역·동일 원자료·동일 조사 설정으로 다시 생성하면 근거 패키지를 기본 1시간 재사용한다. Planner 작성과 Reviewer 검수는 매번 새로 수행한다. 재사용 시간은 `EVIDENCE_CACHE_TTL_SECONDS`로 조정하며 `0`이면 끈다.

- 호출 위치: `ai_server/app/main.py`만 호출한다. React는 OpenAI 키·공공 API 키를 읽지 않는다.
- 입력: 원본에서 재계산한 기간, 월별 방문자 수, 외지인 관광소비액, 체류·관심도 관측값, 최신 소비 업종 구성, 동일 시도 원본 보유 시군구의 공통 최근 3개월 비교값이다.
- 대시보드와 AI 기획안의 월간 추세는 모든 지원 지역에서 가장 최근 12개월만 사용한다. 더 오래된 원본 ZIP은 삭제하지 않고 향후 계절성·ML 검증용으로 보존한다.
- 출력: JSON Schema로 `summary`, `observed_findings`, 단일 `strategies` 항목을 검증한다. 조사 공백은 Agent 내부 검토 정보로 보존하고 사용자 화면에는 출처 목록을 표시한다. `benchmark_case`는 일반 출처와 구분해 팝업의 `전략 설계에 참고한 사례` 카드에 최대 3건을 보여 준다.
- 기획 기간은 원칙적으로 향후 3~6개월이며, 문제와 집행 단계에 따라 기간을 유연하게 조정할 수 있다.
- 기획안 필드: 문제/제안(`problem_to_solve`), 실제 기간·수치·지역 비교를 담은 판단 근거(`comparison_analysis`), 해결안(`solution`), 일정·작업·산출물이 짝지어진 5개 집행 단계(`implementation_steps`), 기대 변화(`expected_effect`), 예산 산정식(`budget`), 내부 검토용 성과 기준(`kpi`)과 근거 ID(`evidence`)를 분리한다.
- 모델: 작성은 `OPENAI_REPORT_MODEL`, 지역 조사는 `OPENAI_RESEARCH_MODEL`, 사례 조사는 `OPENAI_CASE_RESEARCH_MODEL`, 적합성 평가는 `OPENAI_TRANSFER_MODEL`, 검토는 `OPENAI_REVIEW_MODEL`을 사용한다. 비어 있으면 보고서 모델로 대체한다.
- 프롬프트·페르소나는 `ai_server/app/agents/prompts.py`에서 한곳으로 관리한다. 역할별 코드 파일은 독립적으로 유지한다.
- 품질검토: 근거 타당성, 비교 품질, 실행 상세성, 간결성, 공무원 활용성, 시각자료 준비도를 평가한다. 82점 이상이고 critical 오류가 없어야 통과한다.

OpenAI는 문장·실행 제안을 담당한다. 월간 수치와 그래프는 항상 원본 ZIP의 계산값을 사용한다. OpenAI가 만들어 낸 방문객·관광소비·예산 금액을 사실처럼 표시하지 않는다.

개발 환경에서 API 크레딧이 소진된 경우에는 `strategy-report/sample`이 선택 지역의 실제 snapshot과 고정 문장 규칙으로 오프라인 테스트 결과를 만든다. 팝업에 `오프라인 테스트 결과`를 표시하고 공식 웹 조사·RAG·Case Scout·Transferability·Planner·Reviewer가 실행되지 않았음을 명시한다. `APP_ENV=production`에서는 이 endpoint를 제공하지 않는다.

ChromaDB RAG 호출 구조는 연결되어 있다. 지역 공식 문서는 `data/rag/official_documents.jsonl`, 검수한 성공사례는 `data/rag/official_case_studies.jsonl`에서 관리한다. 색인 전에는 검색 결과가 비어 있으며 응답의 `research_gaps`에 자료 부족을 기록한다. 월간 숫자표는 RAG에 넣지 않는다.

## 4. ML 자연추세와 실행 목표 비교의 정의

등록·검증된 저장 모델이 있으면 해당 지역의 과거 추세를 바탕으로 `ML 자연추세`를 먼저 표시한다. 사용자가 방문자·관광소비 목표율을 입력한 경우에만 같은 월 기준의 `실행 목표`를 별도 선으로 표시한다. 이 목표선은 사업의 인과효과 예측이나 보장 성과가 아니라, 목표 달성에 필요한 월별 수준이다. ML이 없는 지역은 효과 수치를 만들지 않고 관측 자료와 공식 근거만 표시한다.

```text
월별 방문 목표 = 해당 월 ML 자연추세 × (1 + 최종 목표율 × 월 진행률)
월별 소비 목표 = 해당 월 ML 자연추세 × (1 + 최종 목표율 × 월 진행률)
누적 목표 차이 = Σ(월별 실행 목표 - 월별 ML 자연추세)
```

기본 비교기간은 3개월이며, 사용자가 확정한 희망 일정과 모델의 전망 범위가 있으면 최대 6개월까지 유연하게 사용한다. 모델 선택은 시간순 Validation/Test와 seasonal-naive 기준선 비교를 통과한 저장 산출물만 사용한다.

## 5. Word 기획서 구성

1. 핵심 판단
2. 최신 관측 지표와 월간 방문·관광소비 그래프
3. 문제/제안과 실제 데이터 기반 판단 근거
4. 쉬운 표현의 해결 방법과 예산 준비 항목
5. 5단계 집행 방법 표·프로젝트 타임라인·완료 산출물
6. 실행/미실행 목표 비교 표·그래프
7. 전략에 참고한 공식 성공사례 표와 관광데이터랩·관광 Open API·공식 문서 등 사용한 자료명

문서는 `python-docx`로 생성하고, 원자료 추세·목표 비교 그래프는 `matplotlib`으로 생성한다. 장문 반복을 피하기 위해 Agent 출력과 문서 표는 글자 수를 제한하며, Word는 최대 5쪽 안에서 생성한다. 두 라이브러리는 루트 `requirements.txt`에서 관리한다.

## 6. PowerPoint 기획서 구성

1. 지역명·분석기간·핵심 제안 표지
2. 핵심 관측지표 3개와 문제/기회·추천안
3. 최근 12개월 방문자·관광소비 추세와 같은 기준의 지역 비교
4. 단일 추천 전략·운영 방식·핵심 산출물과 공식 지역 사진
5. ML 자연추세와 사용자 실행 목표, 누적 방문자·소비 목표 차이
6. 희망 예산·산정 원칙·성과 확인 지표
7. 일정·작업·산출물을 연결한 5단계 실행 로드맵
8. 공식 출처와 방문자·소비액 모델·시간순 검증 방식

PowerPoint는 `python-pptx`로 생성한다. 사진은 Agent가 선택한 한국관광공사 Open API의 공식 이미지 URL만 사용하며, 이미지가 없거나 다운로드에 실패해도 PPT 생성은 계속된다. 차트는 보고서의 관측값과 저장 ML 결과만 사용하고 LLM이 새 수치를 만들지 않는다.
