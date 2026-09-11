import { useEffect, useState } from 'react'
import { applyTheme, getStoredTheme, THEME_CHANGE_EVENT } from '../theme'

function moveTo(path) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo({ top: 0 })
}

export default function HeaderActions() {
  const [theme, setTheme] = useState(getStoredTheme)

  useEffect(() => {
    const syncTheme = (event) => setTheme(event.detail || getStoredTheme())
    window.addEventListener(THEME_CHANGE_EVENT, syncTheme)
    return () => window.removeEventListener(THEME_CHANGE_EVENT, syncTheme)
  }, [])

  const toggleTheme = () => {
    setTheme(applyTheme(theme === 'night' ? 'day' : 'night'))
  }

  return <div className="global-header-actions">
    <button type="button" onClick={() => moveTo('/signup')}>회원가입</button>
    <button type="button" onClick={() => moveTo('/login')}>로그인</button>
    <button type="button" onClick={() => moveTo('/my')}>My Page</button>
    <button type="button" onClick={toggleTheme}>{theme === 'night' ? 'Day Mode' : 'Night Mode'}</button>
  </div>
}
