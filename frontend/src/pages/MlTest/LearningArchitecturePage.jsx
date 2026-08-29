import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, ArrowDown, ArrowRight, Bot, Box, BrainCircuit, Braces, CheckCircle2,
  Cloud, Database, FileCode2, Folder, FolderTree, GitBranch, Globe2, HardDrive,
  Layers3, LoaderCircle, Monitor, Network, PackageCheck, Send, Server, Sparkles,
  UserRound, Workflow,
} from 'lucide-react'
import '../../App.css'
import WorkspaceShell from '../../components/WorkspaceShell'
import { chatWithProjectLearningAssistant, getProjectLearningCatalog } from '../../api/projectLearningApi'
import LearningSectionNav from './LearningSectionNav'
import './mlTest.css'

const EXAMPLES = {
  openai: ['5개 Agent는 각각 무슨 일을 해?', 'OpenAI는 어느 단계에서 개입해?', 'RAG와 웹 검색은 어떻게 달라?', '기획안이 품질검수를 통과하지 못하면 어떻게 돼?'],
  react: ['로컬에서 요청이 어떻게 이동해?', 'pages와 components는 어떻게 달라?', 'AWS 배포 후 구조는 어떻게 바뀌어?', 'React에서 OpenAI 키가 안 보이는 이유는 뭐야?'],
}

const CORE_AGENT_LABELS = {
  EvidenceAgent: ['01', '지역 근거', '원자료·Open API·공식 문서를 확인'],
  CaseStudyAgent: ['02', '공식 사례', '타지역 사업·예산·관측 결과를 조사'],
  TransferabilityAgent: ['03', '적합성 판단', '선택 지역에 적용할 조건과 제외 조건 검토'],
  PlannerAgent: ['04', '기획안 작성', '근거와 조건을 하나의 실행안으로 구성'],
  ReviewerAgent: ['05', '최종 검수', '환각·근거·실행 가능성을 다시 확인'],
}

/** 짧은 단계 카드를 자동 줄바꿈하여 작은 화면에서도 가로 스크롤 없이 보여줍니다. */
function PipelineDiagram({ nodes, label }) {
  return <section className="learning-flow" aria-label={label}>{nodes.map((node, index) => <div className="learning-flow-step" key={node.id}>
    <article className={`kind-${node.kind}`}><i>{String(index + 1).padStart(2, '0')}</i><div><h3>{node.title}</h3><p>{node.role}</p>{node.file && <code>{node.file}</code>}</div></article>
    {index < nodes.length - 1 && <span><ArrowRight size={16} /></span>}
  </div>)}</section>
}

