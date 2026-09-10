/**
 * 화면 경로 계약을 React 컴포넌트와 분리해 Node에서도 검증할 수 있게 합니다.
 * 페이지 수가 적어 별도 라우터 패키지는 사용하지 않지만, 알 수 없는 경로를
 * 대시보드로 오인하지 않고 과거 주소는 명시적인 별칭으로만 유지합니다.
 */
export const APP_ROUTES = Object.freeze({
  '/': 'home',
  '/dashboard': 'dashboard',
  '/planning': 'planning',
  '/strategy': 'strategy',
  '/saved-plans': 'savedPlans',
  '/ml-test': 'mlTest',
  '/openai-test': 'openAiLearning',
  '/react-test': 'reactLearning',
  '/llm-control': 'llmControl',
  '/project-tree': 'projectTree',
})

export const ROUTE_ALIASES = Object.freeze({
  '/diagnosis': '/dashboard',
  '/proposal': '/strategy',
})

export function normalizePathname(pathname) {
  const value = typeof pathname === 'string' && pathname.trim() ? pathname.trim() : '/'
  const withLeadingSlash = value.startsWith('/') ? value : `/${value}`
  return withLeadingSlash === '/' ? '/' : withLeadingSlash.replace(/\/+$/, '')
}

export function resolveAppRoute(pathname) {
  const requestedPath = normalizePathname(pathname)
  const canonicalPath = ROUTE_ALIASES[requestedPath] || requestedPath
  return {
    requestedPath,
    canonicalPath,
    pageId: APP_ROUTES[canonicalPath] || null,
    found: Boolean(APP_ROUTES[canonicalPath]),
  }
}

/**
 * 별도 구조 탐색기 주소가 없으면 현재 React 주소의 호스트를 그대로 사용합니다.
 * 팀원이 LAN 주소로 접속했을 때 localhost가 팀원 PC를 가리키는 문제를 막습니다.
 */
export function resolveProjectTreeUrl(configuredUrl, pageUrl) {
  const configured = typeof configuredUrl === 'string' ? configuredUrl.trim() : ''
  if (configured) return configured.replace(/\/+$/, '')
  const url = new URL(pageUrl)
  url.port = '8501'
  url.pathname = ''
  url.search = ''
  url.hash = ''
  return url.origin
}
