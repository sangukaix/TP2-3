import { Bot, Globe2, LoaderCircle, Send } from 'lucide-react'
import { useState } from 'react'
import { chatWithTourismAssistant } from '../api/dashboardApi'
import { chatHistory } from '../features/planning/chatHistory'

// 처음 보는 사용자가 질문 범위를 이해할 수 있도록 보여 주는 안내 예시입니다.
// 클릭 시 바로 질문을 보내지 않으며, 사용자가 자신의 문장으로 작성합니다.
const QUICK_QUESTIONS = [
  '이 기획안에서 수정할 수 있는 항목을 알려줘.',
  '방문 목표 4%, 소비 목표 5%로 바꿔줘.',
  '현재 사업의 홍보 문구를 쉽게 바꿔줘.',
]

/** bid3 제안서 화면의 우측 AI 비서 역할을 관광 전략용으로 이식한 패널입니다. */
export default function WorkspaceAssistantPanel({ region, report, onApplyPatch, planningBrief }) {
  // 대화 기록은 이 패널을 열어 둔 동안만 React state에 보관합니다.
  // 보고서 본문·사업 여건은 부모 화면에서 전달받아 AI의 참고 자료로만 사용합니다.
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [appliedPatch, setAppliedPatch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 질문을 API에 보내고, 최근 8개 대화만 함께 전달합니다.
  // 기록 길이를 제한하면 토큰 비용과 응답 지연을 일정하게 유지할 수 있습니다.
  const ask = async (preset) => {
    const content = String(preset || question).trim()
    if (!content || loading) return
    const history = [...messages, { role: 'user', content }]
    setMessages(history)
    setQuestion('')
    setError('')
    setLoading(true)
    try {
      const answer = await chatWithTourismAssistant(region.code, {
        region_name: region.name,
        question: content,
        history: chatHistory(history),
        current_report: report,
        planning_brief: planningBrief || null,
        enable_web_search: report ? false : useWebSearch,
      })
      setMessages((items) => [...items, { role: 'assistant', ...answer }])
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  // AI가 ‘수정안(report_patch)’을 준 가장 최근 답변만 적용 버튼에 연결합니다.
  // 자동 반영하지 않아 사용자가 제안 내용을 확인한 후에만 기획안을 바꿀 수 있습니다.
  const latestPatch = [...messages].reverse().find((item) => item.role === 'assistant' && item.report_patch)?.report_patch

  return <aside className="workspace-chat" aria-label="AI 챗봇">
    <header><span><Bot size={17} /></span><div><b>AI 챗봇</b></div><em>{loading ? '응답 중' : error ? '요청 실패' : '질문 대기'}</em></header>
    <p className="workspace-chat-intro">현재 아이디어의 목표 KPI·예상 견적·문장·실행 단계를 조정하세요. 다른 사업은 근거가 연결된 후보 안에서 비교할 수 있습니다.</p>
    <div className="workspace-chat-messages">
      {messages.length === 0 && <div className="workspace-chat-empty">{QUICK_QUESTIONS.map((item) => <p key={item}>{item}</p>)}</div>}
      {messages.map((message, index) => (
        <article className={`workspace-chat-message is-${message.role}`} key={`${message.role}-${index}`}>
          <b>{message.role === 'assistant' ? 'AI' : '나'}</b>
          <div>
            <p>{message.content || message.answer}</p>
            {message.role === 'assistant' && <small>{message.generation_mode === 'offline_sample' ? '오프라인 예시 · 모델 응답 아님' : `${message.execution?.model || message.generation_mode || '모델 정보 없음'} · ${message.execution?.web_search_used ? '웹 검색 사용' : '새 웹 검색 미사용'}`}</small>}
            {message.key_points?.length > 0 && <ul>{message.key_points.map((point) => <li key={point}>{point}</li>)}</ul>}
            {message.sources?.length > 0 && (
              <details>
                <summary>공식 출처 {message.sources.length}건</summary>
                {message.sources.map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>{source.title}</a>)}
              </details>
            )}
          </div>
        </article>
      ))}
      {loading && <p className="workspace-chat-thinking"><LoaderCircle size={15} />근거와 지역 데이터를 확인하고 있습니다…</p>}
      {error && <p className="workspace-chat-error">{error}</p>}
    </div>
    {report && latestPatch && onApplyPatch && <button className="workspace-chat-apply" type="button" disabled={loading || appliedPatch === latestPatch} onClick={() => { onApplyPatch(latestPatch); setAppliedPatch(latestPatch) }}>{appliedPatch === latestPatch ? '반영됨 · 기획안 저장 필요' : '이 수정안을 기획안에 반영'}</button>}
    <footer className="workspace-chat-composer">{!report && <label><input type="checkbox" checked={useWebSearch} onChange={(event) => setUseWebSearch(event.target.checked)} /><Globe2 size={13} />웹 검색</label>}<div><textarea rows="2" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() } }} placeholder="분석 결과나 기획안에 대해 질문하세요!" /><button type="button" onClick={() => ask()} disabled={!question.trim() || loading} aria-label="질문 전송"><Send size={15} /></button></div></footer>
  </aside>
}
