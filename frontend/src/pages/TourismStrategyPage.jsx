import { CheckCircle2, Download, FileText, LoaderCircle, Presentation, Save, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import WorkspaceAssistantPanel from '../components/WorkspaceAssistantPanel'
import WorkspaceShell from '../components/WorkspaceShell'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal, getAiStrategyReportJob, saveStoredStrategyReport } from '../api/dashboardApi'
import { clearActiveStrategyJob, downloadBlob, readActiveStrategyJob, readSavedReport, saveReport, useWorkspaceRegionData } from './tourismWorkspace'
import { readPlanningDraft } from '../features/planning/planningBrief'
import { applyReportPatch } from '../features/planning/applyReportPatch'
import '../features/planning/planning.css'
import '../App.css'

/** 아이디어 제안 화면에서는 편집 가능한 범위를 간단히 안내합니다. */
function StrategyQualityNotice({ report }) {
  const decision = report.planning_decision || {}
  const candidates = (decision.design_candidates || []).filter((row) => row.case_source_ids?.length)
  return <section className="strategy-quality-notice is-approved" aria-label="챗봇 수정 안내">
    <strong>챗봇으로 기획안을 조정하세요</strong>
    <ul><li>목표 KPI 증가율과 예상 견적</li><li>사업 소개 문장과 홍보 방식</li><li>현재 사업의 참여 범위와 실행 단계</li></ul>
    <p>관측값·ML 예측값·공식 사례 수치는 유지됩니다. 목표와 견적은 계획 가정입니다.</p>
    {candidates.length > 0 && <details><summary>근거가 연결된 아이디어 {candidates.length}개</summary><div className="strategy-candidate-list">{candidates.map((candidate) => <article key={candidate.candidate_id}><b>{candidate.candidate_id === decision.selected_candidate_id ? '현재 제안 · ' : '다른 아이디어 · '}{candidate.title}</b><p>{candidate.mechanism}</p></article>)}</div></details>}
  </section>
}

