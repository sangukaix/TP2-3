export const THEME_STORAGE_KEY = 'oligo-theme'
export const DEFAULT_THEME = 'night'
export const THEME_CHANGE_EVENT = 'oligo-theme-change'

function normalizeTheme(theme) {
  return theme === 'day' ? 'day' : DEFAULT_THEME
}

export function getStoredTheme() {
  try {
    return normalizeTheme(window.localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    return DEFAULT_THEME
  }
}

export function applyTheme(theme) {
  const nextTheme = normalizeTheme(theme)
  document.documentElement.dataset.theme = nextTheme

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme)
  } catch {
    // 저장 공간을 사용할 수 없어도 현재 화면의 테마 전환은 계속 동작합니다.
  }

  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: nextTheme }))
  return nextTheme
}

export function initializeTheme() {
  return applyTheme(getStoredTheme())
}
