const {chromium}=require('playwright')
const assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})})
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}})
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  const base=process.argv[2]||'http://127.0.0.1:8010'
  await page.goto(`${base}/?story=level-first#matchday`)
  const panel=page.getByRole('region',{name:'Live Companion',exact:true})
  await panel.waitFor()
  assert.equal(await page.locator('.fan-pitch-player').count(),22)
  await panel.getByRole('button',{name:/Follow the play/}).click()
  await panel.getByRole('button',{name:'What just happened?'}).click()
  await panel.getByText(/still unfolding/).waitFor()
  await page.getByRole('button',{name:/Play highlight/}).click()
  await page.waitForTimeout(2500)
  await page.getByRole('button',{name:/Pause play/}).click()
  await panel.getByRole('button',{name:'Show me the numbers'}).click()
  assert((await panel.innerText()).includes('In this sequence so far:'))
  await page.getByRole('button',{name:/Restart/}).click()
  assert.equal(await panel.getByText(/In this sequence so far/).count(),0)
  await panel.screenshot({path:'var/live-companion-desktop.png'})
  for(const width of [360,390,760]){
   await page.setViewportSize({width,height:844})
   await panel.scrollIntoViewIfNeeded()
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`)
  }
  await page.setViewportSize({width:390,height:844})
  await panel.screenshot({path:'var/live-companion-mobile.png'})
  assert.deepEqual(errors,[])
  console.log('PASS Live Companion: Matchday integration, 22 players, pending outcome, playback-scoped answers, rewind invalidation, desktop and 360/390/760px, no browser errors.')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
