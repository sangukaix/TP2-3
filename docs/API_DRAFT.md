# 프론트엔드 연동 API 초안

> 상태: UI 골격용 초안. 실제 데이터 파일의 컬럼·지역 코드·기간을 검증한 뒤 Pydantic schema로 확정한다.

## 기본 원칙

### 사업 여건 계약 (2026-08-28 구현)

`POST /ai/v1/demo/{region_code}/strategy-report/jobs`의 기존 요청에 선택 필드 `planning_brief`를 추가한다. 생략하면 기존 호출과 호환된다.

```json
{
  "region_name": "서울특별시 강남구",
  "planning_brief": {
    "version": 1,
    "region_code": "11680",
    "budget_status": "confirmed",
    "budget_min_krw": null,
    "budget_max_krw": 30000000,
    "budget_hard_limit": true,
    "schedule_status": "fixed",
    "start_date": "2026-10-01",
    "end_date": "2026-12-31",
    "resources_confirmed": "",
    "resources_possible": "",
    "hard_constraints": "신규 시설 설치 제외",
    "preferences": "",
    "field_context": "",
    "references": []
  }
}
```

- 예산 상태: `unknown | indicative | confirmed`. 미정 금액은 null. 지정 금액은 1원~1조 원 정수이며 최소≤최대.
- 일정 상태: `unknown | flexible | fixed`. 지정 시 시작일·종료일 모두 필요, 시작≤종료.
- 자원은 확정/협의 중을 구분한다. 제약과 선호도 별도 필드다.
- 문서 `references`: `{name, text}` 최대 3개, 텍스트 각 6,000자 이하. 지시문이 아닌 사용자 제공 데이터로만 사용한다.
- 지역 불일치·조건 오류: HTTP 422. 작업 등록: HTTP 202 + 기존 job_id. 생성 결과에 `planning_brief`와 SHA256 `planning_brief_fingerprint`를 보존한다.
- 기존 채팅 요청도 `planning_brief`를 받는다. 현재 기획안이 있으면 그 기획안의 생성 당시 조건을 우선한다.

`POST /ai/v1/planning/reference?filename=자료.docx`

- body: 파일 바이트, Content-Type: application/octet-stream. TXT/MD/DOCX만 지원한다.
- 성공: `{name, text}`. 파일은 2MB 이하, DOCX 압축 해제 합계 12MB 이하. 초과 413, 잘못된 파일/텍스트 초과 422 + `detail: {code, message}`.
- 유료 AI·웹 호출 없이 메모리에서 읽는다. 원본 디스크 저장·공용 RAG 등록 없음.

- React는 `/api`와 `/ai` 경로만 호출한다.
- 로컬 개발에서는 일반 데이터 Backend FastAPI(`8100`), 원자료·근거 기반 전략 AI FastAPI(`8111`)가 담당한다. 배포 포트는 Nginx 뒤에서 별도로 설정한다.
- OpenAI API 키는 어떤 응답이나 React 코드에도 포함하지 않고 AI 서버의 `.env`에서만 읽는다.
- 모든 실제 수치에는 `region_code`, `year_month`, `source_name`, `source_url`을 함께 보존한다.

## 구현된 테스트·지도 엔드포인트

### `GET /api/v1/boundaries/sido`

첫 지도 단계에서 보여 줄 시도 경계를 반환한다. VWorld의 현행 경계 기준으로 광주·전남 통합처럼 행정구역이 변경된 경우에는 해당 기준을 그대로 표시한다. VWorld 시도 레이어에 누락될 수 있는 세종특별자치시는 시군구 경계에서 보완한다.

### `POST /ai/v1/demo/{region_code}/strategy-report`

`region_name`을 본문에 넣어 요청한다. AI 서버는 선택 지역 원본·Open API·지역 공식 문서를 Evidence Pack으로 만들고, Case Scout가 전국 공식 성과평가·결산·예산·보도자료에서 실제 집행 사례를 찾는다. Transferability Agent가 선택 지역 적용 조건을 평가한 뒤 Planner가 구조화 기획안을 작성한다. Reviewer는 근거·사례 오용·비교·실행성·간결성·공무원 활용성·시각자료를 검토하며 미달 시 한 번 재작성한다. 응답에는 기존 필드와 함께 `quality_review`, `evidence_sources`, `research_gaps`, `agent_trace`가 포함된다.

### `GET /ai/v1/demo/{region_code}/dashboard?region_name={region_name}`

선택 지역 공식 원본을 읽기 전용으로 계산해 상단 카드용 최신 기준월, 외지인 방문자 수, 외지인 관광소비액, 평균 숙박일수와 각각의 전월 대비를 반환한다. 이 경로는 OpenAI를 호출하지 않는다.

