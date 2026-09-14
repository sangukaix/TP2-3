import fs from 'node:fs/promises';
import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_revision';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const requests=[];
await Promise.all(['ml-test','llm-control','openai-test','saved-plans'].map(async(route)=>{
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1.5});
page.on('request',r=>{if(r.url().includes('/ai/'))requests.push({method:r.method(),url:r.url()});});
try{
await page.goto('http://localhost:5176/'+route,{waitUntil:'domcontentloaded'});
if(route==='llm-control') {await page.locator('.llm-routing-panel').waitFor({timeout:180000});await page.locator('.llm-provider-grid').screenshot({path:dir+'/providers.png'});await page.locator('.llm-routing-panel').screenshot({path:dir+'/routing.png'});}
if(route==='ml-test') {await page.locator('.ml-module-card').first().waitFor({timeout:180000});await page.locator('.ml-module-card').first().screenshot({path:dir+'/ml_module.png'});}
if(route==='openai-test'){await page.waitForTimeout(3000);}
if(route==='saved-plans'){await page.getByRole('button',{name:'성동구 지역상품권 환급 프로그램',exact:true}).waitFor({timeout:60000});await page.getByRole('button',{name:'성동구 지역상품권 환급 프로그램',exact:true}).click();await page.locator('.saved-plan-modal').waitFor({timeout:60000});await page.locator('.saved-plan-modal').screenshot({path:dir+'/saved_modal.png'});}
await page.screenshot({path:dir+'/'+route+'_ready.png'});await fs.writeFile(dir+'/'+route+'_ready.txt',await page.locator('body').innerText());console.log(route,'ready');
}catch(e){await fs.writeFile(dir+'/'+route+'_error.txt',await page.locator('body').innerText());console.log(route,e.message);}
await page.close();}));
await fs.writeFile(dir+'/read_requests.json',JSON.stringify(requests,null,2));await browser.close();
