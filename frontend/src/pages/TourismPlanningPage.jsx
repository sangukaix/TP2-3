import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, CalendarDays, Check, CircleHelp, Coins, Layers3, LoaderCircle, Save, ShieldCheck, Sparkles } from 'lucide-react'
import WorkspaceShell from '../components/WorkspaceShell'
import RegionWorkspacePicker from '../components/RegionWorkspacePicker'
import PlanningBriefSummary from '../features/planning/PlanningBriefSummary'
import { BUSINESS_DIRECTIONS, EXCLUDED_OPERATIONS, simplifiedDraft, threeMonthSchedule, savePlanningDraft, validatePlanningBrief } from '../features/planning/planningBrief'
import { readActiveStrategyJob, saveActiveStrategyJob, useWorkspaceRegionData } from './tourismWorkspace'
import { getStrategyGenerationReadiness, startAiStrategyReportJob } from '../api/dashboardApi'
import '../App.css'
import '../features/planning/planning.css'

// ‘미정/입력하기’처럼 서로 하나만 선택하는 버튼 그룹입니다.
// radio input 대신 버튼과 aria-pressed를 사용해 현재 선택을 더 분명하게 표시합니다.
function Choice({ label, value, options, onChange }) {
  return <div className="planning-choice" role="group" aria-label={label}>{options.map(([key, text]) =>
    <button key={key} type="button" aria-pressed={value === key} className={value === key ? 'is-selected' : ''} onClick={() => onChange(key)}>{value === key && <Check size={13} />}{text}</button>
  )}</div>
}
// 네 개의 사업 여건 카드가 같은 제목·도움말·아이콘 구조를 쓰도록 만든 공통 레이아웃입니다.
function Section({ number, icon: Icon, title, why, children }) {
  return <section className="planning-section"><header><span className="planning-section-icon"><Icon size={18} /></span><div><span className="planning-section-number">{number}</span><h2>{title}</h2></div><span className="planning-help" tabIndex="0" aria-label={why}><CircleHelp size={16} /><span>{why}</span></span></header>{children}</section>
}

