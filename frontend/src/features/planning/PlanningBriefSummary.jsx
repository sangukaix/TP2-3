import { MapPin } from 'lucide-react'
import { briefBudget, briefPeriod, BUSINESS_DIRECTIONS, EXCLUDED_OPERATIONS, RESOURCE_OPTIONS, CONTEXT_OPTIONS, optionLabels } from './planningBrief'

/** 초안과 저장 기획서가 같은 컴포넌트로 생성 조건을 보여 줍니다. */
export default function PlanningBriefSummary({ brief, regionName, compact = false, title }) {
  // 입력 폼 오른쪽 요약과 생성된 기획안의 조건 확인은 같은 컴포넌트를 재사용합니다.
  // 그래서 화면마다 예산·일정 표현 기준이 달라지는 일을 막습니다.
  if (!brief) return null
  const guided = ['guided_v1', 'guided_v2'].includes(brief.input_profile)
  const choices = brief.input_profile === 'guided_v2'
  return <section className={`planning-summary ${compact ? 'is-compact' : ''}`} aria-label="기획 조건 요약">
    <header><span><MapPin size={15} />{regionName}</span><h2>{title || (compact ? '기획 조건 요약' : '이번 기획의 여건')}</h2></header>
    <dl>
      {guided && <div><dt>사업 방향</dt><dd>{BUSINESS_DIRECTIONS.find(([key]) => key === brief.business_direction)?.[1]}</dd></div>}
      <div><dt>예산</dt><dd>{briefBudget(brief)}<small>{guided ? '견적 예시 · 실행 가능성 보장 아님' : brief.budget_status === 'indicative' ? '희망 예산' : 'AI가 사업 규모 제안'}</small></dd></div>
      <div><dt>{choices ? '사업기간' : '일정'}</dt><dd>{briefPeriod(brief)}<small>{choices ? '한국 시간 · 다음 달부터 3개월' : brief.input_profile === 'guided_v1' ? '준비·운영·평가를 포함한 시범 기간' : brief.schedule_status === 'fixed' ? '반드시 지킬 일정' : brief.schedule_status === 'flexible' ? '조정 가능한 일정' : '지역 특성과 계절을 함께 검토'}</small></dd></div>
      <div><dt>시설 · 인력</dt><dd>{choices ? optionLabels(RESOURCE_OPTIONS, brief.resource_options) || '선택하지 않음' : brief.resources_status === 'unknown' ? '미정 · AI가 기반 제안' : brief.resources_confirmed || '입력하지 않음'}</dd></div>
      {!choices && <div><dt>제외 조건</dt><dd>{brief.input_profile === 'guided_v1' ? EXCLUDED_OPERATIONS.filter(([key]) => brief.excluded_operations?.includes(key)).map(([, label]) => label).join(' · ') || '없음' : brief.hard_constraints || '미정'}</dd></div>}
      {brief.preferences && <div><dt>참고 선호</dt><dd>{brief.preferences}</dd></div>}
      {choices && brief.context_options?.length > 0 && <div><dt>현장 정보와 선호</dt><dd>{optionLabels(CONTEXT_OPTIONS, brief.context_options)}</dd></div>}
      {!choices && brief.field_context && <div><dt>현장 정보</dt><dd>{brief.field_context}</dd></div>}
      {brief.references?.length > 0 && <div><dt>참고자료</dt><dd>{brief.references.map((f) => <span key={f.name}>{f.name}<br /></span>)}</dd></div>}
    </dl>
  </section>
}