강남구(`11680`)는 예외적으로 저장된 ML artifact를 읽어 최근 3개월 관측값과 향후 3개월 예측값을 반환한다. 학습은 이 HTTP 요청에서 실행하지 않는다. `monthly_trend[].is_forecast`로 관측·예측을 구분하며, `forecast`에는 모델 버전·시간순 테스트 기간·MAE·한계를 담는다. `diagnostic.is_forecast=true`인 업종별 소비 금액은 전체 소비액 예측에 최신 관측 업종 비중을 적용한 가정이다.

### `GET /ai/v1/demo/sido-comparison?sido_name={sido_name}`

선택 시도 아래의 원본 보유 시군구를 대상으로, 모든 지역에 공통으로 존재하는 가장 최근 3개월의 순 방문자 수·외지인 관광소비액·숙박 방문 비율·평균 숙박일수 평균을 반환한다. 원본이 없는 시군구의 값은 만들지 않으며, 비교 가능한 시군구가 2개 미만이면 응답하지 않는다.

```json
{
  "region_name": "서울특별시 강남구",
  "latest_month": "2026-07",
  "source": "한국관광 데이터랩 강남구 공식 다운로드 ZIP",
  "metrics": [
    {
      "label": "7월 방문자 수",
      "value": "17,963,441명",
      "detail": "순 방문자 수",
      "change_label": "전월 대비",
      "change_value": "-0.1%",
      "change_direction": "down"
    }
  ]
}
```

현재 지원 지역의 원본 연결을 검증하는 경로다. 정식 서비스에서는 검증·전처리한 월간 지표를 MySQL과 일반 Backend의 `GET /api/v1/regions/{region_code}/dashboard`로 이전한다.

### `GET /ai/v1/demo/{region_code}/region-info?region_name={region_name}`

지역 선택 화면의 `지역 정보 상세보기` 팝업이 호출한다. 서버 `.env`의 한국관광공사 국문 관광정보 API 키로 `areaCode2`와 `areaBasedList2`를 조회하고, 관광자원명·분류·주소·제공 이미지 URL만 반환한다. 이 경로는 OpenAI를 호출하지 않는다.

월간 방문자·관광소비 수치는 이 경로에서 계산하지 않으며, 기존 `/dashboard` 원자료 응답과 화면에서 출처를 분리해 표시한다. API 키 미설정, 일시 오류, 지역명 미일치, 빈 결과는 HTTP 오류 대신 `status`와 사용자용 안내문으로 반환해 대시보드 전체가 멈추지 않게 한다.

### `POST /ai/v1/demo/{region_code}/strategy-report/jobs`

긴 AI 전략기획 생성을 서버 백그라운드 작업으로 등록하고 HTTP `202`와 `job_id`를 즉시 반환한다. React는 작업 ID를 브라우저 localStorage에 지역별로 보관한다. 따라서 사용자가 다른 페이지·탭으로 이동한 뒤 AI 전략기획 화면에 돌아와도 같은 작업을 계속 조회할 수 있다.

### `GET /ai/v1/demo/{region_code}/strategy-report/jobs/{job_id}`

백그라운드 작업의 `queued`, `running`, `completed`, `failed` 상태와 사용자용 안내문을 반환한다. 완료 시에만 구조화된 `ReportResponse`를 포함하며, React는 이를 저장 기획서 목록에 한 번만 기록한다. 개발 서버 재시작은 메모리 작업을 중단하므로, 운영 환경에서는 Redis·Celery 또는 DB 기반 작업 큐로 교체한다.

### `GET /api/v1/boundaries/sigungu?sido_code={2자리 시도 코드}`

