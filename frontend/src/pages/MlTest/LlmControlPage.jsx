import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, Bot, CheckCircle2, CircleDotDashed, DatabaseZap, RefreshCw, Save, ServerCog, ShieldAlert } from 'lucide-react'
import '../../App.css'
import WorkspaceShell from '../../components/WorkspaceShell'
import LearningSectionNav from './LearningSectionNav'
import { getLlmConfig, getLlmStatus, getLlmTrace, resetLlmConfig, saveLlmConfig } from '../../api/llmControlApi'
import './mlTest.css'
import './LlmControlPage.css'

const LABELS = {
  evidence: '지역 근거 조사', case_study: '공식 사례 조사', local_web_query_planner: '무료 공식 검색 질문 설계', transferability: '지역 적합성 판단',
  planner: '기획안 초안 작성', planner_revision: '기획안 보완', reviewer: '1차 품질 검수',
  final_reviewer: '최종 품질 검수', chat_explain: '챗봇 설명', chat_research: '챗봇 공식 조사', chat_revise: '챗봇 수정',
}

const TOOL_LABELS = {
  get_region_metrics: '지역 관측값', compare_regions: '타 지역 비교', get_ml_forecast: 'ML 전망·검증',
  get_planning_decision: '후보 선정 근거', get_case_comparison_matrix: '사례 운영원리 비교', search_collected_sources: '수집 자료 검색',
  read_collected_source: '사례·출처 읽기', read_task_section: '세부 근거 읽기',
}

/** 연결 상태와 실제 추론은 다릅니다. 실패·도구 조회·유료 폴백을 숨기지 않습니다. */
function TraceEvent({ event }) {
  const blocked = event.provider_called === false || event.status === 'blocked'
  const failed = event.status === 'failed' || blocked
  const prepared = event.input_preparation
  return <article className={failed ? 'llm-trace-failed' : ''}>
    <b>{LABELS[event.stage] || event.stage} · {blocked ? '호출 차단' : failed ? '실패' : event.status === 'completed' ? '완료' : '상태 미확인'}</b>
    <span>{event.provider} · {event.model}</span>
    <em>{event.duration_ms?.toLocaleString()} ms</em>
    {event.fallback && <i>대체 실행: {event.requested_provider} → {event.provider}</i>}
    <small>{failed ? `결과 미채택 · ${event.error_code || event.fallback_reason || '오류 확인 필요'}`
      : event.web_search_used ? 'OpenAI Web Search 사용' : '구조화 JSON 출력 · 웹검색 실행 아님'}</small>
    {event.tool_trace?.length > 0 && <small>근거 도구: {event.tool_trace.map((tool) =>
      `${TOOL_LABELS[tool.tool] || tool.tool} (${tool.status === 'completed' ? '조회' : '자료 미확보'})`).join(' · ')}</small>}
    {prepared && <small>원본은 요청 안에 보존 · 출처 {prepared.sources_available}건 중 원문 조회 {prepared.sources_read}건</small>}
    {event.fallback && <small>대체 실행 사유: {event.fallback_reason}</small>}
    {event.paid_reason && <small>{blocked ? '차단 사유' : 'OpenAI 사용 사유'}: {event.paid_reason}</small>}
  </article>
}

