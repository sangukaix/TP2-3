import { Bot, Globe2, LoaderCircle, Send } from 'lucide-react'
import { useState } from 'react'
import { chatWithTourismAssistant } from '../api/dashboardApi'

const QUICK_QUESTIONS = [
  '이 지역에서 가장 먼저 검토할 지표를 알려줘.',
  '비슷한 지역의 공식 사례와 비교해 줘.',
  '기획안을 더 구체적인 실행안으로 바꿔 줘.',
]

/** bid3 제안서 화면의 우측 AI 비서 역할을 관광 전략용으로 이식한 패널입니다. */
export default function WorkspaceAssistantPanel({ region, report, onApplyPatch }) {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [useWebSearch, setUseWebSearch] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
        history: history.slice(-8),
        current_report: report,
        enable_web_search: useWebSearch,
      })
      setMessages((items) => [...items, { role: 'assistant', ...answer }])
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  const latestPatch = [...messages].reverse().find((item) => item.role === 'assistant' && item.report_patch)?.report_patch

  return <aside className="workspace-chat" aria-label="AI 챗봇">
    <header><span><Bot size={17} /></span><div><b>AI 챗봇</b></div><em>Active</em></header>
    <p className="workspace-chat-intro">지표의 의미를 묻거나, 공식 사례를 찾아 현재 기획안을 더 구체적으로 수정할 수 있습니다.</p>
    <div className="workspace-chat-messages">
      {messages.length === 0 && <div className="workspace-chat-empty">{QUICK_QUESTIONS.map((item) => <button key={item} type="button" onClick={() => ask(item)}>{item}</button>)}</div>}
      {messages.map((message, index) => (
        <article className={`workspace-chat-message is-${message.role}`} key={`${message.role}-${index}`}>
          <b>{message.role === 'assistant' ? 'AI' : '나'}</b>
          <div>
            <p>{message.content}</p>
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
    {latestPatch && onApplyPatch && <button className="workspace-chat-apply" type="button" onClick={() => onApplyPatch(latestPatch)}>이 수정안을 기획안에 반영</button>}
    <footer><label><input type="checkbox" checked={useWebSearch} onChange={(event) => setUseWebSearch(event.target.checked)} /><Globe2 size={13} />웹 검색</label><div><textarea rows="3" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() } }} placeholder="기획안에 대해 질문하세요" /><button type="button" onClick={() => ask()} disabled={!question.trim() || loading} aria-label="질문 전송"><Send size={15} /></button></div></footer>
  </aside>
}
