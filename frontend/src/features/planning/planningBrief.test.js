import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyPlanningBrief, validatePlanningBrief, savePlanningDraft, readPlanningDraft, briefBudget, briefPeriod, planningContextCharCount } from './planningBrief.js'
import { threeMonthSchedule, nextThreeMonthSchedule, simplifiedDraft } from './planningBrief.js'

test('간편 일정은 연도 경계를 넘어 3개월 말일까지 계산한다', () => {
  assert.deepEqual(threeMonthSchedule('2026-12'), { schedule_status: 'fixed', start_date: '2026-12-01', end_date: '2027-02-28' })
})
test('간편 입력은 숨겨진 구형 조건을 전송하지 않는다', () => {
  const legacy={...emptyPlanningBrief('51110'),visitor_target_pct:20,spending_target_pct:30,budget_hard_limit:true,preferences:'선호',hard_constraints:'구형 조건'}
  globalThis.window={localStorage:{getItem:()=>JSON.stringify({brief:legacy})}}
  const brief=simplifiedDraft('51110')
  assert.equal(brief.visitor_target_pct,null)
  assert.equal(brief.budget_hard_limit,false)
  assert.equal(brief.hard_constraints,'')
  assert.equal(brief.field_context,'')
  assert.deepEqual(brief.excluded_operations,[])
  assert.equal(brief.input_profile,'guided_v2')
  assert.match(validatePlanningBrief({...brief,input_profile:'guided_v1',business_direction:'night_time_experience',excluded_operations:['night_time_experience']}),/충돌/)
})

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
test('자유 입력과 첨부문서의 합계가 문맥 한도를 넘으면 생성 전에 막는다', () => {
  const valid = { ...emptyPlanningBrief('11680'), field_context: '가'.repeat(3000), references: [{ name: 'memo.txt', text: '나'.repeat(3000) }] }
  assert.equal(planningContextCharCount(valid), 6000)
  assert.equal(validatePlanningBrief(valid), '')
  assert.match(validatePlanningBrief({ ...valid, preferences: '추가' }), /합계 6,000자/)
})

test('한국 시간 월 경계와 연도 경계에서 다음 세 달을 선택한다', () => {
  assert.deepEqual(nextThreeMonthSchedule(new Date('2026-09-01T00:00:00+09:00')), {schedule_status:'fixed',start_date:'2026-10-01',end_date:'2026-12-31'})
  assert.deepEqual(nextThreeMonthSchedule(new Date('2026-09-30T15:00:00Z')), {schedule_status:'fixed',start_date:'2026-11-01',end_date:'2027-01-31'})
  assert.equal(nextThreeMonthSchedule(new Date('2027-11-01T00:00:00+09:00')).end_date,'2028-02-29')
})
test('새 선택형 초안은 구형 자유 입력 초안을 덮어쓰지 않는다', () => {
  const data = new Map()
  globalThis.window = {localStorage:{getItem:(key)=>data.get(key),setItem:(key,value)=>data.set(key,value)}}
  savePlanningDraft({...emptyPlanningBrief('11680'),field_context:'이전 메모'})
  const old = data.get('tour-insight-planning-brief-11680')
  savePlanningDraft({...simplifiedDraft('11680'),resource_options:['merchants'],context_options:['families']})
  assert.equal(data.get('tour-insight-planning-brief-11680'),old)
  assert.deepEqual(simplifiedDraft('11680').resource_options,['merchants'])
  delete globalThis.window
})
