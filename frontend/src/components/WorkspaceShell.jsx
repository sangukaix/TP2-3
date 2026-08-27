import {
  FileBarChart,
  LayoutDashboard,
  MapPinned,
  Sparkles,
} from 'lucide-react'

const menuItems = [
  { href: '/dashboard', label: '지역선택', icon: LayoutDashboard },
  { href: '/strategy', label: 'AI 전략기획', icon: Sparkles },
]

/**
 * bid3의 224px 사이드바·64px 상단바 비율을 React + Vite에 맞춰 옮긴 공통 화면 틀입니다.
 * 입찰·결제 메뉴는 제거하고 관광 분석 업무 흐름만 남겼습니다.
 */
export default function WorkspaceShell({ children }) {
  const currentPath = window.location.pathname

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <a className="workspace-brand" href="/" aria-label="TOUR Insight 홈">
          <span><MapPinned size={18} /></span>
          <div><b>TOUR INSIGHT</b></div>
        </a>

        <nav className="workspace-nav" aria-label="관광 분석 메뉴">
          <p>분석 업무</p>
          {menuItems.map(({ href, label, icon: Icon }) => (
            <a className={currentPath === href ? 'is-active' : ''} href={href} key={href}><Icon size={17} /><span>{label}</span></a>
          ))}
          <p>기획서 관리</p>
          <a className={currentPath === '/saved-plans' ? 'is-active' : ''} href="/saved-plans"><FileBarChart size={17} /><span>저장된 기획서</span></a>
        </nav>

      </aside>

      <section className="workspace-main">
        <header className="workspace-topbar">
          <div>
            <p>지역관광 전략 업무공간</p>
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </section>

      <nav className="workspace-mobile-nav" aria-label="모바일 관광 분석 메뉴">
        {menuItems.slice(0, 3).map(({ href, label, icon: Icon }) => (
          <a className={currentPath === href ? 'is-active' : ''} href={href} key={href}><Icon size={17} /><span>{label}</span></a>
        ))}
      </nav>
    </div>
  )
}
