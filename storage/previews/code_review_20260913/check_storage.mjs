import { chromium } from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
import assert from 'node:assert/strict'
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true})
const page = await browser.newPage()
let polls=0, saves=0, starts=0
let expectedTitle='저장 장애 검증'
const errors=[]
page.on('requestfailed', r=>console.log('REQUEST FAILED',r.url(),r.failure()?.errorText))
page.on('console', m=>{if(m.type()==='error') console.log('BROWSER',m.text())})
page.on('pageerror', e=>errors.push(e.message))
const report={region_name:'인천광역시 부평구', summary:'검증용 기획안', reference_estimate:{items:[],total_krw:0}, strategies:[{title:'저장 장애 검증',implementation_steps:[]}]}
await page.route('**/*', async route=>{
  const url=new URL(route.request().url())
  if(url.origin!=='http://127.0.0.1:5187') return route.abort()
  if(!url.pathname.startsWith('/ai/')&&!url.pathname.startsWith('/api/')) return route.continue()
  let json={}
  if(url.pathname.endsWith('/catalog')) json={regions:[{region_code:'28237',region_name:report.region_name}]}
  if(url.pathname.endsWith('/readiness-audit')) json={regions:[{region_code:'28237',data_ready:true,generation_ready:true}]}
  if(url.pathname.endsWith('/jobs/offline-test')) {polls++;json={job_id:'offline-test',region_code:'28237',status:'completed',report}}
  if(url.pathname.endsWith('/jobs')&&route.request().method()==='POST') {starts++;json={job_id:'offline-test',region_code:'28237'}}
  if(url.pathname.endsWith('/generation-readiness')) json={data_freshness:{status:'ready',can_generate:true}}
  if(url.pathname.endsWith('/assistant-chat')) json={answer:'대역 수정안',generation_mode:'offline_sample',report_patch:{strategy_title:'수정된 기획안'}}
  if(route.request().method()==='PUT') {saves++;assert.equal(route.request().postDataJSON().strategies[0].title,expectedTitle)}
  return route.fulfill({json})
})
await page.addInitScript(()=>{
  const original=Storage.prototype.setItem
  Storage.prototype.setItem=function(key,value){
    // 조건 저장 직후 작업 ID·대형 본문을 저장할 때 공간이 소진되는 상황.
    if(key.includes('planning')) return original.call(this,key,value)
    throw new DOMException('full','QuotaExceededError')
  }
  Storage.prototype.removeItem=function(){throw new DOMException('blocked','SecurityError')}
})
try {
  await page.goto('http://127.0.0.1:5187/strategy?job_id=offline-test&region_code=28237&region_name='+encodeURIComponent(report.region_name))
  await page.getByRole('heading',{name:'저장 장애 검증'}).waitFor()
  assert.equal(new URL(page.url()).search,'')
  await page.getByRole('button',{name:'기획안 저장하기',exact:true}).click()
  await page.getByText('기획안을 저장했습니다.',{exact:true}).waitFor()
  assert.equal(saves,1)
  const before=polls
  await page.waitForTimeout(3500)
  assert.equal(polls,before,'완료 작업을 반복 조회하면 안 됨')
  assert.equal(starts,0,'복원 중 새 생성 요청 금지')
  await page.getByPlaceholder('분석 결과나 기획안에 대해 질문하세요!').fill('제목 수정')
  await page.getByRole('button',{name:'질문 전송'}).click()
  await page.getByRole('button',{name:'이 수정안을 기획안에 반영'}).click()
  await page.getByRole('heading',{name:'수정된 기획안'}).waitFor()
  expectedTitle='수정된 기획안'
  await page.getByRole('button',{name:'기획안 저장하기',exact:true}).click()
  await page.getByText('기획안을 저장했습니다.',{exact:true}).waitFor()
  assert.equal(saves,2)
  await page.goto('http://127.0.0.1:5187/planning')
  await page.getByRole('button',{name:'기획안 생성',exact:true}).click()
  await page.getByRole('heading',{name:'저장 장애 검증'}).waitFor()
  assert.equal(starts,1,'저장 공간 소진 뒤에도 서버 작업을 한 번만 시작하고 복원')
  assert.deepEqual(errors,[])
  await page.screenshot({path:'storage/previews/code_review_20260913/storage-fallback.png',fullPage:true})
  console.log('PASS: external fonts blocked; storage writes/deletes fail; URL job restored; report edited; server saves succeed; polling stops; new generation handed off exactly once. All API responses mocked.')
} catch(error) {
  console.log(JSON.stringify({errors,polls,saves,starts,text:await page.locator('body').innerText()}))
  throw error
} finally {await browser.close()}
