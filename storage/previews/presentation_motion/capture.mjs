import fs from 'node:fs/promises';
import { chromium } from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_motion';
await fs.mkdir(dir+'/frames',{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const page=await context.newPage();
await page.goto('http://localhost:5176/',{waitUntil:'networkidle'});
await page.locator('.home-process').scrollIntoViewIfNeeded();
await page.getByRole('button',{name:'01 분석 지역 선택'}).click();
const clip=await page.locator('.home-workflow-layout').boundingBox();
await page.screenshot({path:dir+'/home_poster.png',clip});
const frames=[];const start=Date.now();
for(let i=0;Date.now()-start<16000;i++){
 const time=Date.now()-start;
 await page.screenshot({path:dir+'/frames/'+String(i).padStart(4,'0')+'.png',clip});
 frames.push({file:String(i).padStart(4,'0')+'.png',time,step:await page.locator('.home-step-rail li.is-active').innerText()});
 await page.waitForTimeout(Math.max(0,(i+1)*100-(Date.now()-start)));
}
await fs.writeFile(dir+'/frames.json',JSON.stringify({duration:Date.now()-start,clip,frames},null,2));
await page.goto('http://localhost:5176/dashboard',{waitUntil:'networkidle'});
await page.waitForTimeout(1800);
await page.screenshot({path:dir+'/dashboard_full.png',fullPage:true});
await page.screenshot({path:dir+'/dashboard_top.png'});
await fs.writeFile(dir+'/dashboard_dom.txt',await page.locator('body').innerText());
await fs.writeFile(dir+'/dashboard_selectors.json',JSON.stringify(await page.locator('main section, main article, main h2, select').evaluateAll(es=>es.map(e=>({tag:e.tagName,cls:e.className,text:e.innerText.slice(0,160)}))),null,2));
await browser.close();
console.log('Captured',frames.length,'motion frames and dashboard');