/** 선생님 구조도를 TP2-3의 실제 로컬 포트와 AWS 예정 상태로 나눠 그립니다. */
function ReactSystemArchitecture({ architecture }) {
  const current = architecture?.current
  const deployment = architecture?.deployment
  if (!current) return null
  const serviceIcons = { frontend: Monitor, backend: Server, ai: BrainCircuit }
  const resourceIcons = { mysql: Database, joblib: HardDrive, chroma: Box, openai: Sparkles }
  return <section className="learning-block system-architecture-block">
    <header><Network size={18} /><div><h2>TP2-3 시스템 구조 설계</h2><p>실선은 HTTP 요청, 점선은 데이터·모델 연결입니다.</p></div></header>
    <div className="system-map" role="img" aria-label="사용자 브라우저에서 React, Backend, AI Server와 데이터 자원으로 이어지는 현재 로컬 시스템 구조">
      <article className="system-user-node"><UserRound size={18} /><div><b>사용자</b><span>Web Browser</span></div></article>
      <div className="system-main-arrow"><ArrowDown size={18} /><span>HTTP 요청</span></div>
      <div className="system-current-zone">
        <div className="system-zone-title"><span>{current.label}</span><em>RUNNING STRUCTURE</em></div>
        <div className="system-service-grid">{current.services.map((service) => {
          const Icon = serviceIcons[service.id] || Server
          return <article className={`system-service is-${service.id}`} key={service.id}><div><Icon size={19} /><span>{service.path}</span></div><h3>{service.title}</h3><b>{service.tech}</b><code>localhost:{service.port}</code><p>{service.role}</p></article>
        })}</div>
        <div className="system-proxy-label"><GitBranch size={15} /><span>Vite Proxy</span><code>/api/* → 8100</code><code>/ai/* → 8111</code></div>
        <div className="system-resource-grid">{current.resources.map((resource) => {
          const Icon = resourceIcons[resource.id] || Box
          return <article className={`system-resource owner-${resource.owner}`} key={resource.id}><Icon size={18} /><div><h3>{resource.title}</h3><b>{resource.tech}</b><p>{resource.role}</p></div><small>{resource.owner === 'backend' ? 'Backend 연결' : 'AI Server 연결'}</small></article>
        })}</div>
      </div>
    </div>
    {deployment && <div className="deployment-map"><header><Cloud size={18} /><div><b>{deployment.label}</b><span>{deployment.note}</span></div><em>PLANNED</em></header><div className="deployment-flow"><article><Globe2 size={17} /><span>사용자</span></article><ArrowRight size={16} /><article><Network size={17} /><span>{deployment.gateway}</span><small>{deployment.host}</small></article><ArrowRight size={16} /><div>{deployment.routes.map((route) => <p key={route.path}><code>{route.path}</code><span>{route.target}</span></p>)}</div></div></div>}
  </section>
}

/** 전체 파일을 늘어놓지 않고 폴더별 책임과 대표 파일만 펼쳐 보게 합니다. */
function ReactFolderTree({ tree }) {
  return <section className="learning-block react-folder-tree"><header><FolderTree size={18} /><div><h2>React 폴더 구조</h2><p>폴더는 역할별로 나누고, 세부 파일은 필요한 항목만 펼쳐 봅니다.</p></div></header>
    <div className="folder-root"><div className="folder-root-label"><Folder size={17} /><b>frontend/</b><span>React + Vite 애플리케이션</span></div><div className="folder-branches">{tree.map((item) => <details key={`${item.group}-${item.path}`} open={item.group === 'Page' || item.group === 'Component'}><summary><span className={`folder-icon group-${item.group.toLowerCase()}`}><Folder size={14} /></span><code>{item.path}</code><p>{item.role}</p><b>{item.count ? `${item.count}개` : '빌드 시 생성'}</b></summary>{item.examples?.length > 0 && <ul>{item.examples.map((file) => <li key={file}><FileCode2 size={12} /><code>{file}</code></li>)}</ul>}</details>)}</div></div>
  </section>
}

/** 5개 핵심 Agent의 병렬 조사와 순차 작성 구조를 한 화면에 보여줍니다. */
function OpenAiAgentArchitecture({ agents }) {
  const detected = new Set(agents.map((agent) => agent.name))
  const coreAgents = Object.entries(CORE_AGENT_LABELS).filter(([name]) => detected.has(name))
  const laterAgents = coreAgents.slice(2)
  return <section className="learning-block openai-agent-map"><header><Workflow size={18} /><div><h2>5-Agent 기획안 생성 구조</h2><p>OpenAI는 조사·판단·작성·검수 단계마다 정해진 JSON을 반환합니다.</p></div></header>
    <div className="agent-input-row"><span><Database size={15} />공식 관측값</span><span><BrainCircuit size={15} />ML 전망</span><span><Box size={15} />RAG·공식 웹</span><span><Braces size={15} />사용자 조건</span></div>
    <ArrowDown className="agent-down" size={18} />
    <div className="agent-parallel"><p>병렬 조사</p>{coreAgents.slice(0, 2).map(([name, [number, title, role]]) => <article key={name}><i>{number}</i><div><h3>{title}</h3><b>{name}</b><p>{role}</p></div></article>)}</div>
    <ArrowDown className="agent-down" size={18} />
    <div className="agent-sequence">{laterAgents.map(([name, [number, title, role]], index) => <div key={name}><article><i>{number}</i><div><h3>{title}</h3><b>{name}</b><p>{role}</p></div></article>{index < laterAgents.length - 1 && <ArrowRight size={17} />}</div>)}</div>
    <div className="agent-output"><PackageCheck size={18} /><div><b>구조화 기획안 JSON</b><span>화면 미리보기 → MySQL 저장 → Word/PPT 출력</span></div></div>
  </section>
}

/** OpenAI 파일은 기능 묶음만 먼저 보여주고 세부 경로는 접어서 장문을 줄입니다. */
function FileRoleTree({ files }) {
  const groups = useMemo(() => files.reduce((result, file) => {
    if (!result[file.group]) result[file.group] = []
    result[file.group].push(file)
    return result
  }, {}), [files])
  return <section className="learning-file-tree"><header><FolderTree size={18} /><div><h2>핵심 코드 위치</h2><p>필요한 묶음만 펼쳐 실제 파일을 확인합니다.</p></div></header>
    <div>{Object.entries(groups).map(([group, rows]) => <details key={group}><summary><span>{group}</span><b>{rows.length}</b></summary><ul>{rows.map((row) => <li key={`${group}-${row.path}`}><FileCode2 size={13} /><code>{row.path}</code><p>{row.role}</p></li>)}</ul></details>)}</div>
  </section>
}

/** route와 기술 목록은 학습할 때만 펼치도록 기본 화면의 글자 밀도를 낮춥니다. */
function TechnicalIndex({ topic, catalog }) {
  return <section className="learning-route-list"><header><Braces size={18} /><div><h2>{topic === 'openai' ? 'API · 모델 설정' : '페이지 · API 연결'}</h2><p>현재 소스에서 자동으로 찾은 상세 목록입니다.</p></div></header>
    <details><summary>Route {catalog.routes.length}개 보기</summary><div>{catalog.routes.map((route, index) => <article key={`${route.path}-${index}`}><b>{route.method}</b><code>{route.path}</code><span>{route.handler}</span></article>)}</div></details>
    {catalog.dependencies.length > 0 && <details><summary>사용 기술 · 설정 {catalog.dependencies.length}개 보기</summary><ul>{catalog.dependencies.map((item) => <li key={item.name}><b>{item.name}</b><span>{item.role}</span></li>)}</ul></details>}
  </section>
}

/** OpenAI·React 페이지가 공유하는 오른쪽 학습 챗봇입니다. */
function ProjectTutor({ topic }) {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }) }, [messages, busy])
  const send = async (text) => {
    const value = String(text || '').trim()
    if (!value || busy) return
    const history = messages.map(({ role, content }) => ({ role, content })).slice(-6)
    setMessages((current) => [...current, { role: 'user', content: value }]); setQuestion(''); setBusy(true); setError('')
    try {
      const response = await chatWithProjectLearningAssistant(topic, { question: value, history })
      setMessages((current) => [...current, { role: 'assistant', content: response.answer, points: response.key_points, files: response.related_files, caution: response.caution }])
    } catch (reason) { setError(reason.message) }
    finally { setBusy(false) }
  }
  return <aside className="learning-tutor"><header><span><Bot size={18} /></span><div><h2>{topic === 'openai' ? 'OpenAI 챗봇' : 'React 챗봇'}</h2><p>현재 프로젝트 구조 학습 도우미</p></div><i><b />Active</i></header>
    <div className="learning-tutor-scope"><Sparkles size={13} />이 페이지를 만들 때 스캔한 실제 구조만 근거로 답합니다.</div>
    <div className="learning-tutor-messages" aria-live="polite">{messages.length === 0 && <section className="learning-tutor-empty"><b>구조가 궁금한 부분을 물어보세요</b><p>파일 위치, 실행 순서, 사용하는 기술과 이유를 쉬운 말로 설명합니다.</p>{EXAMPLES[topic].map((text) => <button type="button" onClick={() => send(text)} key={text}>{text}</button>)}</section>}
      {messages.map((message, index) => <article className={`learning-tutor-message is-${message.role}`} key={`${message.role}-${index}`}><small>{message.role === 'user' ? '나' : '학습 챗봇'}</small><p>{message.content}</p>{message.points?.length > 0 && <ul>{message.points.map((point) => <li key={point}>{point}</li>)}</ul>}{message.files?.length > 0 && <div>{message.files.map((file) => <code key={file}>{file}</code>)}</div>}{message.caution && <em>{message.caution}</em>}</article>)}
      {busy && <p className="learning-tutor-loading"><LoaderCircle size={14} />현재 구조를 확인하고 있습니다.</p>}<div ref={endRef} /></div>
    {error && <p className="learning-tutor-error" role="alert"><AlertCircle size={13} />{error}</p>}
    <form onSubmit={(event) => { event.preventDefault(); send(question) }}><textarea rows="3" maxLength="2000" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={`${topic === 'openai' ? 'Agent AI와 OpenAI' : 'React 구조'}에 대해 질문해 주세요.`} /><button type="submit" disabled={!question.trim() || busy} aria-label="질문 보내기">{busy ? <LoaderCircle size={16} /> : <Send size={16} />}</button></form>
    <footer>OpenAI API 사용 · RAG 및 웹 검색 미사용</footer></aside>
}

