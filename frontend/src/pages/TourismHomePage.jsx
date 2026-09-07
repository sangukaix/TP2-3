import { useEffect, useState } from 'react'
import { ArrowRight, BarChart3, Bot, FileText, MapPinned } from 'lucide-react'
import '../App.css'
import logo from '../assets/logo.png'

const STEPS = [
  {
    icon: MapPinned,
    title: '1. 분석 지역 선택',
    description: '전국 지도에서 시도와 시군구를 선택하고 해당 지역의 최신 관광 현황을 확인합니다.',
    points: ['시도·시군구 2단계 선택', '지도에서 선택 지역 강조'],
  },
  {
    icon: BarChart3,
    title: '2. 관광 데이터 진단',
    description: '방문자 수, 관광소비액, 숙박과 업종별 소비를 그래프로 비교해 개선 기회를 찾습니다.',
    points: ['최근 12개월 추세', '소비·체류 구조 진단'],
  },
  {
    icon: Bot,
    title: '3. AI 챗봇',
    description: '지역 원자료와 공식 사례를 근거로 문제의 의미를 설명하고 기획안 수정안을 제안합니다.',
    points: ['공식 웹 자료 검색', '사용자 확인 후 수정 적용'],
  },
  {
    icon: FileText,
    title: '4. 전략기획서 출력',
    description: '검증된 분석과 실행 단계를 회의용 Word 또는 발표용 PowerPoint로 만듭니다.',
    points: ['5단계 실행 로드맵', 'Word·PowerPoint 선택 출력'],
  },
]

// 네 단계는 하나의 기준 시간으로 순환합니다. 카드마다 다른 속도를 쓰지 않습니다.
const CARD_ROTATION_MS = 4000

// 왼쪽 카드의 현재 단계에 맞춰 우측 시연 화면도 함께 바뀝니다.
const INTERACTION_DEMOS = [
  { key: 'region', action: '시도 · 시군구 선택', output: '선택 지역의 지도와 핵심 지표가 즉시 표시됩니다.' },
  { key: 'dashboard', action: '월별 그래프 확인', output: '방문자 수·관광소비액·업종 비중을 한눈에 비교합니다.' },
  { key: 'chat', action: 'AI 챗봇에 질문', output: '공식 근거를 바탕으로 개선안과 실행 단계를 제안합니다.' },
  { key: 'proposal', action: 'Word 또는 PPT 선택', output: '검토한 전략을 회의·보고용 기획서로 다운로드합니다.' },
]

