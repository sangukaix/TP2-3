import {
  FileBarChart,
  LayoutDashboard,
  Sparkles,
  ClipboardList,
} from 'lucide-react'
import logo from '../assets/logo.png'

const menuItems = [
  { href: '/dashboard', label: '지역선택', icon: LayoutDashboard },
  { href: '/planning', label: '기획안 생성', icon: ClipboardList },
  { href: '/strategy', label: '기획안 수정 · 출력', icon: Sparkles },
]
const savedPlansMenuItem = { href: '/saved-plans', label: '저장된 기획서', icon: FileBarChart }

/**
 * bid3의 224px 사이드바·64px 상단바 비율을 React + Vite에 맞춰 옮긴 공통 화면 틀입니다.
 * 입찰·결제 메뉴는 제거하고 관광 분석 업무 흐름만 남겼습니다.
 */
export default function WorkspaceShell({ children }) {
  const currentPath = window.location.pathname
  const topbarLabel = currentPath === '/dashboard'
    ? '1. 희망 지역을 선택해주세요'
    : currentPath === '/planning'
      ? '2. 필수 조건을 선택 후 기획안 생성'
      : currentPath === '/strategy'
        ? '3. 기획안 수정 및 출력'
        : currentPath === '/saved-plans'
          ? '저장공간'
          : currentPath === '/ml-test'
            ? '머신러닝 결과'
            : currentPath === '/openai-test'
              ? 'OpenAI · Agent AI 구조'
              : currentPath === '/react-test'
                ? 'React · Vite 구조'
          : '지역관광 전략 업무공간'

  return (
    <div className="workspace-shell">
      <header className="home-header workspace-global-header">
        <div>
          <div className="home-brand-wrap">
            <a className="home-brand" href="/" aria-label="OLIGO 홈"><img className="home-brand-logo" src={logo} alt="OLIGO (가제)" /></a>
            <a className="ml-learning-dot" href="/ml-test" aria-label="머신러닝 학습 결과 보기" title="머신러닝 학습 결과" />
          </div>
        </div>
      </header>

      <aside className="workspace-sidebar">
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
            <p>{topbarLabel}</p>
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </section>

      <nav className="workspace-mobile-nav" aria-label="모바일 관광 분석 메뉴">
        {[...menuItems, savedPlansMenuItem].map(({ href, label, icon: Icon }) => (
          <a className={currentPath === href ? 'is-active' : ''} href={href} key={href}><Icon size={17} /><span>{label}</span></a>
        ))}
      </nav>
    </div>
  )
}
