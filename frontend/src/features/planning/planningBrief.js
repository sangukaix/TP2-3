/** 원자료와 별도로 보관하는 사용자 사업 여건. 지역별 초안과 생성 당시 조건은 구분합니다. */
export function emptyPlanningBrief(regionCode) {
  // API 스키마와 같은 기본 형태를 먼저 만들면, 미정 값도 0이나 빈 사실로 오해되지 않습니다.
  return { version: 1, region_code: regionCode, budget_status: 'unknown', budget_min_krw: null,
    budget_max_krw: null, budget_hard_limit: false, schedule_status: 'unknown', start_date: null,
    end_date: null, resources_status: 'unknown', resources_confirmed: '', resources_possible: '',
    constraints_status: 'unknown', hard_constraints: '',
    preferences: '', field_context: '', references: [] }
}

// 지역별 키를 사용해 강남구 초안과 다른 시군구 초안이 서로 덮어쓰지 않게 합니다.
const key = (code) => `tour-insight-planning-brief-${code}`
export function readPlanningDraft(code) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(key(code)) || 'null')
    if (saved?.brief?.region_code === code && saved.brief.version === 1 && Array.isArray(saved.brief.references)) {
      // 이전 초안에는 상태 필드가 없으므로, 이미 적은 내용이 사라지지 않게 한 번만 보정합니다.
      const legacy = saved.brief
      return {
        ...emptyPlanningBrief(code), ...legacy,
        resources_status: legacy.resources_status || (legacy.resources_confirmed || legacy.resources_possible ? 'known' : 'unknown'),
        constraints_status: legacy.constraints_status || (legacy.hard_constraints ? 'known' : 'unknown'),
      }
    }
  } catch { /* 손상된 초안은 다른 지역 정보로 대체하지 않고 새로 시작합니다. */ }
  return emptyPlanningBrief(code)
}
export function savePlanningDraft(brief) {
  // 첨부 본문은 생성 요청에만 쓰고 브라우저 초안에는 남기지 않습니다.
  const draft = { ...brief, references: [] }
  window.localStorage.setItem(key(brief.region_code), JSON.stringify({ brief: draft, saved_at: new Date().toISOString() }))
}
export function validatePlanningBrief(brief) {
  // 서버 Pydantic 검증 전에 같은 규칙을 한 번 적용해 사용자가 바로 오류를 알 수 있게 합니다.
  if (brief.budget_status !== 'unknown') {
    if (!Number.isSafeInteger(brief.budget_max_krw) || brief.budget_max_krw <= 0 || brief.budget_max_krw > 1e12) return '예산은 1원 이상 1조 원 이하의 정수로 입력해 주세요.'
    if (brief.budget_min_krw !== null && (!Number.isSafeInteger(brief.budget_min_krw) || brief.budget_min_krw <= 0 || brief.budget_min_krw > brief.budget_max_krw)) return '최소 예산은 최대 예산 이하로 입력해 주세요.'
  }
  if (brief.schedule_status !== 'unknown') {
    if (!brief.start_date || !brief.end_date) return '사업 시작일과 종료일을 모두 입력해 주세요.'
    if (brief.end_date < brief.start_date) return '종료일은 시작일보다 빠를 수 없습니다.'
  }
  return ''
}
export function briefBudget(brief) {
  // 입력 숫자를 요약 카드에서 읽기 좋은 ‘원’ 단위 문자열로 바꿉니다.
  if (!brief || brief.budget_status === 'unknown') return '미정 · AI가 규모 제안'
  if (!Number.isSafeInteger(brief.budget_max_krw) || brief.budget_max_krw <= 0) return '금액 입력 필요'
  const amount = (n) => `${Number(n).toLocaleString('ko-KR')}원`
  return `${brief.budget_min_krw ? amount(brief.budget_min_krw) + ' ~ ' : ''}${amount(brief.budget_max_krw)}${brief.budget_hard_limit ? ' 이내' : ''}`
}
export function briefPeriod(brief) {
  // 날짜 둘 중 하나만 입력된 상태는 저장하면 안 되므로 요약에도 ‘입력 필요’로 표시합니다.
  if (!brief || brief.schedule_status === 'unknown') return '미정 · AI가 일정 제안'
  return brief.start_date && brief.end_date ? `${brief.start_date} ~ ${brief.end_date}` : '날짜 입력 필요'
}
