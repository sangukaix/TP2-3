/**
 * FastAPI가 준비된 뒤 프론트엔드가 호출할 API 모음입니다.
 * Vite는 vite.config.js의 proxy를 통해 /api 요청을 TP2-3 Backend로 전달합니다.
 */
export async function getRegionDashboard(regionCode) {
  const response = await fetch(`/api/v1/regions/${regionCode}/dashboard`)

  if (!response.ok) throw new Error('지역 관광 대시보드 데이터를 불러오지 못했습니다.')
  return response.json()
}

/**
 * VWorld 키는 Backend에서만 사용합니다.
 * React는 이 API를 호출해 키가 제거된 시군구 GeoJSON만 받습니다.
 */
export async function getSigunguBoundaries(sidoCode = '') {
  const query = sidoCode ? `?sido_code=${encodeURIComponent(sidoCode)}` : ''
  const response = await fetch(`/api/v1/boundaries/sigungu${query}`)

  if (!response.ok) throw new Error('시군구 행정구역 경계를 불러오지 못했습니다.')
  return response.json()
}

/** 전국 17개 시도 경계입니다. 첫 지도 단계에서만 사용합니다. */
export async function getSidoBoundaries() {
  const response = await fetch('/api/v1/boundaries/sido')

  if (!response.ok) throw new Error('시도 행정구역 경계를 불러오지 못했습니다.')
  return response.json()
}

/** 강남구 관광지 Open API의 실제 연결을 확인하는 작은 테스트용 호출입니다. */
export async function getGangnamTourismOpenApiDemo() {
  const response = await fetch('/api/v1/demo/gangnam-tourism')

  if (!response.ok) throw new Error('강남구 관광 Open API 데이터를 불러오지 못했습니다.')
  return response.json()
}

/** AI 서버에 전략 보고서를 요청합니다. OpenAI 키는 브라우저가 아닌 서버 .env에서만 사용합니다. */
export async function getAiStrategyReport(regionCode, options) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/strategy-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => null)
    const message = error?.detail?.message || 'AI 전략 보고서를 생성하지 못했습니다.'
    // 개발 중 API 크레딧이 소진되면 실제 원자료 기반 오프라인 샘플로 화면만 검증합니다.
    // 응답의 generation_mode를 통해 실시간 AI 결과와 명확히 구분합니다.
    if (/credit|quota|billing|크레딧|잔액/i.test(message)) {
      const sampleResponse = await fetch(`/ai/v1/demo/${regionCode}/strategy-report/sample`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options),
      })
      if (sampleResponse.ok) return sampleResponse.json()
    }
    throw new Error(message)
  }
  return response.json()
}

/**
 * 긴 AI 전략기획 작업을 서버 백그라운드에 등록합니다.
 * 응답을 기다리는 화면이 사라져도 서버 작업은 계속됩니다.
 */
export async function startAiStrategyReportJob(regionCode, options) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/strategy-report/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    const message = Array.isArray(error?.detail) ? error.detail.map((item) => item.msg?.replace('Value error, ', '')).join(' / ') : error?.detail?.message
    throw new Error(message || 'AI 전략기획 작업을 시작하지 못했습니다.')
  }
  return response.json()
}