/** 실제 서버 상태와 저장된 라우팅을 보여 주는 팀 내부 운영·학습 화면입니다. */
export default function LlmControlPage() {
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [trace, setTrace] = useState([])
  const [usage, setUsage] = useState(null)
  const [adminToken, setAdminToken] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, nextConfig, tracePayload] = await Promise.all([getLlmStatus(), getLlmConfig(), getLlmTrace()])
      setStatus(nextStatus); setConfig(nextConfig); setTrace(tracePayload.events || []); setUsage(tracePayload.usage || null); setMessage('')
    } catch (error) { setMessage(error.message) }
  }, [])
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 15000); return () => window.clearInterval(timer) }, [refresh])
  const changeRoute = (task, field, value) => setConfig((current) => ({ ...current, routes: { ...current.routes, [task]: { ...current.routes[task], [field]: value } } }))
  const save = async () => { setBusy(true); try { setConfig(await saveLlmConfig(config, adminToken)); setMessage('저장했습니다. 다음 Agent 실행부터 이 설정이 적용됩니다.') } catch (error) { setMessage(error.message) } finally { setBusy(false) } }
  const restore = async () => { setBusy(true); try { setConfig(await resetLlmConfig(adminToken)); setMessage('서버 환경변수의 기본 라우팅으로 복구했습니다.') } catch (error) { setMessage(error.message) } finally { setBusy(false) } }
  return <WorkspaceShell><main className="ml-test-page llm-control-page"><LearningSectionNav />
    <header className="ml-test-hero"><div><p>LLM CONTROL CENTER</p><h1>AI Router</h1><span>Qwen은 근거 비교·검색 질문 설계·사전 검수, Gemma는 기획·수정, OpenAI는 필요한 공식 웹 조사와 독립 최종 검수를 맡습니다. 학생 절약 모드는 무료 공식 검색 API와 저장 근거를 우선 사용하고 OpenAI 최종 검수 1회만 허용합니다. ACTIVE는 연결 확인이며, 실제 추론은 실행 기록으로 확인합니다.</span></div><button type="button" onClick={refresh}><RefreshCw size={15} />새로고침</button></header>
    {status?.cost_policy?.student_budget ? <p className="llm-control-message">학생 절약 모드 적용 중 · Qwen·Gemma가 비교·작성·재검수를 수행 · OpenAI 웹 조사는 자동 실행하지 않음 · 무료 검색 API 키가 있으면 Qwen 질문으로 공식 도메인 원문 후보만 제한 조회 · 로컬 검수 통과본만 OpenAI 독립 최종 검수 1회 · 저장 근거가 부족하면 미승인으로 남습니다.</p> : status?.cost_policy?.local_first && <p className="llm-control-message">로컬 우선 적용 중 · 기획 생성 1건의 OpenAI 요청 최대 3회 · 로컬 실패 시 유료 자동 대체 없음 · 로컬 검수 미통과 시 최종 유료 검수 생략. 웹검색 내부 호출·토큰에 따른 금액 상한을 뜻하지 않습니다.</p>}
    {status?.cost_policy?.free_official_web_search && <p className="llm-control-message">무료 공식 검색 도구 · {status.cost_policy.free_official_web_search.configured_providers?.length ? `${status.cost_policy.free_official_web_search.configured_providers.join(' → ')} 연결됨` : 'API 키 미설정'} · 보고서 1건당 최대 {status.cost_policy.free_official_web_search.max_queries_per_report}개 질문 · 검색 요약은 원문 검수 전 후보로만 사용</p>}
    {message && <p className="llm-control-message"><AlertCircle size={14} />{message}</p>}
    <section className="llm-provider-grid">{status?.providers?.map((provider) => { const role = provider.role || provider.provider; const label = role === 'openai' ? 'OpenAI' : role === 'qwen' ? 'Qwen · Ollama' : 'Gemma · Ollama'; return <article key={role} className={`is-${provider.status}`}><header><ServerCog size={18} /><div><b>{label}</b><span>{provider.message}</span></div><em>{provider.status === 'active' ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}{provider.status}</em></header><p>{provider.models?.join(' · ') || '모델 목록 확인 필요'}</p><footer>{provider.capabilities?.map((item) => <i key={item}>{item}</i>)}</footer></article> })}</section>
    {config && <section className="llm-routing-panel">
      <header><div><Bot size={19} /><div><h2>작업별 라우팅</h2><p>저장 후 실제 적용 경로를 표시합니다. 설정 변경에는 관리자 토큰이 필요합니다.</p></div></div>
        <label>모드<select value={config.mode} onChange={(event) => setConfig({ ...config, mode: event.target.value })}>
          <option value="student_budget">student_budget · 학생 절약 (OpenAI 최종 검수 1회)</option><option value="local_first">local_first · 로컬 우선</option><option value="hybrid">hybrid · 유료 대체 허용</option><option value="openai_only">openai_only</option><option value="local_only">local_only · 웹검색 불가</option>
        </select></label></header>
      <div className="llm-routing-table"><div className="llm-routing-row is-head"><span>작업</span><span>Provider</span><span>모델</span><span>폴백</span></div>
        {Object.entries(config.routes).map(([task, route]) => {
          const applied = config.mode === status?.mode
          const locked = applied ? status?.capability_locks?.[task] : '모드 저장 후 실제 경로 확인'
          const shown = applied && locked ? (status?.effective_routes?.[task] || route) : route
          return <div className="llm-routing-row" key={task}>
            <b>{LABELS[task] || task}{locked && <small>{locked}</small>}</b>
            <select value={shown.provider} disabled={Boolean(locked)} onChange={(event) => changeRoute(task, 'provider', event.target.value)}>
              <option value="openai">OpenAI</option><option value="qwen">Qwen</option><option value="gemma">Gemma</option><option value="local_sources">저장된 공식 근거</option><option value="unavailable">실행 불가</option>
            </select>
            <input value={shown.model || ''} disabled={Boolean(locked)} placeholder="환경변수 기본 모델" onChange={(event) => changeRoute(task, 'model', event.target.value)} />
            <select value={shown.fallback} disabled={Boolean(locked)} onChange={(event) => changeRoute(task, 'fallback', event.target.value)}><option value="none">없음</option><option value="openai">OpenAI</option></select>
          </div>
        })}
      </div>
      <footer><input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} placeholder="LLM 관리자 토큰 (저장하지 않음)" /><button type="button" disabled={busy} onClick={restore}>기본값 복구</button><button type="button" disabled={busy} onClick={save}><Save size={14} />설정 저장</button></footer>
    </section>}
    <section className="llm-trace-panel"><header><div><CircleDotDashed size={18} /><div><h2>실시간 실행 기록</h2><p>시도별 성공·실패·대체 실행을 표시합니다. 근거 조회는 이번 요청의 수집 자료 대상이며, 실시간 웹검색과 구분합니다.</p></div></div>{usage && <span><DatabaseZap size={14} />실행 시도 {usage.tracked_calls}회 · 확인된 토큰 {usage.total_tokens.toLocaleString()}<small>사용량 미확인 {usage.usage_unknown_attempts ?? 0}회 · 비용은 별도 검증 필요</small></span>}</header><div>{trace.length === 0 ? <p className="llm-empty">아직 이 AI Server에서 실행된 LLM 호출이 없습니다.</p> : trace.map((event, index) => <TraceEvent key={`${event.recorded_at}-${index}`} event={event} />)}</div></section>
  </main></WorkspaceShell>
}
