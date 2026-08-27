import { useMemo, useState } from 'react'
import { Bot, Check, Globe2, LoaderCircle, Send, Sparkles, X } from 'lucide-react'
import { chatWithTourismAssistant } from '../api/dashboardApi'

const QUICK_QUESTIONS = [
  '이 지역에서 가장 먼저 개선할 문제는 무엇인가요?',
  '비슷한 지역의 공식 성공사례를 찾아 비교해 주세요.',
  '현재 기획안을 더 구체적인 실행안으로 바꿔 주세요.',
]

/**
 * 선택 지역의 원자료 snapshot과 현재 기획안을 함께 읽는 대화형 보조 패널입니다.
 * AI가 만든 수정안은 자동 저장하지 않고 사용자가 확인한 뒤 적용하게 합니다.
 */
export default function TourismAssistant({ open, onClose, region, report, onApplyPatch }) {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [useWebSearch, setUseWebSearch] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const latestPatch = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant' && message.report_patch)?.report_patch,
    [messages],
  )

  const sendQuestion = async (preset) => {
    const content = String(preset ?? question).trim()
    if (!content || isLoading) return
    const history = [...messages, { role: 'user', content }]
    setMessages(history)
    setQuestion('')
    setError('')
    setIsLoading(true)
    try {
      const response = await chatWithTourismAssistant(region.code, {
        region_name: region.name,
        question: content,
        history: history.slice(-8).map(({ role, content: messageContent }) => ({ role, content: messageContent })),
        current_report: report,
        enable_web_search: useWebSearch,
      })
      setMessages((current) => [...current, {
        role: 'assistant',
        content: response.answer,
        key_points: response.key_points,
        sources: response.sources,
        report_patch: response.report_patch,
        generation_mode: response.generation_mode,
      }])
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      <button className={`assistant-scrim${open ? ' is-visible' : ''}`} type="button" onClick={onClose} aria-label="AI 챗봇 닫기" />
      <aside className={`tourism-assistant${open ? ' is-open' : ''}`} aria-hidden={!open}>
        <header>
          <div><span><Bot size={18} /></span><div><b>AI 챗봇</b><small>{region.name} 데이터 기준</small></div></div>
          <button type="button" onClick={onClose} aria-label="닫기"><X size={18} /></button>
        </header>

        <section className="assistant-context">
          <Sparkles size={15} />
          <p><b>현재 분석 범위</b><span>{report ? '원자료와 생성된 기획안을 함께 읽고 있습니다.' : '지역 원자료를 읽고 있습니다. 기획안 생성 후에는 문장과 전략도 수정할 수 있습니다.'}</span></p>
        </section>

        <div className="assistant-messages">
          {messages.length === 0 && <div className="assistant-empty">
            <Bot size={26} />
            <b>무엇을 확인하거나 바꿀까요?</b>
            <p>관광 지표의 의미를 설명하고, 공식 사례를 조사하거나 현재 기획안의 수정안을 제안합니다.</p>
            <div>{QUICK_QUESTIONS.map((item) => <button type="button" key={item} onClick={() => sendQuestion(item)}>{item}</button>)}</div>
          </div>}
          {messages.map((message, index) => (
            <article className={`assistant-message is-${message.role}`} key={`${message.role}-${index}`}>
              <span>{message.role === 'assistant' ? <Bot size={14} /> : '나'}</span>
              <div>
                <p>{message.content}</p>
                {message.key_points?.length > 0 && <ul>{message.key_points.map((item) => <li key={item}>{item}</li>)}</ul>}
                {message.sources?.length > 0 && <details><summary>공식 출처 {message.sources.length}건</summary>{message.sources.map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>{source.title}</a>)}</details>}
                {message.generation_mode === 'offline_sample' && <small>현재 API 크레딧 없이 원자료 규칙으로 만든 테스트 답변입니다.</small>}
              </div>
            </article>
          ))}
          {isLoading && <div className="assistant-thinking"><LoaderCircle size={17} /><span>지역 데이터와 근거를 확인하고 있습니다…</span></div>}
          {error && <p className="assistant-error">{error}</p>}
        </div>

        {latestPatch && <button className="assistant-apply" type="button" onClick={() => onApplyPatch(latestPatch)}><Check size={16} />기획안 수정안 적용</button>}
        <footer>
          <label><input type="checkbox" checked={useWebSearch} onChange={(event) => setUseWebSearch(event.target.checked)} /><Globe2 size={14} />공식 웹 자료도 검색</label>
          <div><textarea rows="2" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendQuestion() } }} placeholder="분석 결과나 기획안에 대해 질문하세요" /><button type="button" onClick={() => sendQuestion()} disabled={!question.trim() || isLoading} aria-label="질문 보내기"><Send size={16} /></button></div>
        </footer>
      </aside>
    </>
  )
}
