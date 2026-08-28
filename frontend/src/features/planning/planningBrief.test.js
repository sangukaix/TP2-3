import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyPlanningBrief, validatePlanningBrief, savePlanningDraft, readPlanningDraft, briefBudget, briefPeriod } from './planningBrief.js'

test('미정은 예산 0원이 아니며 유효하다', () => {
  const value = emptyPlanningBrief('11680')
  assert.equal(value.budget_max_krw, null)
  assert.equal(validatePlanningBrief(value), '')
  assert.match(briefBudget(value), /미정/)
})
test('예산과 일정 역전 검증', () => {
  const value = { ...emptyPlanningBrief('11680'), budget_status: 'confirmed', budget_max_krw: 100, budget_min_krw: 200 }
  assert.match(validatePlanningBrief(value), /최소 예산/)
  assert.match(validatePlanningBrief({ ...emptyPlanningBrief('11680'), schedule_status: 'fixed', start_date: '2026-12-01', end_date: '2026-11-01' }), /종료일/)
})
test('입력 중인 빈 금액이나 날짜를 0원 또는 확정 일정으로 보여주지 않는다', () => {
  const value = { ...emptyPlanningBrief('11680'), budget_status: 'confirmed', schedule_status: 'fixed' }
  assert.equal(briefBudget(value), '금액 입력 필요')
  assert.equal(briefPeriod(value), '날짜 입력 필요')
})
test('초안은 지역별로 격리되어 저장된다', () => {
  const data = new Map()
  globalThis.window = { localStorage: { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) } }
  const value = { ...emptyPlanningBrief('11680'), hard_constraints: '야간 제외' }
  savePlanningDraft(value)
  assert.equal(readPlanningDraft('11680').hard_constraints, '야간 제외')
  assert.equal(readPlanningDraft('28245').hard_constraints, '')
  delete globalThis.window
})
