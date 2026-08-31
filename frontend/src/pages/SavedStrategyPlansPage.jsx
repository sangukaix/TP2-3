import { ChevronLeft, ChevronRight, Download, Eye, FileText, Presentation, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import WorkspaceShell from '../components/WorkspaceShell'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal } from '../api/dashboardApi'
import { downloadBlob, listSavedReports, readSavedReport } from './tourismWorkspace'
import '../App.css'

function formatSavedDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
}

/** bid3의 저장 공고 목록처럼, 생성한 관광 전략기획서를 다시 열고 문서로 받는 기록 게시판입니다. */
export default function SavedStrategyPlansPage() {
  const [plans, setPlans] = useState(listSavedReports)
  const [selectedPlan, setSelectedPlan] = useState(null)
  const [downloading, setDownloading] = useState('')
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)
  // 게시판 행의 고유 reportKey로 읽어야 같은 지역의 이전 기획안도 정확히 다시 열립니다.
  const selectedReport = selectedPlan ? readSavedReport(selectedPlan) : null
  const strategy = selectedReport?.strategies?.[0]
  const filteredPlans = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase('ko-KR')
    if (!keyword) return plans
    return plans.filter((plan) => `${plan.regionName} ${plan.title} ${plan.summary}`.toLocaleLowerCase('ko-KR').includes(keyword))
  }, [plans, query])
  const pageCount = Math.max(1, Math.ceil(filteredPlans.length / pageSize))
  const currentPage = Math.min(page, pageCount)
  const visiblePlans = filteredPlans.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  // 기록이 없는 상태도 실제 업무 게시판처럼 기본 10개 행의 높이를 유지합니다.
  const blankRowCount = query ? 0 : Math.max(0, pageSize - visiblePlans.length)

  const download = async (plan, format) => {
    const report = readSavedReport(plan)
    if (!report) { setError('저장된 기획안 본문을 찾지 못했습니다.'); return }
    setDownloading(`${plan.regionCode}-${format}`); setError('')
    try {
      const blob = format === 'docx' ? await downloadAiStrategyProposal(plan.regionCode, report) : await downloadAiStrategyPresentation(plan.regionCode, report)
      downloadBlob(blob, `${plan.regionName.replaceAll(' ', '-')}-관광-전략기획안.${format}`)
    } catch (requestError) {
      setError(requestError.message)
    } finally { setDownloading('') }
  }

  return <WorkspaceShell onOpenAssistant={() => window.location.assign('/strategy')}>
    <main className="tourism-work-page saved-plans-page">
      <header className="work-page-header"><div><h1>저장된 기획서</h1><span>한 번 생성한 결과는 이 게시판에서 다시 열고 내려받을 수 있습니다.</span></div><a className="saved-plans-create" href="/strategy"><FileText size={15} />새 기획안 만들기</a></header>
      {error && <p className="work-error">{error}</p>}
      <section className="saved-plan-board board-modern">
        <header><div><h2>저장된 전략기획서 <b>{plans.length}</b>건</h2></div><button type="button" onClick={() => { setPlans(listSavedReports()); setPage(1) }}>새로고침</button></header>
        <div className="saved-board-toolbar"><label>표시 <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }}><option value="10">10</option><option value="20">20</option></select>건</label><label className="saved-board-search"><Search size={14} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1) }} placeholder="지역 또는 기획안 검색" /></label></div>
        <div className="saved-plan-table">
          <div className="saved-plan-table-head"><span>번호</span><span>지역</span><span>기획안 제목</span><span>생성일</span><span>문서</span><span>작업</span></div>
          {visiblePlans.map((plan, index) => <article key={`modern-${plan.entryId || plan.regionCode}-${plan.savedAt}`}><i className="saved-plan-number">{filteredPlans.length - ((currentPage - 1) * pageSize + index)}</i><div className="saved-plan-region"><b>{plan.regionName}</b></div><div className="saved-plan-title"><strong>{plan.title}</strong></div><time>{formatSavedDate(plan.savedAt)}</time><span className="saved-plan-formats" aria-label="Word와 PowerPoint 문서 지원"><FileText size={15} /><Presentation size={15} /></span><div className="saved-plan-actions"><button type="button" onClick={() => setSelectedPlan(plan)}><Eye size={14} />보기</button><button type="button" disabled={Boolean(downloading)} onClick={() => download(plan, 'docx')}><Download size={14} />Word</button><button type="button" disabled={Boolean(downloading)} onClick={() => download(plan, 'pptx')}><Presentation size={14} />PPT</button></div></article>)}
          {Array.from({ length: blankRowCount }, (_, index) => <article className="saved-plan-blank-row" key={`blank-${index}`} aria-hidden="true"><i /><div /><div /><time /><span /><div /></article>)}
          {query && visiblePlans.length === 0 && <p className="saved-plan-no-results">검색 결과가 없습니다.</p>}
        </div>
        <footer className="saved-plan-pagination"><span>전체 {filteredPlans.length}건</span><div><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1} aria-label="이전 페이지"><ChevronLeft size={15} /></button><b>{currentPage}</b><small>/ {pageCount}</small><button type="button" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={currentPage === pageCount} aria-label="다음 페이지"><ChevronRight size={15} /></button></div></footer>
      </section>
      {plans.length === 0 ? <section className="saved-plans-empty"><FileText size={25} /><h2>저장된 기획서가 없습니다.</h2><p>AI 전략기획 화면에서 기획안을 생성하면 이 목록에 자동으로 기록됩니다.</p><a href="/strategy">AI 전략기획 시작</a></section> : <section className="saved-plan-board"><header><div><p>기획서 기록</p><h2>저장된 전략기획서 <b>{plans.length}</b>건</h2></div><button type="button" onClick={() => { setPlans(listSavedReports()); setPage(1) }}>새로고침</button></header><div className="saved-board-toolbar"><label>표시 <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }}><option value="5">5</option><option value="10">10</option><option value="20">20</option></select>건</label><label className="saved-board-search"><Search size={14} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1) }} placeholder="지역 또는 기획안 검색" /></label></div><div className="saved-plan-table"><div className="saved-plan-table-head"><span>번호</span><span>지역</span><span>기획안 제목</span><span>생성일</span><span>상태</span><span>작업</span></div>{visiblePlans.map((plan, index) => <article key={plan.entryId || `${plan.regionCode}-${plan.savedAt}`}><i className="saved-plan-number">{filteredPlans.length - ((currentPage - 1) * pageSize + index)}</i><div className="saved-plan-region"><span><b>{plan.regionName}</b><small>관광 전략</small></span></div><div><strong>{plan.title}</strong><p>{plan.summary}</p></div><time>{formatSavedDate(plan.savedAt)}</time><span className="saved-plan-status">저장됨</span><div className="saved-plan-actions"><button type="button" onClick={() => setSelectedPlan(plan)}><Eye size={14} />보기</button><button type="button" disabled={Boolean(downloading)} onClick={() => download(plan, 'docx')}><Download size={14} />Word</button><button type="button" disabled={Boolean(downloading)} onClick={() => download(plan, 'pptx')}><Presentation size={14} />PPT</button></div></article>)}{visiblePlans.length === 0 && <p className="saved-plan-no-results">검색 결과가 없습니다.</p>}</div><footer className="saved-plan-pagination"><span>전체 {filteredPlans.length}건</span><div><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1} aria-label="이전 페이지"><ChevronLeft size={15} /></button><b>{currentPage}</b><small>/ {pageCount}</small><button type="button" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={currentPage === pageCount} aria-label="다음 페이지"><ChevronRight size={15} /></button></div></footer></section>}
      {selectedPlan && selectedReport && strategy && <div className="saved-plan-modal-backdrop" role="presentation" onMouseDown={() => setSelectedPlan(null)}><section className="saved-plan-modal" role="dialog" aria-modal="true" aria-label="저장된 기획서" onMouseDown={(event) => event.stopPropagation()}><button className="saved-plan-modal-close" type="button" onClick={() => setSelectedPlan(null)} aria-label="닫기"><X size={18} /></button><header><p>{selectedPlan.regionName} 관광 전략 기획안</p><h2>{strategy.title}</h2><span>{formatSavedDate(selectedPlan.savedAt)} 생성</span></header><section className="saved-plan-modal-summary"><b>핵심 제안</b><p>{selectedReport.summary}</p></section><div className="saved-plan-modal-grid"><article><b>문제 / 제안</b><p>{strategy.problem_to_solve}</p></article><article><b>해결 방법</b><p>{strategy.solution}</p></article></div><section className="saved-plan-modal-steps"><b>5단계 실행 방법</b><ol>{strategy.implementation_steps?.map((step) => <li key={step.step}><i>{step.step}</i><span><small>{step.schedule}</small>{step.task}</span></li>)}</ol></section><footer><button type="button" onClick={() => download(selectedPlan, 'docx')} disabled={Boolean(downloading)}><Download size={15} />Word 다운로드</button><button type="button" onClick={() => download(selectedPlan, 'pptx')} disabled={Boolean(downloading)}><Presentation size={15} />PowerPoint 다운로드</button></footer></section></div>}
    </main>
  </WorkspaceShell>
}
