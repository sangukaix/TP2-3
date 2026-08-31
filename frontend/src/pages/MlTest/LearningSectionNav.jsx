import { Bot, BrainCircuit, CodeXml } from 'lucide-react'

const sections = [
  { href: '/ml-test', label: '머신러닝 결과', icon: BrainCircuit },
  { href: '/openai-test', label: 'OpenAI', icon: Bot },
  { href: '/react-test', label: 'React', icon: CodeXml },
]

/** 관리자 학습 페이지 세 개가 같은 위치와 모양의 탭을 공유합니다. */
export default function LearningSectionNav() {
  const path = window.location.pathname
  return <nav className="learning-section-nav" aria-label="프로젝트 학습 영역">
    {sections.map(({ href, label, icon: Icon }) => <a href={href} key={href} className={path === href ? 'is-active' : ''}><Icon size={15} />{label}</a>)}
  </nav>
}
