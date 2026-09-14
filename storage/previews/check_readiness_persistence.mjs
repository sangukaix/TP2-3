import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage();let mode='ready';
await page.route('**/ai/v1/**',r=>{
 if(mode==='network')return r.abort();
 return r.fulfill({json:{status:'completed',regions:[{region_code:'43114',region_name:'청원구',data_ready:mode!=='sql',generation_ready:mode==='ready',readiness_reason:mode==='sql'?'SQL 연결 확인 필요':null}],local_model_message:mode==='ready'?'Qwen·Gemma 연결 확인':'Qwen·Gemma 연결 또는 모델 설정 확인 필요'}});
});
await page.route('**/api/v1/**',r=>r.fulfill({json:{}}));
await page.goto('http://127.0.0.1:5176');
await page.evaluate(async()=>{
 const R=await import('/node_modules/.vite/deps/react.js');const e=R.createElement??R.default.createElement;
 const D=await import('/node_modules/.vite/deps/react-dom_client.js');const root=D.createRoot??D.default.createRoot;
 const {default:Picker}=await import('/src/components/RegionWorkspacePicker.jsx');
 const refreshers=[]; window.setInterval=(fn,ms)=>{if(ms===60000) refreshers.push(fn);return 0}; window.testRefresh=()=>refreshers.forEach(fn=>fn());
 const host=document.createElement('div');document.body.replaceChildren(host);
 root(host).render(e(Picker,{region:{code:'43114',name:'청원구'},onChange:()=>{}}));
});
const select=page.locator('select');
await page.getByText('청원구 · 자료 준비됨',{exact:true}).waitFor({state:'attached'});
assert.equal(await select.evaluate(n=>getComputedStyle(n).color),'rgb(21, 128, 61)');
mode='offline';await page.evaluate(()=>window.testRefresh());
await page.getByText('Qwen·Gemma 연결 또는 모델 설정 확인 필요',{exact:true}).waitFor({state:'attached'});
assert.equal(await select.evaluate(n=>getComputedStyle(n).color),'rgb(21, 128, 61)');
mode='network';await page.evaluate(()=>window.testRefresh());
await page.getByText('상태 조회 연결 끊김 · 마지막 확인 결과 표시',{exact:true}).waitFor({state:'attached'});
assert.equal(await select.evaluate(n=>getComputedStyle(n).color),'rgb(21, 128, 61)');
mode='sql';await page.evaluate(()=>window.testRefresh());
await page.getByText('청원구 · SQL 연결 확인 필요',{exact:true}).waitFor({state:'attached'});
assert.notEqual(await select.evaluate(n=>getComputedStyle(n).color),'rgb(21, 128, 61)');
mode='ready';await page.evaluate(()=>window.testRefresh());
await page.getByText('청원구 · 자료 준비됨',{exact:true}).waitFor({state:'attached'});
assert.equal(await select.evaluate(n=>getComputedStyle(n).color),'rgb(21, 128, 61)');
await browser.close();console.log('PASS data green persists through LLM offline/network errors; SQL failure removes green; recovery restores it');



