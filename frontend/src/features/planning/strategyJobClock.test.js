import test from 'node:test'
import assert from 'node:assert/strict'
import { formatJobElapsed, resolveJobStart } from './strategyJobClock.js'
import { strategyJobUrl, readStrategyJobLink } from './strategyJobLink.js'

test('경과 시각은 타이머 콜백 수 대신 실제 시간 차이로 계산하고 30분 이후에도 계속된다', () => {
  const start = Date.parse('2026-01-01T00:00:00Z')
  assert.equal(formatJobElapsed(start, start), '00:00')
  assert.equal(formatJobElapsed(start, start + 65_000), '01:05')
  assert.equal(formatJobElapsed(start, start + 1801_000), '30:01')
  assert.equal(formatJobElapsed(start, start + 3600_000), '60:00')
  assert.equal(formatJobElapsed(start, start - 1000), '00:00')
})

test('시작 시각을 URL 및 저장소로 복원하여 페이지 이동 시 초기화하지 않는다', () => {
  const values = new Map()
  globalThis.window = { localStorage: { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) } }
  const job = { job_id:'clock-resume', region_code:'30170', started_at:'2026-01-01T00:00:00Z' }
  const url = new URL(strategyJobUrl(job, '대전광역시 서구'), 'http://localhost:5176')
  assert.equal(readStrategyJobLink(url).started_at, job.started_at)
  assert.equal(resolveJobStart(job.job_id, job.started_at), Date.parse(job.started_at))
  assert.equal(resolveJobStart(job.job_id, null, Date.parse(job.started_at) + 600_000), Date.parse(job.started_at))
  globalThis.window.localStorage = { getItem() { throw Error('unavailable') }, setItem() { throw Error('unavailable') } }
  assert.equal(resolveJobStart('clock-no-storage', job.started_at), Date.parse(job.started_at))
})
