/** 브라우저 저장 공간과 무관하게 이미 시작한 서버 작업을 다음 페이지로 전달합니다. */
export function strategyJobUrl(job, regionName) {
  const query = new URLSearchParams({ job_id: job.job_id, region_code: job.region_code, region_name: regionName })
  return `/strategy?${query}`
}

export function readStrategyJobLink(location = window.location) {
  if (!['/strategy', '/strategy/', '/proposal', '/proposal/'].includes(location.pathname)) return null
  const query = new URLSearchParams(location.search)
  const job_id = query.get('job_id')
  const region_code = query.get('region_code')
  const region_name = query.get('region_name')
  if (!/^[\w-]{1,100}$/.test(job_id || '') || !/^\d{5}$/.test(region_code || '') || !region_name?.trim()) return null
  return { job_id, region_code, region_name }
}

export function clearStrategyJobLink() {
  const url = new URL(window.location.href)
  for (const key of ['job_id', 'region_code', 'region_name']) url.searchParams.delete(key)
  window.history.replaceState(window.history.state, '', url)
}
