import { CheckCircle2, Download, FileText, LoaderCircle, Presentation, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import WorkspaceAssistantPanel from '../components/WorkspaceAssistantPanel'
import WorkspaceShell from '../components/WorkspaceShell'
import RegionWorkspacePicker from '../components/RegionWorkspacePicker'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal, getAiStrategyReportJob, startAiStrategyReportJob } from '../api/dashboardApi'
import { clearActiveStrategyJob, downloadBlob, readActiveStrategyJob, readSavedReport, saveActiveStrategyJob, saveReport, useWorkspaceRegionData } from './tourismWorkspace'
import '../App.css'

/** bid3 ProposalWorkspace처럼 좌측 작업 캔버스와 우측 AI 비서를 분리한 전략 기획 화면입니다. */
export default function TourismStrategyPage() {
  const { region, chooseRegion, dashboard } = useWorkspaceRegionData()
  const [report, setReport] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [jobMessage, setJobMessage] = useState('')
  const [downloadingFormat, setDownloadingFormat] = useState('')
  const [error, setError] = useState('')
  // 현재 지역의 작업만 상태값으로 우선하고, 페이지를 새로 열면 localStorage에 남긴 작업 ID를 복구합니다.
  const persistedJob = readActiveStrategyJob(region.code)
  const currentJob = activeJob?.region_code === region.code ? activeJob : persistedJob
  const storedReport = report?.region_name === region.name ? report : readSavedReport(region.code)
  const displayReport = currentJob ? null : storedReport
  const strategy = displayReport?.strategies?.[0]
  const loading = Boolean(currentJob)

  // polling은 화면을 떠날 때만 멈추며, 서버에서 실행 중인 Agent 작업 자체는 취소하지 않습니다.
  useEffect(() => {
    if (!currentJob?.job_id) return undefined
    let isActive = true
    const poll = async () => {
      try {
        const job = await getAiStrategyReportJob(region.code, currentJob.job_id)
        if (!isActive) return
        setJobMessage(job.message || '')
        if (job.status === 'completed' && job.report) {
          // 여러 탭에서 같은 완료 응답을 받아도 job_id를 저장 ID로 써 한 건만 갱신합니다.
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
        if (!isActive) return
        // 페이지 이동·일시적인 네트워크 오류로 서버 작업을 지우지 않습니다. 다음 polling에서 다시 확인합니다.
        setJobMessage('서버에서 기획안을 계속 생성 중입니다. 잠시 후 상태를 다시 확인합니다.')
      }
    }
    poll()
    const timer = window.setInterval(poll, 3000)
    return () => { isActive = false; window.clearInterval(timer) }
  }, [currentJob?.job_id, region.code])

  const generate = async () => {
    setError('')
    try {
      const job = await startAiStrategyReportJob(region.code, { region_name: region.name })
      saveActiveStrategyJob(job)
      setReport(null)
      setJobMessage(job.message || '')
      setActiveJob(job)
    } catch (requestError) { setError(requestError.message) }
  }
  const applyPatch = (patch) => {
    const current = displayReport
    const first = current?.strategies?.[0]
    if (!first) return
    const updated = { ...first, ...patch, implementation_steps: patch.implementation_steps?.length ? patch.implementation_steps : first.implementation_steps }
    const next = { ...current, summary: patch.summary || current.summary, strategies: [updated, ...current.strategies.slice(1)] }
    setReport(saveReport(region.code, next))
  }
  const downloadPlan = async (format) => {
    if (!displayReport) return
    setDownloadingFormat(format); setError('')
    try {
      const blob = format === 'docx' ? await downloadAiStrategyProposal(region.code, displayReport) : await downloadAiStrategyPresentation(region.code, displayReport)
      downloadBlob(blob, `${region.name.replaceAll(' ', '-')}-관광-전략기획안.${format}`)
    } catch (requestError) { setError(requestError.message) } finally { setDownloadingFormat('') }
  }

  return <WorkspaceShell onOpenAssistant={() => document.querySelector('.workspace-chat textarea')?.focus()}>
    <main className="tourism-work-page">
      <header className="work-page-header"><div><h1>AI 전략기획</h1><span>관측된 문제와 공식 근거를 연결해 실행 가능한 지역관광 기획안을 만듭니다.</span></div><RegionWorkspacePicker region={region} onChange={(code) => { chooseRegion(code); setReport(null); setActiveJob(null); setError('') }} /></header>
      <div className="strategy-workspace"><section className="strategy-canvas"><header className="strategy-project-header"><div><h2>{region.name}</h2><p>{dashboard?.latest_month || '최신 월'} 원자료와 공식 참고자료를 함께 검토합니다.</p></div></header>
        {error && <p className="work-error">{error}</p>}
        {!displayReport && !loading && <section className="strategy-start"><span><Sparkles size={21} /></span><h3>AI 전략기획을 시작할 준비가 되었습니다.</h3><p>지역 원자료, 공식 관광 API와 검수된 사례를 Agent가 나누어 조사한 뒤 한 개의 통합 실행안으로 정리합니다.</p><button type="button" onClick={generate}>AI 전략기획 생성</button></section>}
        {loading && <section className="strategy-start strategy-start--loading"><span className="strategy-job-loader" aria-hidden="true"><i /><i /><LoaderCircle size={22} /></span><h3>전략을 만들고 있습니다.</h3><p>{jobMessage || '지역 지표 확인 → 공식 사례 조사 → 실행안 작성 → 품질 검토 순서로 진행 중입니다.'}</p><div className="strategy-job-flow"><span>원자료</span><i /><span>공식 사례</span><i /><span>기획안</span><i /><span>품질 검토</span></div><small>다른 페이지로 이동하거나 새 창을 열어도 서버에서 작업을 계속 진행합니다.</small></section>}
        {displayReport && strategy && <div className="strategy-output"><section className="strategy-summary"><p>핵심 제안</p><h3>{strategy.title}</h3><strong>{displayReport.summary}</strong></section><div className="strategy-briefs"><article><span>문제 / 제안</span><p>{strategy.problem_to_solve}</p><small>{strategy.comparison_analysis}</small></article><article><span>해결 방법</span><p>{strategy.solution}</p></article></div><section className="strategy-steps"><header><div><p>실행 로드맵</p><h3>5단계 집행 방법</h3></div><span>{strategy.timeframe}</span></header><ol>{strategy.implementation_steps?.map((step, index) => <li key={step.step || index}><i>{step.step || index + 1}</i><div><small>{step.schedule}</small><b>{step.task}</b><span>완료 기준 · {step.deliverable}</span></div></li>)}</ol></section><section className="strategy-effect"><CheckCircle2 size={18} /><div><span>기대할 수 있는 변화</span><p>{strategy.expected_effect}</p></div></section><div className="strategy-document-actions"><span><FileText size={16} />기획서 출력</span><button type="button" onClick={() => downloadPlan('docx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'docx' ? <LoaderCircle size={15} /> : <Download size={15} />}{downloadingFormat === 'docx' ? 'Word 생성 중…' : 'Word 다운로드'}</button><button type="button" className="is-pptx" onClick={() => downloadPlan('pptx')} disabled={Boolean(downloadingFormat)}>{downloadingFormat === 'pptx' ? <LoaderCircle size={15} /> : <Presentation size={15} />}{downloadingFormat === 'pptx' ? 'PowerPoint 생성 중…' : 'PowerPoint 다운로드'}</button></div></div>}
      </section><WorkspaceAssistantPanel region={region} report={displayReport} onApplyPatch={applyPatch} /></div>
    </main>
  </WorkspaceShell>
}
