import test from 'node:test'
import assert from 'node:assert/strict'
import { applyReportPatch } from './applyReportPatch.js'
import { chatHistory } from './chatHistory.js'

test('계획 목표와 임시 견적만 조정하고 관측·ML 값은 보존한다', () => {
  const report = { strategies: [{}], ml_analysis: { visitors: 100 }, target_proposal_basis: { explanation: '기존 목표' } }
  const next = applyReportPatch(report, { execution_scenario: { visitor_target_pct: 4, spending_target_pct: 5 },
    reference_estimate: { status: 'planning_assumption_not_quote', total_krw: 100, items: [{ name: '운영', amount: 100 }] }, ml_analysis: { visitors: 999 } })
  assert.equal(next.execution_scenario.visitor_target_pct, 4)
  assert.equal(next.reference_estimate.total_krw, 100)
  assert.equal(next.ml_analysis.visitors, 100)
  assert.equal(next.target_proposal_basis, undefined)
  assert.equal(report.execution_scenario, undefined)
  const invalid = applyReportPatch(report, { execution_scenario: { visitor_target_pct: Infinity, spending_target_pct: 5 },
    reference_estimate: { status: 'planning_assumption_not_quote', total_krw: 100, items: [{ amount: 90 }] } })
  assert.equal(invalid.execution_scenario, undefined)
  assert.equal(invalid.reference_estimate, undefined)
})

test('두 번째 질문의 AI 답변도 role/content로 전송한다', () => {
  assert.deepEqual(chatHistory([{ role: 'user', content: '질문' }, { role: 'assistant', answer: '답변', execution: {} }, { role: 'user', content: '추가 질문' }]),
    [{ role: 'user', content: '질문' }, { role: 'assistant', content: '답변' }, { role: 'user', content: '추가 질문' }])
})

test('빈 수정·예측 변조를 막고 원본과 다른 전략을 보존한다', () => {
  const report = { summary: '요약', strategies: [{ title: '제목', solution: '기존', budget: '예산' }, { title: '다른 전략' }], ml_analysis: { value: 10 }, quality_review: { approved: true } }
  const next = applyReportPatch(report, { solution: '  ', budget: '변조', ml_analysis: { value: 99 }, strategy_title: '새 제목' })
  assert.equal(next.strategies[0].solution, '기존')
  assert.equal(next.strategies[0].budget, '예산')
  assert.equal(next.strategies[0].title, '새 제목')
  assert.equal(next.ml_analysis.value, 10)
  assert.equal(next.quality_review.review_stale, true)
  assert.equal(next.quality_review.approved, false)
  assert.equal(report.strategies[0].title, '제목')
  assert.deepEqual(next.strategies[1], report.strategies[1])
})
test('잘린 실행 단계로 기존 단계를 덮어쓰지 않는다', () => {
  const report = { strategies: [{ implementation_steps: [{ task: '원래' }] }] }
  assert.deepEqual(applyReportPatch(report, { implementation_steps: [{}] }).strategies[0].implementation_steps, report.strategies[0].implementation_steps)
  assert.equal(applyReportPatch(null, {}), null)
})
