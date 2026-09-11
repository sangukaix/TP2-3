
import { lazy, Suspense, useEffect, useState } from 'react'



// 첫 화면에서 Leaflet·Recharts·보고서 코드를 모두 내려받지 않도록 페이지 단위로 분리합니다.
const TourismHomePage = lazy(() => import('./pages/TourismHomePage'))
const TourismDashboardPage = lazy(() => import('./pages/TourismDashboardPage'))
const TourismStrategyPage = lazy(() => import('./pages/TourismStrategyPage'))
const TourismPlanningPage = lazy(() => import('./pages/TourismPlanningPage'))
const SavedStrategyPlansPage = lazy(() => import('./pages/SavedStrategyPlansBoardPage'))
const MlTestPage = lazy(() => import('./pages/MlTest/MlTestPage'))
const LearningArchitecturePage = lazy(() => import('./pages/MlTest/LearningArchitecturePage'))
const LlmControlPage = lazy(() => import('./pages/MlTest/LlmControlPage'))

const SignupPage = lazy(() => import('./pages/Signup'))
const LoginPage = lazy(() => import('./pages/Login'))

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

  const [path, setPath] = useState(window.location.pathname)

  useEffect(() => {
    const updatePath = () => setPath(window.location.pathname)
    window.addEventListener('popstate', updatePath)
    return () => window.removeEventListener('popstate', updatePath)
  }, [])

  let Page = TourismDashboardPage
  if (path === '/') Page = TourismHomePage
  if (path === '/signup') Page = SignupPage
  if (path === '/login') Page = LoginPage
  // 진단 지표는 지역선택 화면 안에 통합했습니다. 예전 주소도 대시보드를 표시해 링크가 끊기지 않게 합니다.
  if (path === '/diagnosis') Page = TourismDashboardPage
  if (path === '/strategy') Page = TourismStrategyPage
  if (path === '/planning') Page = TourismPlanningPage
  // 기획서 제작은 AI 전략기획 화면에 통합했습니다. 예전 주소는 같은 화면으로 연결합니다.
  if (path === '/proposal') Page = TourismStrategyPage
  if (path === '/saved-plans') Page = SavedStrategyPlansPage
  // 로고 옆 작은 점으로만 진입하는 팀 학습용 ML 설명 페이지입니다.
  if (path === '/ml-test') Page = MlTestPage
  if (path === '/openai-test') Page = OpenAiLearningPage
  if (path === '/react-test') Page = ReactLearningPage
  if (path === '/llm-control') Page = LlmControlPage
  if (path === '/project-tree') Page = ProjectTreePage


  return <Suspense fallback={<PageLoading />}><Page /></Suspense>
}
