// UI-only check: the answer is intercepted, so no paid model calls are made.
const {chromium}=require('playwright')
const assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[]
  page.on('pageerror',e=>errors.push(e.message))
  await page.goto((process.argv[2]||'http://127.0.0.1:8017')+'/#assistant')
  const hero=page.locator('.ft-welcome-mascot .footie-mascot')
  await hero.waitFor()
  await page.waitForFunction(()=>document.querySelector('.ft-welcome-mascot [data-mood="idle"]'))
  await page.mouse.move(1300,300)
  await page.waitForFunction(()=>document.querySelector('.ft-welcome-mascot .fm-eyes').style.transform.includes('3px'))
  await page.screenshot({path:'var/footie-mascot-desktop.png',fullPage:true})
  const field=page.getByRole('textbox',{name:'Ask a football question'})
  await field.focus()
  assert.equal(await hero.getAttribute('data-mood'),'listening')
  let release
  const gate=new Promise(resolve=>{release=resolve})
  await page.route('**/api/fan/assistant/ask',async route=>{
   await gate
   await route.fulfill({json:{request_id:'mascot-ui-check',status:'answered',title:'From the match records',text:['A preview answer for the mascot interface check.'],facts:[],actions:[],visual:null,plan:{},as_of:'2026-10-20',mode:'lookup',suggestions:[]}})
  })
  await field.fill('How many goals does Mateo Cross have?')
  await page.getByRole('button',{name:'Send question'}).click()
  await page.locator('.ft-thinking [data-mood="thinking"]').waitFor()
  await page.screenshot({path:'var/footie-mascot-thinking.png',fullPage:true})
  release()
  await page.getByRole('heading',{name:'From the match records'}).waitFor()
  assert.equal(await page.locator('.ft-answer-mark .footie-mascot').count(),1)
  assert.equal(await page.locator('.ft-thinking').count(),0)
  await page.getByRole('button',{name:/New conversation/}).click()
  await hero.waitFor()
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.mouse.move(1400,10)
  assert.equal(await hero.locator('.fm-blink').evaluate(el=>getComputedStyle(el).animationName),'none')
  assert.equal(await hero.locator('.fm-eyes').evaluate(el=>getComputedStyle(el).transform),'none')
  for(const width of [390,360]){
   await page.setViewportSize({width,height:844})
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow')
   const bounds=await hero.boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=width)
   assert(await page.evaluate(()=>{
    const cards=document.querySelector('.ft-starters').getBoundingClientRect()
    const composer=document.querySelector('.ft-composer').getBoundingClientRect()
    return composer.top>=cards.bottom
   }),'composer overlaps question suggestions')
  }
  await page.screenshot({path:'var/footie-mascot-mobile.png',fullPage:true})
  assert.deepEqual(errors,[])
  console.log('PASS Footie mascot: cursor gaze, typing/listening, pending/thinking, answer avatar, reset, reduced motion, 390/360px layout; no browser errors or model calls.')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
