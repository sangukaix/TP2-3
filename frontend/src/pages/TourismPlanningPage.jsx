import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, CalendarDays, Check, CircleHelp, Coins, Layers3, LoaderCircle, Paperclip, Save, ShieldCheck, Sparkles, X } from 'lucide-react'
import WorkspaceShell from '../components/WorkspaceShell'
import RegionWorkspacePicker from '../components/RegionWorkspacePicker'
import PlanningBriefSummary from '../features/planning/PlanningBriefSummary'
import { readPlanningDraft, savePlanningDraft, validatePlanningBrief } from '../features/planning/planningBrief'
import { readActiveStrategyJob, saveActiveStrategyJob, useWorkspaceRegionData } from './tourismWorkspace'
import { startAiStrategyReportJob, uploadPlanningReference } from '../api/dashboardApi'
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
  const [brief, setBrief] = useState(() => readPlanningDraft(region.code))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
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
  // 모든 입력 변경은 한 함수로 모아 저장 전 경고(dirty 상태)와 안내 문구를 일관되게 갱신합니다.
  const update = (changes) => { setBrief((current) => ({ ...current, ...changes })); setDirty(true); setMessage(''); setError('') }
  // 서버 요청 전에 브라우저에서도 기본 형식(금액·날짜)을 먼저 검사합니다.
  const save = useCallback(() => {
    const problem = validatePlanningBrief(brief)
    if (problem) { setError(problem); return false }
    try { savePlanningDraft(brief); setDirty(false); setMessage('이 브라우저에 기획 조건을 저장했습니다.'); setError(''); return true }
    catch { setError('브라우저 저장 공간이 부족합니다. 첨부자료를 줄여 다시 저장해 주세요.'); return false }
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
    if (submitting.current || uploading || !save()) return
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
  // 첨부는 서버에서 텍스트만 안전하게 추출한 후 state에 넣습니다.
  // 파일 원본은 서버·브라우저 저장소에 보관하지 않습니다.
  const attach = async (event) => {
    const file = event.target.files?.[0]; event.target.value = ''
    if (!file) return
    if (brief.references.length >= 3) { setError('참고자료는 최대 3개까지 첨부할 수 있습니다.'); return }
    setUploading(true); setError('')
    try {
      const reference = await uploadPlanningReference(file)
      setBrief((current) => ({ ...current, references: [...current.references.filter((f) => f.name !== reference.name), reference] }))
      setDirty(true)
    } catch (requestError) { setError(requestError.message) }
    finally { setUploading(false) }
  }
  // 화면에서는 쉼표가 있는 금액도 허용하지만, 저장 값은 계산 가능한 정수 원 단위로 정규화합니다.
  const amountChange = (field, raw) => update({ [field]: raw.replace(/\D/g, '') ? Number(raw.replace(/\D/g, '')) : null })
  return <form className="planning-layout" onSubmit={generate}>
    <div className="planning-fields">
      <fieldset disabled={busy} className="planning-fieldset">
        <Section number="01" icon={Coins} title="예산" why="희망 예산은 사업의 크기를 가늠하는 참고 조건입니다. AI가 임의로 확정 예산처럼 사용하지 않습니다.">
          <Choice label="예산 상태" value={brief.budget_status} options={[['unknown', '미정'], ['indicative', '희망 예산']]} onChange={(value) => update({ budget_status: value, ...(value === 'unknown' ? { budget_min_krw: null, budget_max_krw: null, budget_hard_limit: false } : {}) })} />
          {brief.budget_status !== 'unknown' ? <><div className="planning-input-row">
            <label>최소 금액 <small>선택</small><div className="planning-money"><input aria-label="최소 예산" inputMode="numeric" value={brief.budget_min_krw?.toLocaleString('ko-KR') || ''} onChange={(e) => amountChange('budget_min_krw', e.target.value)} placeholder="범위가 있을 때" /><span>원</span></div></label>
            <label>금액 또는 최대 금액<div className="planning-money"><input aria-label="최대 예산" inputMode="numeric" value={brief.budget_max_krw?.toLocaleString('ko-KR') || ''} onChange={(e) => amountChange('budget_max_krw', e.target.value)} placeholder="예: 30,000,000" /><span>원</span></div></label>
          </div><label className="planning-check"><input type="checkbox" checked={brief.budget_hard_limit} onChange={(e) => update({ budget_hard_limit: e.target.checked })} />이 금액을 반드시 넘지 않아야 합니다.</label></> : <p className="planning-hint">AI가 지역 여건에 맞춰 사업 규모와 비용 항목을 제안합니다.</p>}
        </Section>
        <Section number="02" icon={CalendarDays} title="사업 추진 시기" why="지역의 계절성과 준비 시간을 함께 검토하고, 실행 단계를 가능한 기간에 맞춰 설계합니다.">
          <Choice label="일정 상태" value={brief.schedule_status} options={[['unknown', '미정'], ['flexible', '희망 기간']]} onChange={(value) => update({ schedule_status: value, ...(value === 'unknown' ? { start_date: null, end_date: null } : {}) })} />
          {brief.schedule_status !== 'unknown' ? <div className="planning-input-row"><label>준비·사업 시작일<input type="date" value={brief.start_date || ''} onChange={(e) => update({ start_date: e.target.value || null })} /></label><label>운영 종료일<input type="date" min={brief.start_date || undefined} value={brief.end_date || ''} onChange={(e) => update({ end_date: e.target.value || null })} /></label></div> : <p className="planning-hint">시기가 정해지지 않았다면 지역에 맞는 운영 시기와 기간을 제안합니다.</p>}
        </Section>
        <Section number="03" icon={Layers3} title="시설 · 인력" why="현재 활용 가능한 시설과 인력을 알면, AI가 바로 시작할 일과 추가로 준비할 일을 구분할 수 있습니다.">
          <Choice label="시설·인력 입력 상태" value={brief.resources_status} options={[['unknown', '미정'], ['known', '입력하기']]} onChange={(value) => update({ resources_status: value, ...(value === 'unknown' ? { resources_confirmed: '', resources_possible: '' } : {}) })} />
          {brief.resources_status === 'known' ? <label className="planning-detail-field">현재 활용 가능한 시설·행사·인력 <small>선택</small><textarea rows="3" maxLength={1500} value={brief.resources_confirmed} onChange={(e) => update({ resources_confirmed: e.target.value })} placeholder="예: 보유 공간, 기존 행사, 운영 인력, 확정 협력처" /></label> : <p className="planning-hint">정보가 없어도 됩니다. AI가 필요한 운영 기반과 확보 순서를 제안합니다.</p>}
        </Section>
        <Section number="04" icon={ShieldCheck} title="필수 조건" why="운영 제한을 먼저 알면 실행하기 어려운 사업을 걸러내고, 가능한 대안을 찾을 수 있습니다.">
          <Choice label="필수 조건 입력 상태" value={brief.constraints_status} options={[['unknown', '미정'], ['known', '입력하기']]} onChange={(value) => update({ constraints_status: value, ...(value === 'unknown' ? { hard_constraints: '' } : {}) })} />
          {brief.constraints_status === 'known' ? <><div className="planning-constraint-examples" aria-label="작성 예시"><span>작성 예시</span>{['신규 시설 설치 제외', '추가 인력 투입 어려움', '야간 운영 제외'].map((text) => <i key={text}>{text}</i>)}</div><label className="planning-sr-only" htmlFor="hard-constraints">필수 조건</label><textarea id="hard-constraints" rows="3" maxLength={2000} value={brief.hard_constraints} onChange={(e) => update({ hard_constraints: e.target.value })} placeholder="제외할 방식, 인력·장소 제한, 반드시 준수할 정책 조건을 적어주세요." /></> : <p className="planning-hint">제한 사항이 정해지지 않았다면, AI가 지역 여건에 맞는 실행 조건을 함께 제안합니다.</p>}
        </Section>
        <details className="planning-section planning-extra"><summary>추가자료 <span>선택</span></summary>
          <label>AI가 고려하면 좋을 현장 정보<textarea rows="3" maxLength={2500} value={brief.field_context} onChange={(e) => update({ field_context: e.target.value })} placeholder="기존 사업의 경험, 주민·상인 의견, 연계할 행사 등 공개 데이터에 없는 상황" /></label>
          <label>참고할 선호 <small>필수 조건과 구분</small><textarea rows="2" maxLength={1000} value={brief.preferences} onChange={(e) => update({ preferences: e.target.value })} placeholder="꼭 정해두지 않아도 됩니다. 검토해 보고 싶은 분야나 방식이 있다면 알려주세요." /></label>
          <div className="planning-reference-heading"><div><span>참고문서</span><p>기획안 작성 시 참고가 가능한 데이터, 문서를 첨부해 주세요.</p></div></div>
          <div className="planning-upload"><label><Paperclip size={15} />{uploading ? '자료 읽는 중…' : '참고자료 첨부'}<input type="file" accept=".hwpx,.pdf,.docx,.txt,.md,.xlsx" disabled={uploading || brief.references.length >= 3} onChange={attach} /></label><small>한글(HWPX) · Word · PDF · TXT · Excel / 2MB, 6,000자 이하 / 최대 3개</small></div>
          <p className="planning-hint">첨부 내용은 기획안 생성 용도로만 사용되며, 데이터에 저장되지 않습니다. 개인정보·비공개 민감정보는 제외해 주세요.</p>
          {brief.references.map((file, index) => <div className="planning-reference" key={file.name}><details><summary>{file.name} <small>{file.text.length.toLocaleString()}자</small></summary><pre>{file.text}</pre></details><button type="button" aria-label={`${file.name} 제거`} onClick={() => update({ references: brief.references.filter((_, i) => i !== index) })}><X size={15} /></button></div>)}
        </details>
      </fieldset>
      {/* 빈 임시저장 영역은 제거하고, 필요한 상태 안내만 입력 카드 아래에 간결하게 표시합니다. */}
      {(error || message || dirty || dataState === 'error') && <div className="planning-inline-status" aria-live="polite">{error ? <p role="alert" className="planning-error">{error}</p> : (message || dirty) && <p>{message || '저장하지 않은 변경사항이 있습니다.'}</p>}
        {dataState === 'error' && <p className="planning-error">지역 원자료를 불러오지 못했습니다. 서버 연결을 확인해 주세요.</p>}</div>}
    </div>
    <aside className="planning-summary-column"><PlanningBriefSummary brief={brief} regionName={region.name} title="아래 조건으로 기획안 생성" /><button type="submit" disabled={busy || uploading || dataState !== 'ready'} className="planning-primary planning-summary-generate">{busy ? <LoaderCircle className="planning-spinner" size={16} /> : <Sparkles size={16} />}{busy ? '생성 요청 중…' : activeJob ? '생성 중인 기획안 보기' : '기획안 생성'}<ArrowRight size={16} /></button></aside>
  </form>
}

export default function TourismPlanningPage() {
  const { region, chooseRegion, state } = useWorkspaceRegionData()
  const [dirty, setDirty] = useState(false)
  const [saveDraft, setSaveDraft] = useState(null)
  // 다른 지역으로 바꾸기 전, 아직 저장하지 않은 사업 여건이 있으면 한 번 확인합니다.
  const changeRegion = (code) => {
    if (code === region.code) return
    if (dirty && !window.confirm('저장하지 않은 변경사항이 있습니다. 저장하지 않고 지역을 변경할까요?')) return
    setDirty(false); chooseRegion(code)
  }
  return <WorkspaceShell><main className="tourism-work-page planning-page"><header className="work-page-header"><div><h1>{region.name}</h1></div><RegionWorkspacePicker region={region} label="분석지역 변경" onChange={changeRegion} /><button type="button" className="planning-header-save" disabled={!saveDraft} onClick={() => saveDraft?.()}><Save size={15} />임시저장</button></header><PlanningForm key={region.code} region={region} dataState={state} onDirtyChange={setDirty} onSaveReady={setSaveDraft} /></main></WorkspaceShell>
}
