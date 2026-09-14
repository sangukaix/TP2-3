import test from 'node:test'
import assert from 'node:assert/strict'
import { strategyJobUrl, readStrategyJobLink, clearStrategyJobLink } from './strategyJobLink.js'

test('서버 작업은 지역명과 함께 URL로 복원하며 브라우저 저장소가 필요 없다', () => {
  const job = { job_id: 'abc-123', region_code: '28237' }
  const url = new URL(strategyJobUrl(job, '인천광역시 부평구'), 'http://localhost:5176')
  assert.deepEqual(readStrategyJobLink(url), { ...job, region_name: '인천광역시 부평구' })
  assert.equal(readStrategyJobLink(new URL('http://localhost/planning' + url.search)), null)
  assert.equal(readStrategyJobLink(new URL('http://localhost/strategy?job_id=abc&region_code=all&region_name=전국')), null)
})

test('완료 후 작업 식별자만 지우고 다른 주소 상태는 유지한다', () => {
  let replaced
  globalThis.window = {
    location: { href: 'http://localhost/strategy?job_id=abc&region_code=28237&region_name=x&view=detail#body' },
    history: { state: { keep: true }, replaceState: (state, _, url) => { replaced = { state, url } } },
  }
  clearStrategyJobLink()
  assert.equal(replaced.url.href, 'http://localhost/strategy?view=detail#body')
  assert.deepEqual(replaced.state, { keep: true })
})
