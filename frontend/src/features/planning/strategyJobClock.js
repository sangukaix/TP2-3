const memoryStarts = new Map()

export function jobStartTime(value) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) && parsed > 0 && parsed <= Date.now() + 60000 ? parsed : null
}

export function resolveJobStart(jobId, startedAt, now = Date.now()) {
  const key = `tourism-strategy-clock:${jobId}`
  let saved
  try { saved = window.localStorage.getItem(key) } catch { /* Storage is optional. */ }
  const start = jobStartTime(startedAt) ?? jobStartTime(saved) ?? memoryStarts.get(jobId) ?? now
  memoryStarts.set(jobId, start)
  try { window.localStorage.setItem(key, new Date(start).toISOString()) } catch { /* URL and memory retain the start. */ }
  return start
}

export function formatJobElapsed(start, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - start) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
