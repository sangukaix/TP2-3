import { CheckCircle2, Download, FileText, LoaderCircle, Presentation, Save, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import WorkspaceAssistantPanel from '../components/WorkspaceAssistantPanel'
import WorkspaceShell from '../components/WorkspaceShell'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal, getAiStrategyReportJob, saveStoredStrategyReport } from '../api/dashboardApi'
import { clearActiveStrategyJob, downloadBlob, readActiveStrategyJob, readSavedReport, saveReport, useWorkspaceRegionData } from './tourismWorkspace'
import { readPlanningDraft } from '../features/planning/planningBrief'
import '../features/planning/planning.css'
import '../App.css'

/** 생성된 기획안을 페이지 안에서 검토·수정하고, AI 챗봇 제안을 반영한 뒤 저장하는 화면입니다. */
export default function TourismStrategyPage() {
  // 선택 지역과 해당 지역의 마지막 생성 작업을 여러 페이지에서 이어서 사용합니다.
  const { region } = useWorkspaceRegionData()
  const [report, setReport] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [jobMessage, setJobMessage] = useState('')
  const [downloadingFormat, setDownloadingFormat] = useState('')
  const [error, setError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const persistedJob = readActiveStrategyJob(region.code)
  const currentJob = activeJob?.region_code === region.code ? activeJob : persistedJob
  const storedReport = report?.region_name === region.name ? report : readSavedReport(region.code)
  const displayReport = currentJob ? null : storedReport
  const strategy = displayReport?.strategies?.[0]
  const loading = Boolean(currentJob)
  const planningBrief = displayReport ? displayReport.planning_brief : currentJob ? currentJob.planning_brief : readPlanningDraft(region.code)

  // 백그라운드 Agent 작업은 페이지를 떠나도 계속되고, 이 화면은 3초마다 완료 여부만 확인합니다.
  useEffect(() => {
    if (!currentJob?.job_id) return undefined
    let isActive = true
    const poll = async () => {
      try {
        const job = await getAiStrategyReportJob(region.code, currentJob.job_id)
        if (!isActive) return
        setJobMessage(job.message || '')
        if (job.status === 'completed' && job.report) {
          const stored = saveReport(region.code, { ...job.report, __savedEntryId: job.job_id })
          clearActiveStrategyJob(region.code)
          setReport(stored)
          setActiveJob(null)
        } else if (job.status === 'failed') {
          clearActiveStrategyJob(region.code)
          setActiveJob(null)
          setError(job.error || job.message || 'AI 전략기획서를 생성하지 못했습니다.')
        }
      } catch {
        if (isActive) setJobMessage('서버에서 기획안을 계속 생성 중입니다. 잠시 후 상태를 다시 확인합니다.')
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
    const updated = { ...first, ...patch, title: patch.strategy_title || first.title, implementation_steps: patch.implementation_steps?.length ? patch.implementation_steps : first.implementation_steps }
    const next = { ...current, summary: patch.summary || current.summary, strategies: [updated, ...current.strategies.slice(1)] }
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
          {loading && <section className="strategy-start strategy-start--loading"><span className="strategy-job-loader" aria-hidden="true"><i /><i /><LoaderCircle size={22} /></span><h3>전략을 만들고 있습니다.</h3><p>{jobMessage || '지역 지표 확인 → 공식 사례 조사 → 실행안 작성 → 품질 검토 순서로 진행 중입니다.'}</p><div className="strategy-job-flow"><span>원자료</span><i /><span>공식 사례</span><i /><span>기획안</span><i /><span>품질 검토</span></div><small>다른 페이지로 이동하거나 새 창을 열어도 서버에서 작업을 계속 진행합니다.</small></section>}
          {displayReport && strategy && <article className="strategy-output strategy-preview-frame">
            <header className="strategy-preview-header"><div><p>AI 전략기획안 · 편집 중</p><h2>{strategy.title}</h2></div><div><small>{saveMessage || '챗봇 수정 내용을 확인한 뒤 저장하세요.'}</small><button type="button" onClick={saveStrategy}><Save size={15} />기획안 저장하기</button></div></header>
            <div className="strategy-preview-body">
              <section className="strategy-summary"><p>핵심 제안</p><strong>{displayReport.summary}</strong></section>
              <div className="strategy-briefs"><article><span>문제 / 제안</span><p>{strategy.problem_to_solve}</p><small>{strategy.comparison_analysis}</small></article><article><span>해결 방법</span><p>{strategy.solution}</p></article></div>
              <section className="strategy-steps"><header><div><p>실행 로드맵</p><h3>5단계 집행 방법</h3></div><span>{strategy.timeframe}</span></header><ol>{strategy.implementation_steps?.map((step, index) => <li key={step.step || index}><i>{step.step || index + 1}</i><div><small>{step.schedule}</small><b>{step.task}</b><span>완료 기준 · {step.deliverable}</span></div></li>)}</ol></section>
              <section className="strategy-effect"><CheckCircle2 size={18} /><div><span>기대할 수 있는 변화</span><p>{strategy.expected_effect}</p></div></section>
              <div className="strategy-document-actions"><span><FileText size={16} />저장 후 문서 출력</span><button type="button" onClick={() => downloadPlan('docx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'docx' ? <LoaderCircle size={15} /> : <Download size={15} />}{downloadingFormat === 'docx' ? 'Word 생성 중…' : 'Word 다운로드'}</button><button type="button" className="is-pptx" onClick={() => downloadPlan('pptx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'pptx' ? <LoaderCircle size={15} /> : <Presentation size={15} />}{downloadingFormat === 'pptx' ? 'PowerPoint 생성 중…' : 'PowerPoint 다운로드'}</button></div>
            </div>
          </article>}
        </section>
        <WorkspaceAssistantPanel key={`${region.code}-${displayReport?.__savedEntryId || 'draft'}`} planningBrief={planningBrief} region={region} report={displayReport} onApplyPatch={applyPatch} />
      </div>
    </main>
  </WorkspaceShell>
}
