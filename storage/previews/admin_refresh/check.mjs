import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const root='C:/Users/Admin/mbca/TP2-3/storage/previews/admin_refresh';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/ai/**',r=>{const path=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')return r.abort();const topic=path.endsWith('/learning/openai')?'openai':path.endsWith('/learning/react')?'react':null;return r.fulfill({json:topic?JSON.parse(fs.readFileSync(`${root}/${topic}.json`,'utf8')):path.endsWith('/llm/config')?{mode:'student_budget',routes:{planner:{provider:'gemma',model:'gemma',fallback:'none'}}}:path.endsWith('/llm/status')?{providers:[],cost_policy:{student_budget:true}}:path.endsWith('/llm/trace')?{events:[]}: {status:'inactive',message:'UI test: no model calls'}})});
const checks=[];
for(const route of ['openai-test','react-test','llm-control']){
 await page.setViewportSize({width:1600,height:1000});await page.goto(`http://127.0.0.1:5180/${route}`);await page.locator('.learning-tutor').waitFor();
 const width=await page.locator('.learning-tutor').evaluate(e=>Math.round(e.getBoundingClientRect().width));assert.equal(width,340);
 await page.screenshot({path:`${root}/${route}.png`});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:`${root}/${route}-mobile.png`});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);checks.push({route,width,overflow});
}
console.log(JSON.stringify({checks,errors}));await browser.close();
