import { ExternalLink } from 'lucide-react'
import { resolveProjectTreeUrl } from '../routes'
import './projectTree.css'

const explorerUrl = resolveProjectTreeUrl(import.meta.env.VITE_PROJECT_TREE_URL, window.location.href)

/** 공통 업무 메뉴 없이 발표용 구조 지도만 전체 화면에 표시합니다. */
export default function ProjectTreePage() {
  return <main className="project-tree-page">
    <header className="project-tree-toolbar">
      <span>TP2-3 프로젝트 구조 지도</span>
      <a href={explorerUrl} target="_blank" rel="noreferrer"><ExternalLink size={15} />새 창으로 보기</a>
    </header>
    <iframe title="TP2-3 프로젝트 구조 지도" src={explorerUrl} className="project-tree-frame" />
  </main>
}
