import { Component, lazy, Suspense } from 'react'
import { resolveAppRoute } from './routes'

// 첫 화면에서 Leaflet·Recharts·보고서 코드를 모두 내려받지 않도록 페이지 단위로 분리합니다.
const TourismHomePage = lazy(() => import('./pages/TourismHomePage'))
const TourismDashboardPage = lazy(() => import('./pages/TourismDashboardPage'))
const TourismStrategyPage = lazy(() => import('./pages/TourismStrategyPage'))
const TourismPlanningPage = lazy(() => import('./pages/TourismPlanningPage'))
const SavedStrategyPlansPage = lazy(() => import('./pages/SavedStrategyPlansBoardPage'))
const MlTestPage = lazy(() => import('./pages/MlTest/MlTestPage'))
const LearningArchitecturePage = lazy(() => import('./pages/MlTest/LearningArchitecturePage'))
const LlmControlPage = lazy(() => import('./pages/MlTest/LlmControlPage'))
const ProjectTreePage = lazy(() => import('./pages/ProjectTreePage'))

// 학습 주제별 wrapper를 App 바깥에 두어 화면이 다시 그려져도 챗봇 상태가 초기화되지 않게 합니다.
function OpenAiLearningPage() {
  return <LearningArchitecturePage topic="openai" />
}

function ReactLearningPage() {
  return <LearningArchitecturePage topic="react" />
}

function PageLoading() {
  return (
    <main aria-busy="true" aria-label="페이지 불러오는 중" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: '#64748b', background: '#f8fafc', fontSize: 13 }}>
      화면을 준비하고 있습니다.
    </main>
  )
}

// 배포 직후 구형 청크 주소나 화면 오류가 생겨도 빈 화면 대신 복구 경로를 제공합니다.
class PageErrorBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return <main role="alert" style={{ padding: 48, color: '#334155', background: '#f8fafc', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 22 }}>화면을 불러오지 못했습니다.</h1>
      <p>새로고침해 다시 열어 주세요. 서버에서 진행 중인 기획안 생성 작업은 계속됩니다.</p>
      <button type="button" onClick={() => window.location.reload()}>화면 다시 불러오기</button>
    </main>
  }
}

function NotFoundPage() {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f8fafc', color: '#334155' }}>
      <section style={{ textAlign: 'center' }}>
        <p>요청한 화면을 찾지 못했습니다.</p>
        <a href="/dashboard">지역선택 화면으로 이동</a>
      </section>
    </main>
  )
}

/** 현재 페이지 수가 적어 별도 Router 의존성 없이 경로별 화면만 지연 로딩합니다. */
export default function App() {
  const route = resolveAppRoute(window.location.pathname)
  const pages = {
    home: TourismHomePage,
    dashboard: TourismDashboardPage,
    planning: TourismPlanningPage,
    strategy: TourismStrategyPage,
    savedPlans: SavedStrategyPlansPage,
    mlTest: MlTestPage,
    openAiLearning: OpenAiLearningPage,
    reactLearning: ReactLearningPage,
    llmControl: LlmControlPage,
    projectTree: ProjectTreePage,
  }
  const Page = pages[route.pageId] || NotFoundPage

  return <PageErrorBoundary><Suspense fallback={<PageLoading />}><Page /></Suspense></PageErrorBoundary>
}
