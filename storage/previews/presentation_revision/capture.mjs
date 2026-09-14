import fs from 'node:fs/promises';
import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_revision';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1.5});
const requests=[];page.on('request',r=>{if(r.url().includes('/ai/')||r.url().includes('/api/'))requests.push({method:r.method(),url:r.url()});});
for(const [name,route] of [['ml','ml-test'],['agents','openai-test'],['router','llm-control'],['saved','saved-plans']]){
 try{await page.goto('http://localhost:5176/'+route,{waitUntil:'domcontentloaded',timeout:20000});await page.waitForTimeout(5500);await page.screenshot({path:dir+'/'+name+'.png'});await fs.writeFile(dir+'/'+name+'.txt',await page.locator('body').innerText());await fs.writeFile(dir+'/'+name+'_selectors.json',JSON.stringify(await page.locator('main section,main article, main header').evaluateAll(es=>es.map(e=>({tag:e.tagName,cls:e.className,text:e.innerText.slice(0,200)}))),null,2));console.log(name,'captured');}catch(e){console.log(name,e.message);}
}
await fs.writeFile(dir+'/requests.json',JSON.stringify(requests,null,2));await browser.close();
