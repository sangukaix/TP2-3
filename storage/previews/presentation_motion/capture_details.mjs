import fs from 'node:fs/promises';
import { chromium } from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_motion';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:2});
const requests=[];
page.on('response',async res=>{if(res.url().includes('/dashboard')){try{await fs.writeFile(dir+'/dashboard_api.json',JSON.stringify(await res.json(),null,2));}catch{}}});
page.on('request',r=>{if(r.url().includes('/ai/')||r.url().includes('/api/'))requests.push({method:r.method(),url:r.url()});});
await page.goto('http://localhost:5176/dashboard',{waitUntil:'domcontentloaded'});
await page.locator('.metric-card').first().waitFor();
await page.waitForFunction(()=>document.querySelector('.metric-card')?.innerText.includes('17,767,384'));
await page.waitForTimeout(1200);
await page.mouse.move(0,0);
for(const [name,selector] of [['map','.map-panel'],['trend','.trend-panel'],['consumption','.tourism-diagnosis']]){
 await page.locator(selector).screenshot({path:dir+'/dashboard_'+name+'.png'});
}
const cards=await page.locator('.metric-card').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}));
const x=Math.min(...cards.map(r=>r.x)),y=Math.min(...cards.map(r=>r.y));
await page.screenshot({path:dir+'/dashboard_metrics.png',clip:{x,y,width:Math.max(...cards.map(r=>r.x+r.width))-x,height:Math.max(...cards.map(r=>r.y+r.height))-y}});
await page.goto('http://localhost:5176/planning',{waitUntil:'domcontentloaded'});
await page.waitForTimeout(900);
await page.screenshot({path:dir+'/planning.png'});
await fs.writeFile(dir+'/requests.json',JSON.stringify(requests,null,2));
await browser.close();console.log('Detail captures complete');
