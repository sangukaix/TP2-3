import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
await page.route('**/ai/**',r=>r.fulfill({json:{}}));
await page.route('**/api/**',r=>r.fulfill({json:{}}));
await page.goto('http://127.0.0.1:5177/');
await page.evaluate(async()=>{
 const React=await import('/node_modules/.vite/deps/react.js');
 const dom=await import('/node_modules/.vite/deps/react-dom_client.js'); const createRoot=dom.createRoot ?? dom.default.createRoot;
 const {default:Help}=await import('/src/components/ConsumptionCategoryHelp.jsx');
 const e=React.createElement ?? React.default.createElement;
 const host=document.createElement('div');document.body.replaceChildren(host);
 host.style.cssText='max-width:570px;margin:20px auto;padding:8px;';
 const names=['운송업','쇼핑업','식음료업','의료웰니스'];
 createRoot(host).render(e('article',{className:'tourism-diagnosis'},e('div',{className:'tourism-diagnosis-heading'},e('h3',{},'소비패턴 예측')),e('div',{className:'tourism-diagnosis-body'},e('section',{className:'consumption-breakdown'},e('div',{className:'diagnostic-subheading'},e('span',{},'업종'),e('small',{},'향후 3개월 월평균 소비 전망 · ₩278억')),e('div',{className:'consumption-category-list'},...names.map((name,index)=>e(Help,{key:name,category:{name,share:[33.2,31.7,30.2,1.8][index]},index,amountLabel:['₩92억','₩88억','₩84억','₩5억'][index]})))),e('section',{className:'consumption-composition'},e('div',{className:'consumption-donut-wrap'},'그래프 영역'),e('div',{className:'consumption-donut-legend'},...names.map(name=>e('span',{key:name},name)))),e('p',{className:'consumption-method-note'},'%는 소비 비중이며 증가율이 아닙니다. 업종 옆 ?를 눌러 소비 예시를 확인하세요.'))));
});
for (const width of [1440,1024,390]) {
 await page.setViewportSize({width,height:1100});
 const b=page.getByRole('button',{name:'운송업 소비 항목 설명'});
 await b.click();await page.getByText('차량 대여: 렌터카 이용',{exact:true}).waitFor();
 assert.equal(await b.getAttribute('aria-expanded'),'true');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 const clipped=await page.locator('.consumption-category-name > span,.consumption-donut-legend span').evaluateAll(nodes=>nodes.filter(n=>n.scrollWidth>n.clientWidth+1).map(n=>n.textContent));
 assert.deepEqual(clipped,[]);
 await page.screenshot({path:`C:/Users/Admin/mbca/TP2-3/storage/previews/consumption-help-${width}.png`,fullPage:true});
 await b.press('Escape');assert.equal(await b.getAttribute('aria-expanded'),'false');
 await b.focus();await b.press('Enter');assert.equal(await b.getAttribute('aria-expanded'),'true');await b.click();
}
await browser.close();console.log('PASS desktop/tablet/mobile: full labels, click/Enter/Escape, no horizontal overflow');