/** 서버에 남아 있는 장기 작업의 상태를 조회합니다. OpenAI 키는 노출되지 않습니다. */
export async function getAiStrategyReportJob(regionCode, jobId) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/strategy-report/jobs/${encodeURIComponent(jobId)}`)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || 'AI 전략기획 작업 상태를 불러오지 못했습니다.')
  }
  return response.json()
}

/**
 * 화면에서 확인한 구조화 AI 보고서를 서버에 보내 Word 기획서로 내려받습니다.
 * .docx 조립과 원자료 그래프 생성은 AI 서버가 담당하므로 React에는 비밀 키나 문서 라이브러리가 없습니다.
 */
export async function downloadAiStrategyProposal(regionCode, report) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/strategy-proposal.docx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(report),
  })

  if (!response.ok) throw new Error('Word 기획서를 생성하지 못했습니다.')
  return response.blob()
}

/** 같은 구조화 보고서를 회의·발표용 PowerPoint로 만듭니다. */
export async function downloadAiStrategyPresentation(regionCode, report) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/strategy-proposal.pptx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(report),
  })

  if (!response.ok) throw new Error('PowerPoint 기획서를 생성하지 못했습니다.')
  return response.blob()
}

/** 팀 공용 MySQL에 저장된 기획서 목록입니다. 브라우저별 localStorage를 사용하지 않습니다. */
export async function getStoredStrategyReports() {
  const response = await fetch('/ai/v1/strategy-reports')
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || '저장된 기획서 목록을 불러오지 못했습니다.')
  }
  return response.json()
}

/** 제목을 눌렀을 때 MySQL에 보관된 기획안 원문을 읽습니다. */
export async function getStoredStrategyReport(reportId) {
  const response = await fetch(`/ai/v1/strategy-reports/${encodeURIComponent(reportId)}`)
  if (!response.ok) throw new Error('저장된 기획안을 불러오지 못했습니다.')
  return response.json()
}

/** 생성 시 저장된 Word/PPT를 내려받습니다. 파일이 없을 때만 서버가 한 번 생성합니다. */
export async function downloadStoredStrategyDocument(reportId, fileFormat) {
  const response = await fetch(`/ai/v1/strategy-reports/${encodeURIComponent(reportId)}/documents/${fileFormat}`)
  if (!response.ok) throw new Error('저장된 문서를 내려받지 못했습니다.')
  return response.blob()
}

/** 챗봇으로 수정한 기획안을 사용자가 저장 버튼을 눌렀을 때 MySQL 원문에 반영합니다. */
export async function saveStoredStrategyReport(reportId, regionCode, report) {
  const response = await fetch(`/ai/v1/strategy-reports/${encodeURIComponent(reportId)}?region_code=${encodeURIComponent(regionCode)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || '기획안을 저장하지 못했습니다.')
  }
  return response.json()
}

/** 선택 지역 원본에서 계산한 최신 월·전월 대비 상단 카드 데이터입니다. OpenAI 호출은 하지 않습니다. */
export async function getAiRegionDashboard(regionCode, regionName) {
  const params = new URLSearchParams({ region_name: regionName })
  const response = await fetch(`/ai/v1/demo/${regionCode}/dashboard?${params}`)

  if (!response.ok) throw new Error('선택 지역의 월간 대시보드 데이터를 불러오지 못했습니다.')
  return response.json()
}

/**
 * 지역 상세 팝업의 관광자원 정보입니다.
 * 인증키는 AI 서버 .env에서만 읽으며, 이 호출은 OpenAI를 사용하지 않습니다.
 */
export async function getAiRegionOpenApiInfo(regionCode, regionName) {
  const params = new URLSearchParams({ region_name: regionName })
  const response = await fetch(`/ai/v1/demo/${regionCode}/region-info?${params}`)

  if (!response.ok) throw new Error('관광 Open API 지역 정보를 불러오지 못했습니다.')
  return response.json()
}

/**
 * 선택 지역 원자료와 현재 기획안을 서버에서 함께 읽는 AI 도우미입니다.
 * 공식 웹 검색 사용 여부도 서버에 전달하지만 OpenAI 키는 브라우저로 노출하지 않습니다.
 */
export async function chatWithTourismAssistant(regionCode, options) {
  const response = await fetch(`/ai/v1/demo/${regionCode}/assistant-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || 'AI 챗봇이 답변하지 못했습니다.')
  }
  return response.json()
}

/** 참고자료의 텍스트만 추출합니다. 이 단계에서는 OpenAI를 호출하지 않습니다. */
export async function uploadPlanningReference(file) {
  if (file.size > 2_000_000) throw new Error('2MB 이하 파일만 첨부할 수 있습니다.')
  const response = await fetch(`/ai/v1/planning/reference?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
  })
  const result = await response.json()
  if (!response.ok) throw new Error(result?.detail?.message || '참고자료를 읽지 못했습니다.')
  return result
}