function PlanningForm({ region, dataState, onDirtyChange, onSaveReady }) {
  // 입력 초안은 지역 코드별 localStorage에서 복원합니다.
  // 단, 첨부 문서 본문은 브라우저에 저장하지 않고 생성 요청 시에만 사용합니다.
  const [brief, setBrief] = useState(() => simplifiedDraft(region.code))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [freshness, setFreshness] = useState({ status: 'loading', can_generate: false, message: '최신 분석 데이터를 확인하고 있습니다.' })
  const submitting = useRef(false)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    onDirtyChange(dirty)
    if (!dirty) return undefined
    const guard = (event) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [dirty, onDirtyChange])
  const activeJob = readActiveStrategyJob(region.code)
  // 생성만 보호하고, 대시보드·저장 기획안 조회에는 영향을 주지 않는 서버 최신성 계약입니다.
  useEffect(() => {
    let active = true
    getStrategyGenerationReadiness(region.code, region.name)
      .then((result) => { if (active) setFreshness(result?.data_freshness || { status: 'unavailable', can_generate: false, message: '데이터 최신성 정보를 받지 못했습니다.' }) })
      .catch((requestError) => { if (active) setFreshness({ status: 'unavailable', can_generate: false, message: requestError.message }) })
    return () => { active = false }
  }, [region.code, region.name])
  // 모든 입력 변경은 한 함수로 모아 저장 전 경고(dirty 상태)와 안내 문구를 일관되게 갱신합니다.
  const update = (changes) => { setBrief((current) => ({ ...current, ...changes })); setDirty(true); setMessage(''); setError('') }
  // 서버 요청 전에 브라우저에서도 기본 형식(금액·날짜)을 먼저 검사합니다.
  const save = useCallback(() => {
    const problem = validatePlanningBrief(brief)
    if (problem) { setError(problem); return false }
    try { savePlanningDraft(brief); setDirty(false); setMessage('이 브라우저에 기획 조건을 저장했습니다.'); setError(''); return true }
    catch { setError('이 브라우저에 임시저장할 수 없습니다. 저장 공간과 브라우저 설정을 확인해 주세요.'); return false }
  }, [brief])
  // 상단의 임시저장 버튼도 같은 저장·검증 함수를 사용하도록 부모 화면에 함수를 전달합니다.
  useEffect(() => {
    onSaveReady?.(save)
    return () => onSaveReady?.(null)
  }, [onSaveReady, save])
  // 생성 버튼은 장시간 걸리는 AI 작업을 서버에 등록한 뒤 /strategy로 이동합니다.
  // 중복 클릭은 submitting ref로 막고, 실제 진행 상태는 작업 ID로 복원합니다.
  const generate = async (event) => {
    event.preventDefault()
    if (!activeJob && !freshness.can_generate) { setError(freshness.message); return }
    if (submitting.current || !save()) return
    submitting.current = true; setBusy(true)
    try {
      if (activeJob) { window.location.assign('/strategy'); return }
      // 입력한 조건의 복사본이 서버 작업에 전달됩니다. 작성 중 초안은 별도입니다.
      const job = await startAiStrategyReportJob(region.code, { region_name: region.name, planning_brief: brief })
      // 작업 ID만 브라우저에 남기고, 첨부 문서 본문은 서버 작업 중에만 사용합니다.
      saveActiveStrategyJob(job)
      window.location.assign('/strategy')
    } catch (requestError) { setError(requestError.message); submitting.current = false; setBusy(false) }
  }
  // 화면에서는 쉼표가 있는 금액도 허용하지만, 저장 값은 계산 가능한 정수 원 단위로 정규화합니다.
  const amountChange = (field, raw) => update({ [field]: raw.replace(/\D/g, '') ? Number(raw.replace(/\D/g, '')) : null })
  return <form className="planning-layout" onSubmit={generate}>
    <div className="planning-fields">
      <fieldset disabled={busy} className="planning-fieldset">
        <Section number="01" icon={Sparkles} title="사업 방향" why="공식 사례가 확보된 사업 유형 안에서 비교합니다.">
          <Choice label="사업 방향" value={brief.business_direction} options={BUSINESS_DIRECTIONS} onChange={(business_direction) => update({ business_direction })} />
          <p className="planning-hint">관광사업 아이디어를 제안합니다. 신축 건물·공원 등 시설 개발 계획은 지원하지 않습니다. KPI는 근거와 함께 제안하며 생성 후 조정할 수 있습니다.</p>
        </Section>
        <Section number="02" icon={Coins} title="참고 예산" why="예산 배분 예시이며 실행 가능성과 사업 효과를 보장하는 금액은 아닙니다.">
          <Choice label="예산 상태" value={brief.budget_status} options={[['unknown', '미정'], ['indicative', '참고 총액 입력']]} onChange={(budget_status) => update({ budget_status, budget_max_krw: null })} />
          {brief.budget_status !== 'unknown' && <label>참고 예산 총액<div className="planning-money"><input aria-label="참고 예산 총액" inputMode="numeric" value={brief.budget_max_krw?.toLocaleString('ko-KR') || ''} onChange={(e) => amountChange('budget_max_krw', e.target.value)} placeholder="예: 30,000,000" /><span>원</span></div></label>}
          <p className="planning-hint">입력 금액은 견적 예시의 항목별 배분에 반영합니다. 사업 규모·인력·KPI가 이 금액으로 달성된다는 뜻은 아닙니다.</p>
        </Section>
        <Section number="03" icon={CalendarDays} title="3개월 시범 운영" why="시작 월부터 준비·운영·평가를 포함한 3개월로 구성합니다.">
          <label>시작 월 <small>선택 · 비우면 이번 달 기준</small><input type="month" min={new Date().toISOString().slice(0, 7)} value={brief.start_date?.slice(0, 7) || ''} onChange={(e) => update(threeMonthSchedule(e.target.value))} /></label>
          <p className="planning-hint">전망 가능한 기간 안에서 선택해 주세요. 오래된 관측 자료나 너무 먼 일정은 생성 전에 안내합니다.</p>
        </Section>
        <Section number="04" icon={Layers3} title="활용할 자원" why="사용자가 제공한 정보로 참고하며 공식적으로 확인된 사실과 구분합니다.">
          <label>시설·행사·협력처·인력 <small>선택 · 300자</small><textarea rows="2" maxLength={300} value={brief.resources_confirmed} onChange={(e) => update({ resources_confirmed: e.target.value, resources_status: e.target.value ? 'known' : 'unknown' })} placeholder="예: 기존 관광안내소, 상인회 협력 가능, 운영 담당 2명" /></label>
        </Section>
        <Section number="05" icon={ShieldCheck} title="제외할 운영 방식" why="선택한 유형을 사례와 설계 후보에서 제외합니다.">
          {EXCLUDED_OPERATIONS.map(([value, label]) => <label className="planning-check" key={value}><input type="checkbox" checked={brief.excluded_operations.includes(value)} onChange={(e) => update({ excluded_operations: e.target.checked ? [...brief.excluded_operations, value] : brief.excluded_operations.filter((item) => item !== value) })} />{label}</label>)}
        </Section>
        <Section number="선택" icon={Layers3} title="현장 메모" why="사업 범위 안의 참고 정보입니다. 관측값이나 ML 예측을 바꾸지 않습니다.">
          <label>현장 정보와 선호 <small>500자 이내</small><textarea rows="3" maxLength={500} value={brief.field_context} onChange={(e) => update({ field_context: e.target.value })} placeholder="예: 기존 행사와 연계하고 싶음, 주말 가족 방문객 중심. 개인정보는 입력하지 마세요." /></label>
        </Section>
      </fieldset>
      {/* 빈 임시저장 영역은 제거하고, 필요한 상태 안내만 입력 카드 아래에 간결하게 표시합니다. */}
      {(error || message || dirty || dataState === 'error') && <div className="planning-inline-status" aria-live="polite">{error ? <p role="alert" className="planning-error">{error}</p> : (message || dirty) && <p>{message || '저장하지 않은 변경사항이 있습니다.'}</p>}
        {dataState === 'error' && <p className="planning-error">지역 원자료를 불러오지 못했습니다. 서버 연결을 확인해 주세요.</p>}</div>}
    </div>
    <aside className="planning-summary-column"><PlanningBriefSummary brief={brief} regionName={region.name} title="아래 조건으로 기획안 생성" />
      {freshness.status !== 'loading' && (freshness.missing_month_count > 0 || !freshness.can_generate) && <section className={`planning-freshness ${freshness.can_generate ? '' : 'is-blocked'}`} aria-live="polite"><strong>{freshness.can_generate ? '데이터 반영 안내' : '데이터 업데이트 필요'}</strong><p>{freshness.message}</p>{Array.isArray(freshness.required_steps) && freshness.required_steps.length > 0 && <ol>{freshness.required_steps.map((step) => <li key={step}>{step}</li>)}</ol>}</section>}
      <button type="submit" disabled={!activeJob && (busy || dataState !== 'ready' || !freshness.can_generate)} className="planning-primary planning-summary-generate">{busy ? <LoaderCircle className="planning-spinner" size={16} /> : <Sparkles size={16} />}{busy ? '생성 요청 중…' : activeJob ? '생성 중인 기획안 보기' : freshness.status === 'loading' ? '데이터 확인 중…' : freshness.can_generate ? '기획안 생성' : '데이터 업데이트 후 생성'}<ArrowRight size={16} /></button></aside>
  </form>
}

export default function TourismPlanningPage() {
  const { region, regions, chooseRegion, state } = useWorkspaceRegionData()
  const [dirty, setDirty] = useState(false)
  const [saveDraft, setSaveDraft] = useState(null)
  // 다른 지역으로 바꾸기 전, 아직 저장하지 않은 사업 여건이 있으면 한 번 확인합니다.
  const changeRegion = (code) => {
    if (code === region.code) return
    if (dirty && !window.confirm('저장하지 않은 변경사항이 있습니다. 저장하지 않고 지역을 변경할까요?')) return
    setDirty(false); chooseRegion(code)
  }
  return <WorkspaceShell><main className="tourism-work-page planning-page"><header className="work-page-header"><div><h1>{region.name}</h1></div><RegionWorkspacePicker region={region} regions={regions} label="분석지역 변경" onChange={changeRegion} /><button type="button" className="planning-header-save" disabled={!saveDraft} onClick={() => saveDraft?.()}><Save size={15} />임시저장</button></header><PlanningForm key={region.code} region={region} dataState={state} onDirtyChange={setDirty} onSaveReady={setSaveDraft} /></main></WorkspaceShell>
}