VWorld WFS의 전국 시군구 경계를 Backend에서 불러와, 키가 없는 GeoJSON으로 반환한다. `sido_code`를 보내면 브라우저에는 선택 시도의 경계만 반환한다. VWorld는 한 요청에 1,000개 도형 제한이 있어 Backend가 BBOX 분할·중복 제거·시군구별 MultiPolygon 병합을 수행한다. 지도 표시용 좌표는 약 100m 허용오차로 단순화하며 통계·측량에는 사용하지 않는다.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "region_code": "11680", "region_name": "서울특별시 강남구" },
      "geometry": { "type": "MultiPolygon", "coordinates": [] }
    }
  ]
}
```

이 엔드포인트는 지도 표현용 경계에만 사용한다. 관광 원자료와의 실제 조인은 데이터랩 파일의 지역 코드 기준을 검증한 뒤 별도 매핑표로 수행한다.

2026년 6월까지의 인천 서구 원자료를 선택할 수 있도록, 인천 요청에는 현재 서해구·검단구 경계를 합친 코드 `28260` 호환 Feature를 추가한다. `display_name`은 `인천광역시 서구 (2026.06 원자료 기준)`이며 현재 두 구의 통계를 합산했다는 의미가 아니다.

## 예정 엔드포인트

### `GET /api/v1/regions/{region_code}/dashboard`

지역 대시보드에 표시할 검증된 사실을 반환한다.

```json
{
  "region_code": "11680",
  "region_name": "서울특별시 강남구",
  "period": { "from": "2023-01", "to": "2026-06" },
  "metrics": {
    "visitor_count": null,
    "tourism_spending_krw": null,
    "stay_ratio": null,
    "spending_per_visitor_krw": null
  },
  "monthly_trend": [],
  "sources": []
}
```

### `POST /ai/v1/regions/{region_code}/strategy-report`

저장된 지표·예측·공식 근거 문서를 바탕으로 AI 전략 보고서를 반환한다. LLM은 숫자를 계산하거나 출처 없는 사실을 만들지 않는다.

```json
{
  "region_code": "11680",
  "observation": [],
  "forecast": null,
  "recommendations": [],
  "sources": [],
  "generated_at": "2026-08-24T00:00:00+09:00"
}
```

## 현재 화면과의 연결 위치

- `frontend/src/api/dashboardApi.js`: 위 두 엔드포인트 호출 자리
- `frontend/src/pages/TourismDashboardPage.jsx`: 실제 응답을 카드·차트·진단에 표시하며 미지원 지역은 빈 상태로 처리
- `frontend/vite.config.js`: 개발 중 `/api → 8100`, `/ai → 8111` 프록시 설정
- `backend/app/services/vworld.py`: VWorld 키를 서버에서만 사용하고 시군구 GeoJSON을 캐시·중계
# ML 기획 근거 확인

`GET /ai/v1/ml/{region_code}/planning-evidence?region_name={region_name}`

- 저장 모델만 읽으며 OpenAI 호출이나 온라인 재학습을 하지 않는다.
- `status=available`일 때 방문·소비·체류·검색 7개 지표의 전망, 전년 동월 비교 신호, Validation/Test 오차와 의사결정 단위로 묶은 조사 질문을 반환한다.
- 기획안 내부 호출은 `planning_brief`를 함께 전달한다. 일정 미정이면 3·6개월 후보를 모두 만들고, 희망 일정이면 종료월까지 필요한 전망을 최대 12개월 범위에서 계산한다.
- `horizon_policy`에는 선택 근거, 전망 시작·종료월, 기획 비교 구간, 전체 일정 포함 여부와 신뢰도 구분이 들어간다. 1~3개월은 재귀 백테스트, 이후 월은 탐색 전망이다.
- 미지원 지역은 `unsupported`, 모델 재학습 필요·원자료 불일치는 `unavailable`로 반환하며 다른 지역 모델을 대신 쓰지 않는다.

## ML 학습 페이지 카탈로그

`GET /ai/v1/ml/learning/catalog`

- `region_registry.py`에 등록된 모델만 지역 선택 목록에 반환한다.
- 모델 메타데이터의 `target`을 순회해 데이터셋, 모델, Feature, 함수, 기법, Test 오차와 3개월 결과를 카드 단위로 반환한다.
- 새 지역이나 새 Target이 동일 계약으로 등록되면 React의 `MlTest` 페이지는 별도 카드 코드를 추가하지 않고 자동으로 목록을 늘린다.
- 학습용 읽기 전용 API이며 OpenAI, Open API, 모델 재학습을 실행하지 않는다.

### `POST /ai/v1/ml/learning/{region_code}/assistant`

- 요청: `question`, 최근 대화 `history` 최대 6개.
- AI Server가 선택 지역의 등록 모델 카탈로그, 코드 역할표, 기획안 전망기간 규칙을 OpenAI Responses API에 전달한다.
- 답변: `answer`, `key_points`, `related_modules`, `caution`의 구조화 JSON이다.
- 현재 ML 챗봇은 RAG·웹 검색을 사용하지 않는다. OpenAI 키가 없으면 `503 OPENAI_KEY_MISSING`, 미지원 지역은 `404 ML_LEARNING_REGION_UNAVAILABLE`을 반환한다.

### `GET /ai/v1/learning/{topic}`

- `topic`은 `openai` 또는 `react`다.
- OpenAI는 Agent 클래스·오케스트레이터·FastAPI route·환경변수 이름을, React는 src 파일·App route·fetch endpoint·package.json을 현재 소스에서 다시 읽는다.
- 파이프라인, 파일 역할, route, 의존성, 설계 원칙과 챗봇 흐름을 반환한다. 절대경로·소스 전문·환경변수 값은 반환하지 않는다.

### `POST /ai/v1/learning/{topic}/assistant`

- 자동 생성한 해당 주제 카탈로그와 최근 대화 최대 6개를 OpenAI에 전달한다.
- 답변은 `answer`, `key_points`, `related_files`, `caution` 구조다.
- RAG·웹 검색을 사용하지 않으며, 현재 프로젝트에 없는 기능을 사용 중이라고 설명하지 않도록 제한한다.
