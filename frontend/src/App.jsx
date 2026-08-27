import { lazy, Suspense } from 'react'

// 첫 화면에서 Leaflet·Recharts·보고서 코드를 모두 내려받지 않도록 페이지 단위로 분리합니다.
const TourismHomePage = lazy(() => import('./pages/TourismHomePage'))
const TourismDashboardPage = lazy(() => import('./pages/TourismDashboardPage'))
const TourismStrategyPage = lazy(() => import('./pages/TourismStrategyPage'))
const SavedStrategyPlansPage = lazy(() => import('./pages/SavedStrategyPlansBoardPage'))

function PageLoading() {
  return (
    <main aria-busy="true" aria-label="페이지 불러오는 중" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: '#64748b', background: '#f8fafc', fontSize: 13 }}>
      화면을 준비하고 있습니다.
    </main>
  )
}

/** 현재 페이지 수가 적어 별도 Router 의존성 없이 경로별 화면만 지연 로딩합니다. */
export default function App() {
  const path = window.location.pathname
  let Page = TourismDashboardPage
  if (path === '/') Page = TourismHomePage
  // 진단 지표는 지역선택 화면 안에 통합했습니다. 예전 주소도 대시보드를 표시해 링크가 끊기지 않게 합니다.
  if (path === '/diagnosis') Page = TourismDashboardPage
  if (path === '/strategy') Page = TourismStrategyPage
  // 기획서 제작은 AI 전략기획 화면에 통합했습니다. 예전 주소는 같은 화면으로 연결합니다.
  if (path === '/proposal') Page = TourismStrategyPage
  if (path === '/saved-plans') Page = SavedStrategyPlansPage

  return <Suspense fallback={<PageLoading />}><Page /></Suspense>
}