/** bid3 메인 페이지의 상단바·소개 문구·입체 카드 전환을 관광 서비스 내용으로 옮긴 화면입니다. */
export default function TourismHomePage() {
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    // 네 장면은 사용자 마우스 위치와 관계없이 동일한 4초 간격으로 순환합니다.
    const timer = window.setInterval(() => setActiveIndex((current) => (current + 1) % STEPS.length), CARD_ROTATION_MS)
    return () => window.clearInterval(timer)
  }, [])

  const moveTo = (index) => setActiveIndex(index)
  const interactionDemo = INTERACTION_DEMOS[activeIndex]

  return (
    <main className="tourism-home">
      <header className="home-header">
        <div>
          <div className="home-brand-wrap">
            <a className="home-brand" href="/" aria-label="OLIGO 홈"><img className="home-brand-logo" src={logo} alt="OLIGO (가제)" /></a>
            <a className="ml-learning-dot" href="/ml-test" aria-label="머신러닝 학습 결과 보기" title="머신러닝 학습 결과" />
          </div>
        </div>
      </header>

      <section className="home-hero">
        {/* 배경 이미지는 고정하고, 빛줄기·물결 레이어만 독립적으로 움직입니다. */}
        <div className="home-hero-effects" aria-hidden="true">
          <i className="hero-firework hero-firework--left" />
          <i className="hero-firework hero-firework--middle" />
          <i className="hero-firework hero-firework--right" />
          <i className="hero-firework hero-firework--far hero-firework--far-left" />
          <i className="hero-firework hero-firework--far hero-firework--far-center" />
          <i className="hero-firework hero-firework--far hero-firework--far-right" />
          <span className="hero-river-flow hero-river-flow--one" />
          <span className="hero-river-flow hero-river-flow--two" />
          <span className="hero-river-flow hero-river-flow--three" />
        </div>
        <h1>지역 관광의 문제를 찾고<br /><em>실행 가능한 전략</em>으로 바꿉니다</h1>
        <div className="home-hero-subtitle"><i /><p>관광데이터랩의 데이터를 분석하여 AI가 기획서 초안을 작성해줍니다</p><i /></div>
        <div className="home-hero-actions">
          <a href="/dashboard">시작하기 <ArrowRight size={16} /></a>
        </div>
      </section>

      <section className="home-process" aria-label="관광 전략 서비스 이용 단계">
        <div className="home-workflow-layout">
          <nav className="home-step-rail" aria-label="관광 전략 4단계 설명">
            <ol>{STEPS.map((step, index) => {
              const Icon = step.icon
              const isActive = index === activeIndex
              return <li className={isActive ? 'is-active' : index < activeIndex ? 'is-complete' : ''} key={step.title}>
                <button type="button" onClick={() => moveTo(index)} aria-current={isActive ? 'step' : undefined}>
                  <span className="home-step-rail-number">0{index + 1}</span>
                  <span className="home-step-rail-copy"><b>{step.title.replace(/^\d\.\s/, '')}</b></span>
                  <Icon size={16} />
                </button>
              </li>
            })}</ol>
          </nav>
          <aside className={`home-demo-preview home-demo-preview--${interactionDemo.key}`} aria-label={`${STEPS[activeIndex].title} 화면 시연`}>
            <div className="demo-browser">
              <div className="demo-browser-top"><i /><i /><i /></div>
              <div className="demo-scene" key={interactionDemo.key}>
                <span className="demo-scene-glow" aria-hidden="true" />
                <div className="demo-scene-heading"><b>{interactionDemo.action}</b></div>
                {interactionDemo.key === 'region' && <><div className="demo-map-canvas"><svg className="demo-korea-map" viewBox="0 0 230 260" role="img" aria-label="대한민국 지역 선택 지도"><defs><linearGradient id="demoMapFill" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#e7f6fa" /><stop offset="1" stopColor="#bcdce7" /></linearGradient><filter id="demoMapGlow"><feGaussianBlur stdDeviation="3" /></filter></defs><path className="demo-korea-shadow" d="M124 12 144 45 166 57 174 90 166 115 184 143 175 180 155 202 145 239 121 246 101 226 83 207 64 181 67 150 47 126 58 98 52 75 73 52 88 29Z" /><path className="demo-korea-outline" d="M124 12 144 45 166 57 174 90 166 115 184 143 175 180 155 202 145 239 121 246 101 226 83 207 64 181 67 150 47 126 58 98 52 75 73 52 88 29Z" /><path className="demo-map-region-line" d="M74 53 100 68 130 59 151 75M52 75 84 91 116 87 148 103 170 91M58 99 80 119 109 111 141 124 167 115M47 126 78 139 97 158 132 151 172 143M67 150 87 174 121 181 153 169 176 180M83 207 111 198 144 203M88 30 91 57M110 21 115 63M129 60 122 101 129 151 121 181 121 240" /><path className="demo-map-region-line" d="M75 52 79 91 78 139 87 174 83 207M100 68 116 87 109 111 132 151 121 181M151 75 148 103 167 115 172 143 153 169 155 202" /><path className="demo-map-active-glow" d="M87 70 106 66 118 77 113 95 94 99 82 87Z" /><path className="demo-map-active" d="M87 70 106 66 118 77 113 95 94 99 82 87Z" /><circle className="demo-map-pin-core" cx="101" cy="82" r="5" /><circle className="demo-map-pin-ring" cx="101" cy="82" r="11" /><g className="demo-map-islands"><circle cx="34" cy="118" r="2" /><circle cx="28" cy="127" r="1.4" /><circle cx="38" cy="135" r="1.6" /><circle cx="54" cy="211" r="1.8" /><circle cx="63" cy="221" r="1.2" /><path d="M70 238c8-6 20-5 28 2-7 7-21 8-28-2Z" /></g><text className="demo-map-label" x="104" y="112">서울</text></svg><div className="demo-map-grid" /></div><div className="demo-select-row"><span>서울특별시 <b>⌄</b></span><span>강남구 <b>⌄</b></span></div><div className="demo-map-metrics"><b>1,796만</b><span>7월 방문자 수</span><i>전월 대비 +3.1%</i></div></>}
                {interactionDemo.key === 'dashboard' && <><div className="demo-chart-title"><span>월별 관광 흐름</span><i>2026.07</i></div><div className="demo-mini-chart"><i><span>1,540만</span></i><i><span>1,590만</span></i><i><span>1,640만</span></i><i><span>1,700만</span></i><i><span>1,750만</span></i><i><span>1,796만</span></i></div><div className="demo-chart-line" /><div className="demo-chart-legend"><span>방문자 수</span><b>관광소비액</b></div></>}
                {interactionDemo.key === 'chat' && <><div className="demo-chat-question"><i>질문</i> 강남구의 소비를 높일 방법은?</div><div className="demo-chat-thinking"><i /><i /><i />공식 자료와 지역 지표 분석 중</div><div className="demo-chat-answer"><i>AI</i><span>야간 체류 콘텐츠와 숙박 연계를 우선 제안합니다.</span></div><div className="demo-chat-source"><i>✓</i> 공식 자료 4건 근거</div></>}
                {interactionDemo.key === 'proposal' && <><div className="demo-file-tabs"><span className="is-selected">Word</span><span>PowerPoint</span></div><div className="demo-document"><header><small>TOUR INSIGHT</small><em>2026.08</em></header><h4>강남구 관광소비 활성화 실행안</h4><div className="demo-document-kpis"><span><b>+8.4%</b><small>방문 목표</small></span><span><b>+12.1%</b><small>소비 목표</small></span><span><b>5단계</b><small>실행 계획</small></span></div><div className="demo-document-lines"><i /><i /><i /></div><strong>데이터 근거 · 실행 로드맵 · 기대효과</strong></div><div className="demo-export-ready"><i>✓</i><span>기획서 생성 완료</span><b>다운로드</b></div></>}
                <div className="demo-scene-subtitle"><p>{interactionDemo.output}</p></div>
                <span className="demo-pointer" aria-hidden="true" />
                <span className="demo-click-ring" aria-hidden="true" />
              </div>
            </div>
            <div className="demo-clip-progress" aria-hidden="true">{STEPS.map((step, index) => <i className={index === activeIndex ? 'is-active' : index < activeIndex ? 'is-complete' : ''} key={step.title} />)}</div>
          </aside>
        </div>
      </section>

      <footer className="home-footer"><p>공식 관광 데이터와 근거를 활용한 지역관광 전략 지원 서비스</p></footer>
    </main>
  )
}
