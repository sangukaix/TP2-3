import { MapPin } from 'lucide-react'
import { briefBudget, briefPeriod } from './planningBrief'

/** 초안과 저장 기획서가 같은 컴포넌트로 생성 조건을 보여 줍니다. */
export default function PlanningBriefSummary({ brief, regionName, compact = false, title }) {
  // 입력 폼 오른쪽 요약과 생성된 기획안의 조건 확인은 같은 컴포넌트를 재사용합니다.
  // 그래서 화면마다 예산·일정 표현 기준이 달라지는 일을 막습니다.
  if (!brief) return null
  return <section className={`planning-summary ${compact ? 'is-compact' : ''}`} aria-label="기획 조건 요약">
    <header><span><MapPin size={15} />{regionName}</span><h2>{title || (compact ? '기획 조건 요약' : '이번 기획의 여건')}</h2></header>
    <dl>
      <div><dt>예산</dt><dd>{briefBudget(brief)}<small>{brief.budget_status === 'indicative' ? '희망 예산' : 'AI가 사업 규모 제안'}</small></dd></div>
      <div><dt>일정</dt><dd>{briefPeriod(brief)}<small>{brief.schedule_status === 'fixed' ? '반드시 지킬 일정' : brief.schedule_status === 'flexible' ? '조정 가능한 일정' : '지역 특성과 계절을 함께 검토'}</small></dd></div>
      <div><dt>시설 · 인력</dt><dd>{brief.resources_status === 'unknown' ? '미정 · AI가 기반 제안' : brief.resources_confirmed || '입력하지 않음'}</dd></div>
      <div><dt>필수 조건</dt><dd>{brief.constraints_status === 'unknown' ? '미정 · AI가 조건 제안' : brief.hard_constraints || '입력하지 않음'}</dd></div>
      {brief.preferences && <div><dt>참고 선호</dt><dd>{brief.preferences}</dd></div>}
      {brief.field_context && <div><dt>현장 정보</dt><dd>{brief.field_context}</dd></div>}
      {brief.references?.length > 0 && <div><dt>참고자료</dt><dd>{brief.references.map((f) => <span key={f.name}>{f.name}<br /></span>)}</dd></div>}
    </dl>
  </section>
}