/** 생성된 기획안을 페이지 안에서 검토·수정하고, AI 챗봇 제안을 반영한 뒤 저장하는 화면입니다. */
export default function TourismStrategyPage() {
  // 선택 지역과 해당 지역의 마지막 생성 작업을 여러 페이지에서 이어서 사용합니다.
  const { region } = useWorkspaceRegionData()
  const [report, setReport] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [jobProgress, setJobProgress] = useState(null)
  const [downloadingFormat, setDownloadingFormat] = useState('')
  const [error, setError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const persistedJob = readActiveStrategyJob(region.code)
  const currentJob = activeJob?.region_code === region.code ? activeJob : persistedJob
  const persistedReport = useMemo(() => readSavedReport(region.code), [region.code])
  const storedReport = report?.region_name === region.name ? report : persistedReport
  const displayReport = currentJob ? null : storedReport
  const strategy = displayReport?.strategies?.[0]
  const loading = Boolean(currentJob)
  const progress = jobProgress?.jobId === currentJob?.job_id ? jobProgress : null
  const progressStep = progress?.step
  const jobMessage = progress?.message || '서버에서 현재 진행 단계를 확인하고 있습니다.'
  const planningBrief = displayReport ? displayReport.planning_brief : currentJob ? currentJob.planning_brief : readPlanningDraft(region.code)

  const needsPreparation = Boolean(displayReport && !displayReport.reference_estimate?.items)
  useEffect(() => {
    if (!needsPreparation) return undefined
    let active = true
    fetch('/ai/v1/strategy-idea-preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(displayReport) })
      .then((response) => { if (!response.ok) throw new Error('목표·견적 미리보기를 불러오지 못했습니다.'); return response.json() })
      .then((prepared) => { if (active) setReport({ ...displayReport, ...prepared }) })
      .catch((error) => { if (active) setError(error.message) })
    return () => { active = false }
  }, [displayReport, needsPreparation])

  // 백그라운드 Agent 작업은 페이지를 떠나도 계속되고, 이 화면은 3초마다 완료 여부만 확인합니다.
  useEffect(() => {
    if (!currentJob?.job_id) return undefined
    let isActive = true
    const poll = async () => {
      try {
        const job = await getAiStrategyReportJob(region.code, currentJob.job_id)
        if (!isActive) return
        setJobProgress({ jobId: currentJob.job_id, step: job.progress_step, message: job.message || '' })
        if (job.status === 'completed' && job.report) {
          const completed = { ...job.report, __savedEntryId: job.job_id }
          try {
            setReport(saveReport(region.code, completed))
          } catch {
            // 브라우저 저장공간이 부족해도 서버가 만든 본문은 현재 화면에서 확인할 수 있다.
            setReport(completed)
            setError('기획안은 생성됐지만 브라우저에 보관하지 못했습니다. 내용을 확인한 뒤 서버 저장 또는 문서 다운로드를 이용해 주세요.')
          } finally {
            clearActiveStrategyJob(region.code)
            setActiveJob(null)
          }
        } else if (job.status === 'completed') {
          clearActiveStrategyJob(region.code)
          setActiveJob(null)
          setError('완료된 기획안 본문을 불러오지 못했습니다. 같은 조건으로 다시 생성해 주세요.')
        } else if (job.status === 'failed') {
          clearActiveStrategyJob(region.code)
          setActiveJob(null)
          setError(job.error || job.message || 'AI 전략기획서를 생성하지 못했습니다.')
        }
      } catch (requestError) {
        if (!isActive) return
        if (requestError?.status === 404) {
          clearActiveStrategyJob(region.code)
          setActiveJob(null)
          setError('이전 생성 작업을 서버에서 찾지 못했습니다. 입력 조건은 유지되므로 다시 생성해 주세요.')
        } else {
          setJobProgress({ jobId: currentJob.job_id, step: null, message: '진행 상태 연결이 지연되고 있습니다. 잠시 후 서버 상태를 다시 확인합니다.' })
        }
      }
    }
    poll()
    const timer = window.setInterval(poll, 3000)
    return () => { isActive = false; window.clearInterval(timer) }
  }, [currentJob?.job_id, region.code])

  const generate = () => window.location.assign('/planning')

  // 챗봇 수정안은 즉시 화면 미리보기에 반영하고, 최종 저장은 사용자가 저장 버튼을 눌렀을 때만 합니다.
  const applyPatch = (patch) => {
    const current = displayReport
    const first = current?.strategies?.[0]
    if (!first) return
    // 본문이 바뀌면 이전 초안에 부여했던 승인 배지를 계속 표시하지 않습니다.
    const next = applyReportPatch(current, patch)
    setReport(saveReport(region.code, next))
    setSaveMessage('수정 내용을 확인한 뒤 저장하세요.')
  }

  const downloadPlan = async (format) => {
    if (!displayReport) return
    setDownloadingFormat(format); setError('')
    try {
      const blob = format === 'docx' ? await downloadAiStrategyProposal(region.code, displayReport) : await downloadAiStrategyPresentation(region.code, displayReport)
      downloadBlob(blob, `${region.name.replaceAll(' ', '-')}-관광-전략기획안.${format}`)
    } catch (requestError) { setError(requestError.message) } finally { setDownloadingFormat('') }
  }

  // MySQL 저장은 챗봇 반영 후 사용자가 직접 확정합니다.
  const saveStrategy = async () => {
    if (!displayReport?.__savedEntryId) { setError('저장할 기획안을 먼저 생성해 주세요.'); return }
    setError(''); setSaveMessage('')
    try {
      const stored = saveReport(region.code, displayReport)
      await saveStoredStrategyReport(stored.__savedEntryId, region.code, stored)
      setReport(stored)
      setSaveMessage('기획안을 저장했습니다.')
    } catch (requestError) { setError(requestError.message) }
  }

  return <WorkspaceShell>
    <main className="tourism-work-page strategy-page">
      <header className="work-page-header strategy-page-header"><div><h1>{region.name}</h1></div></header>
      <div className="strategy-workspace">
        <section className="strategy-canvas">
          {error && <p className="work-error">{error}</p>}
          {displayReport?.generation_mode === 'offline_sample' && <p className="work-error">오프라인 테스트 결과입니다. 입력 여건에 맞춘 AI 조사·기획은 실행되지 않았습니다.</p>}
          {!displayReport && !loading && <section className="strategy-start"><span><Sparkles size={21} /></span><h3>지역에 필요한 사업을 AI가 제안합니다.</h3><p>예산·일정·실행 여건을 확인한 뒤, 지역 데이터와 공식 사례를 조사해 기획안을 만듭니다. 모르는 조건은 미정으로 시작할 수 있습니다.</p><button type="button" onClick={generate}>사업 여건 입력하고 시작</button></section>}
          {loading && <section className="strategy-start strategy-start--loading"><span className="strategy-job-loader" aria-hidden="true"><i /><i /><LoaderCircle size={22} /></span><h3>기획서 초안을 생성중입니다</h3><p role="status" aria-live="polite">{jobMessage}</p><div className="strategy-job-flow" aria-label="기획서 생성 진행 단계">{['데이터 분석', '공식사례 확인', '기획안 생성', '품질검토'].map((label, index) => <div className="strategy-job-stage" key={label}><span className={Number.isInteger(progressStep) && index < progressStep ? 'is-complete' : index === progressStep ? 'is-current' : ''} aria-current={index === progressStep ? 'step' : undefined}>{Number.isInteger(progressStep) && index < progressStep && <CheckCircle2 size={12} aria-hidden="true" />}{label}<b className="strategy-job-sr">{Number.isInteger(progressStep) && index < progressStep ? ' 완료' : index === progressStep ? ' 진행 중' : ' 대기'}</b></span>{index < 3 && <i className={Number.isInteger(progressStep) && index < progressStep ? 'is-complete' : ''} aria-hidden="true" />}</div>)}</div><small>다른 페이지로 이동하거나 새 창을 열어도 서버에서 작업을 계속 진행합니다.</small></section>}
          {displayReport && strategy && <article className="strategy-output strategy-preview-frame">
            <header className="strategy-preview-header"><div><p>AI 전략기획안 · 편집 중</p><h2>{strategy.title}</h2></div><div><small>{saveMessage || '챗봇 수정 내용을 확인한 뒤 저장하세요.'}</small><button type="button" onClick={saveStrategy}><Save size={15} />기획안 저장하기</button></div></header>
            <div className="strategy-preview-body">
              <StrategyQualityNotice report={displayReport} />
              <section className="strategy-summary"><p>핵심 제안</p><strong>{displayReport.summary?.replace(/\s*·?\s*코드 점검에서 실행·근거 보완 항목이 확인되었습니다\.?/g, '')}</strong></section>
              <div className="strategy-briefs"><article><span>문제 / 제안</span><p>{strategy.problem_to_solve}</p><small>{strategy.comparison_analysis}</small></article><article><span>해결 방법</span><p>{strategy.solution}</p></article></div>
              <section className="strategy-steps"><header><div><p>실행 로드맵</p><h3>5단계 집행 방법</h3></div><span>{strategy.timeframe}</span></header><ol>{strategy.implementation_steps?.map((step, index) => <li key={step.step || index}><i>{step.step || index + 1}</i><div><small>{step.schedule}</small><b>{step.task}</b><span>완료 기준 · {step.deliverable}</span></div></li>)}</ol></section>
              <section className="strategy-effect"><CheckCircle2 size={18} /><div><span>기대할 수 있는 변화</span><p>{strategy.expected_effect}</p></div></section>
              <section className="strategy-summary"><p>조정 가능한 목표 KPI</p><strong>최종월 ML 전망 대비 방문 +{displayReport.execution_scenario?.visitor_target_pct ?? 5}% · 소비 +{displayReport.execution_scenario?.spending_target_pct ?? 5}%</strong><p>목표율은 아래 사례 근거와 계획 가정으로 제안합니다. 사업 효과를 예측한 수치가 아니라 챗봇으로 조정할 수 있는 계획 목표입니다. 월별 목표는 최종월까지 단계적으로 적용합니다.</p>{displayReport.target_proposal_basis?.explanation && <p>{displayReport.target_proposal_basis.explanation}</p>}</section>
              <div className="strategy-briefs"><article><span>예상 견적 · 실제 금액과 다를 수 있습니다</span>{displayReport.reference_estimate?.items ? <><strong>총 {displayReport.reference_estimate.total_krw.toLocaleString()}원</strong><ul>{displayReport.reference_estimate.items.map((row) => <li key={row.name}>{row.name} · {row.amount.toLocaleString()}원</li>)}</ul></> : <p>{strategy.budget}</p>}</article><article><span>성과 측정 방법</span><p>{strategy.kpi}</p></article></div>
              <div className="strategy-document-actions"><span><FileText size={16} />저장 후 문서 출력</span><button type="button" onClick={() => downloadPlan('docx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'docx' ? <LoaderCircle size={15} /> : <Download size={15} />}{downloadingFormat === 'docx' ? 'Word 생성 중…' : 'Word 다운로드'}</button><button type="button" className="is-pptx" onClick={() => downloadPlan('pptx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'pptx' ? <LoaderCircle size={15} /> : <Presentation size={15} />}{downloadingFormat === 'pptx' ? 'PowerPoint 생성 중…' : 'PowerPoint 다운로드'}</button></div>
            </div>
          </article>}
        </section>
        <WorkspaceAssistantPanel key={`${region.code}-${displayReport?.__savedEntryId || 'draft'}`} planningBrief={planningBrief} region={region} report={displayReport} onApplyPatch={applyPatch} />
      </div>
    </main>
  </WorkspaceShell>
}