/** 자동 탐색 카탈로그를 구조도·폴더 트리·학습 챗봇으로 조합합니다. */
export default function LearningArchitecturePage({ topic }) {
  const [catalog, setCatalog] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; getProjectLearningCatalog(topic).then((data) => { if (active) setCatalog(data) }).catch((reason) => { if (active) setError(reason.message) }); return () => { active = false } }, [topic])
  return <WorkspaceShell><main className="ml-test-page learning-architecture-page"><LearningSectionNav />
    {!catalog && !error && <div className="ml-test-state"><LoaderCircle className="learning-spin" size={18} />현재 프로젝트 구조를 읽고 있습니다.</div>}
    {error && <div className="ml-test-state is-error"><AlertCircle size={18} />{error}</div>}
    {catalog && <div className="learning-architecture-layout"><div className="learning-architecture-content">
      <header className="learning-architecture-hero"><div><p>PROJECT STUDY</p><h1>{catalog.title}</h1><span>{catalog.subtitle}</span></div><div className="learning-scan-source"><Braces size={16} /><span>실제 코드 자동 반영</span>{catalog.generated_from.map((source) => <code key={source}>{source}</code>)}</div></header>
      <section className="learning-summary-row">{catalog.summary.map((item) => <div key={item.label}><small>{item.label}</small><b>{item.value}</b></div>)}</section>

      {topic === 'react' ? <>
        <ReactSystemArchitecture architecture={catalog.architecture} />
        <section className="learning-block"><header><Layers3 size={18} /><div><h2>React 요청 처리 흐름</h2><p>URL 진입부터 FastAPI 응답을 화면에 그리기까지의 순서입니다.</p></div></header><PipelineDiagram nodes={catalog.pipeline} label="React 요청 처리 파이프라인" /></section>
        <ReactFolderTree tree={catalog.folder_tree} />
      </> : <>
        <OpenAiAgentArchitecture agents={catalog.agents} />
        <section className="learning-block"><header><Bot size={18} /><div><h2>챗봇 연결 구조</h2><p>질문·현재 기획안·공식 검색 결과를 구조화 응답으로 돌려줍니다.</p></div></header><PipelineDiagram nodes={catalog.chatbot_flow} label="OpenAI 챗봇 파이프라인" /></section>
      </>}

      <section className="learning-block compact-principles"><header><CheckCircle2 size={18} /><div><h2>핵심 설계 원칙</h2><p>수정할 때 유지해야 하는 기준입니다.</p></div></header><div className="learning-principle-grid">{catalog.principles.map((item) => <article key={item.title}><b>{item.title}</b><p>{item.description}</p></article>)}</div></section>

      <div className="learning-two-column">{topic === 'openai' ? <FileRoleTree files={catalog.files} /> : <section className="learning-file-tree react-layer-guide"><header><FolderTree size={18} /><div><h2>레이어별 책임</h2><p>화면과 서버의 역할을 섞지 않습니다.</p></div></header><div><p><Monitor size={14} /><b>React</b><span>표시·입력·상태</span></p><p><Server size={14} /><b>Backend</b><span>정확한 DB 업무</span></p><p><BrainCircuit size={14} /><b>AI Server</b><span>ML·RAG·LLM</span></p><p><Database size={14} /><b>MySQL</b><span>사실·저장 기록</span></p></div></section>}<TechnicalIndex topic={topic} catalog={catalog} /></div>
      <p className="learning-update-note"><Sparkles size={14} />{catalog.update_note}</p>
    </div><ProjectTutor topic={topic} /></div>}
  </main></WorkspaceShell>
}
