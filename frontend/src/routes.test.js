import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveAppRoute, resolveProjectTreeUrl } from './routes.js'

test('공개 화면 경로와 trailing slash를 명시적으로 해석한다', () => {
  assert.deepEqual(resolveAppRoute('/dashboard/'), {
    requestedPath: '/dashboard',
    canonicalPath: '/dashboard',
    pageId: 'dashboard',
    found: true,
  })
  assert.equal(resolveAppRoute('/planning').pageId, 'planning')
})

test('과거 주소는 지정된 화면으로만 연결한다', () => {
  assert.equal(resolveAppRoute('/diagnosis').canonicalPath, '/dashboard')
  assert.equal(resolveAppRoute('/proposal').canonicalPath, '/strategy')
})

test('알 수 없는 주소를 대시보드로 오인하지 않는다', () => {
  assert.deepEqual(resolveAppRoute('/missing'), {
    requestedPath: '/missing',
    canonicalPath: '/missing',
    pageId: null,
    found: false,
  })
})

test('구조 탐색기는 React에 접속한 같은 호스트의 8501 포트를 사용한다', () => {
  assert.equal(resolveProjectTreeUrl('', 'http://192.168.0.23:5176/react-test'), 'http://192.168.0.23:8501')
  assert.equal(resolveProjectTreeUrl('http://tree-host:9500/', 'http://localhost:5176'), 'http://tree-host:9500')
})
