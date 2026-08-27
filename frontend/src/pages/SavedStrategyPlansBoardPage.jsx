import { ChevronLeft, ChevronRight, Download, FileText, Presentation, RotateCcw, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import WorkspaceShell from '../components/WorkspaceShell'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal } from '../api/dashboardApi'
import { downloadBlob, listSavedReports, readSavedReport } from './tourismWorkspace'
import '../App.css'

const ROWS_PER_PAGE = 10

function formatSavedDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

/** 참고 이미지처럼 단순한 표 중심으로 만든 저장 기획서 업무 게시판입니다. */
export default function SavedStrategyPlansBoardPage() {
  const [plans] = useState(listSavedReports)
  const [query, setQuery] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selectedYear, setSelectedYear] = useState('')
  const [page, setPage] = useState(1)
  const [selectedPlan, setSelectedPlan] = useState(null)
  const [downloading, setDownloading] = useState('')
  const [error, setError] = useState('')
  const selectedReport = selectedPlan ? readSavedReport(selectedPlan) : null
  const strategy = selectedReport?.strategies?.[0]

  const availableYears = useMemo(() => [...new Set(plans.map((plan) => new Date(plan.savedAt).getFullYear()).filter(Number.isFinite))].sort((a, b) => b - a), [plans])

  const filteredPlans = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase('ko-KR')
    return plans.filter((plan) => {
      const matchesKeyword = !keyword || `${plan.regionName} ${plan.title}`.toLocaleLowerCase('ko-KR').includes(keyword)
      const savedYear = new Date(plan.savedAt).getFullYear()
      return matchesKeyword && (!selectedYear || savedYear === Number(selectedYear))
    })
  }, [plans, query, selectedYear])
  const pageCount = Math.max(1, Math.ceil(filteredPlans.length / ROWS_PER_PAGE))
  const currentPage = Math.min(page, pageCount)
  const visiblePlans = filteredPlans.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE)
  const blankRows = (query || selectedYear) ? 0 : Math.max(0, ROWS_PER_PAGE - visiblePlans.length)

  const submitSearch = (event) => {
    event.preventDefault()
    setQuery(searchInput)
    setPage(1)
  }

  const resetSearch = () => {
    setSearchInput('')
    setQuery('')
    setSelectedYear('')
    setPage(1)
  }

  const download = async (plan, format) => {
    const report = readSavedReport(plan)
    if (!report) { setError('저장된 기획안 본문을 찾지 못했습니다.'); return }
    setDownloading(`${plan.entryId || plan.regionCode}-${format}`)
    setError('')
    try {
      const blob = format === 'docx'
        ? await downloadAiStrategyProposal(plan.regionCode, report)
        : await downloadAiStrategyPresentation(plan.regionCode, report)
      downloadBlob(blob, `${plan.regionName.replaceAll(' ', '-')}-관광-전략기획안.${format}`)
    } catch (requestError) {
      setError(requestError.message)
    } finally { setDownloading('') }
  }

  return (
    <WorkspaceShell>
      <main className="tourism-work-page saved-board-page">
        {error && <p className="work-error">{error}</p>}
        <section className="strategy-board-table" aria-label="저장된 관광 전략기획서 목록">
          <header className="strategy-board-title"><h1>저장된 관광 전략기획서</h1></header>
          <form className="strategy-board-search-form" onSubmit={submitSearch}>
            <b><i />검색조건</b>
            <select value={selectedYear} onChange={(event) => { setSelectedYear(event.target.value); setPage(1) }} aria-label="작성연도 선택"><option value="">작성연도</option>{availableYears.map((year) => <option key={year} value={year}>{year}</option>)}</select>
            <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="지역 또는 기획서 제목을 입력하세요" aria-label="지역 또는 기획서 제목 검색" />
            <button type="submit"><Search size={17} />조회</button>
            <button type="button" className="strategy-board-reset" onClick={resetSearch}><RotateCcw size={16} />조건비우기</button>
          </form>
          <p className="strategy-board-total"><i />총 <b>{filteredPlans.length}</b>건</p>
          <div className="strategy-board-grid strategy-board-head"><span>번호</span><span>작성연도</span><span>지역</span><span>제목</span><span>첨부파일</span><span>등록일</span></div>
          {visiblePlans.map((plan, index) => <div className="strategy-board-grid strategy-board-row" key={plan.entryId || `${plan.regionCode}-${plan.savedAt}`}><span>{filteredPlans.length - ((currentPage - 1) * ROWS_PER_PAGE + index)}</span><span>{new Date(plan.savedAt).getFullYear() || '-'}</span><span>{plan.regionName}</span><button type="button" onClick={() => setSelectedPlan(plan)}>{plan.title}</button><span className="strategy-board-files"><button type="button" onClick={() => download(plan, 'docx')} disabled={Boolean(downloading)} title="Word 다운로드"><FileText size={17} /></button><button type="button" onClick={() => download(plan, 'pptx')} disabled={Boolean(downloading)} title="PowerPoint 다운로드"><Presentation size={17} /></button></span><time>{formatSavedDate(plan.savedAt)}</time></div>)}
          {Array.from({ length: blankRows }, (_, index) => <div className="strategy-board-grid strategy-board-row is-blank" key={`blank-${index}`} aria-hidden="true"><span /><span /><span /><span /><span /><span /></div>)}
          {(query || selectedYear) && visiblePlans.length === 0 && <p className="strategy-board-no-result">검색 결과가 없습니다.</p>}
          <div className="strategy-board-bottom">
            <a href="/strategy"><FileText size={14} />기획안 만들기</a>
            <nav aria-label="페이지 이동"><button type="button" disabled={currentPage === 1} onClick={() => setPage(1)} aria-label="첫 페이지"><ChevronLeft size={14} /><ChevronLeft size={14} /></button><button type="button" disabled={currentPage === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} aria-label="이전 페이지"><ChevronLeft size={15} /></button><b>{currentPage}</b>{currentPage < pageCount && <button type="button" onClick={() => setPage(currentPage + 1)}>{currentPage + 1}</button>}<button type="button" disabled={currentPage === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} aria-label="다음 페이지"><ChevronRight size={15} /></button><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(pageCount)} aria-label="마지막 페이지"><ChevronRight size={14} /><ChevronRight size={14} /></button></nav>
          </div>
        </section>
        {selectedPlan && selectedReport && strategy && <div className="saved-plan-modal-backdrop" role="presentation" onMouseDown={() => setSelectedPlan(null)}><section className="saved-plan-modal" role="dialog" aria-modal="true" aria-label="저장된 기획서" onMouseDown={(event) => event.stopPropagation()}><button className="saved-plan-modal-close" type="button" onClick={() => setSelectedPlan(null)} aria-label="닫기"><X size={18} /></button><header><p>{selectedPlan.regionName} 관광 전략 기획안</p><h2>{strategy.title}</h2><span>{formatSavedDate(selectedPlan.savedAt)} 생성</span></header><section className="saved-plan-modal-summary"><b>핵심 제안</b><p>{selectedReport.summary}</p></section><div className="saved-plan-modal-grid"><article><b>문제 / 제안</b><p>{strategy.problem_to_solve}</p></article><article><b>해결 방법</b><p>{strategy.solution}</p></article></div><section className="saved-plan-modal-steps"><b>5단계 실행 방법</b><ol>{strategy.implementation_steps?.map((step) => <li key={step.step}><i>{step.step}</i><span><small>{step.schedule}</small>{step.task}</span></li>)}</ol></section><footer><button type="button" onClick={() => download(selectedPlan, 'docx')} disabled={Boolean(downloading)}><Download size={15} />Word 다운로드</button><button type="button" onClick={() => download(selectedPlan, 'pptx')} disabled={Boolean(downloading)}><Presentation size={15} />PowerPoint 다운로드</button></footer></section></div>}
      </main>
    </WorkspaceShell>
  )
}
