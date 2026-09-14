import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:2400},deviceScaleFactor:1.5});
await page.goto('http://localhost:5176/openai-test',{waitUntil:'domcontentloaded'});await page.locator('.agent-output').waitFor({timeout:30000});await page.waitForTimeout(1000);
const b=await page.locator('.openai-agent-map').evaluate(e=>{const a=e.getBoundingClientRect(),b=e.querySelector('.agent-output').getBoundingClientRect();return {x:a.x,y:a.y,width:a.width,height:b.bottom-a.top+12};});
await page.screenshot({path:'C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_revision/agent_flow.png',clip:b});await browser.close();console.log('Agent flow captured');
