// Local UI regression. AI requests are blocked; narration uses a generated silent
// recording to check media continuity, not Azure voice quality or synthesis.
const {chromium}=require('playwright')
const assert=require('node:assert/strict')
const fs=require('node:fs')
function silentRecording(seconds=12){
 const n=seconds*8000*2,b=Buffer.alloc(44+n)
 b.write('RIFF');b.writeUInt32LE(36+n,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16)
 b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28)
 b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n,40)
 return b.toString('base64')
}
;(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
 const base=process.argv[2]||'http://127.0.0.1:8017',errors=[],results=[]
 fs.mkdirSync('var/layout-validation',{recursive:true})
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}})
  page.on('pageerror',e=>errors.push(e.message))
  let audioRequests=0,aiRequests=0
  await page.route('**/api/fan/assistant/ask',route=>{aiRequests++;return route.abort()})
  await page.route('**/api/voice/config',route=>route.fulfill({json:{azure:true}}))
  await page.route('**/api/voice/highlight',route=>{
   audioRequests++;const count=route.request().postDataJSON().events.length
   return route.fulfill({json:{audio:silentRecording(),duration:12,event_count:count,markers:[{at:1,position:.5,text:'Start'},{at:11,position:count-.5,text:'Finish'}]}})
  })
  await page.addInitScript(()=>{
   window.__audio=[];const NativeAudio=window.Audio
   window.Audio=function(...args){const audio=new NativeAudio(...args);window.__audio.push(audio);return audio}
   window.Audio.prototype=NativeAudio.prototype
  })
  await page.goto(base+'/?story=last-gasp#matchday')
  const pitch=page.getByRole('region',{name:'Match pitch',exact:true}),slider=page.getByRole('slider',{name:'Replay position'})
  await pitch.waitFor()
  assert.equal(await pitch.locator('.fan-pitch-player').count(),22)
  assert.equal(await page.getByRole('link',{name:'Explore data',exact:true}).count(),0)
  const canvasTop=await pitch.locator('.fan-pitch-canvas').evaluate(e=>e.getBoundingClientRect().top)
  assert(canvasTop<650,'Pitch should appear earlier on a desktop screen')
  await pitch.evaluate(el=>el.dataset.mount='original')
  await slider.fill('432')
  await pitch.getByRole('button',{name:'Rory Ellis, Eastbridge',exact:true}).locator('.player-disc').click()
  await page.getByRole('link',{name:'Breakdown',exact:true}).click()
  await page.getByRole('heading',{name:'Who was involved?'}).waitFor()
  assert.equal(await slider.inputValue(),'432')
  assert.equal(await pitch.getAttribute('data-mount'),'original')
  assert.equal(await pitch.getByRole('button',{name:'Rory Ellis, Eastbridge',exact:true}).getAttribute('aria-pressed'),'true')
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await page.getByLabel('Second phase',{exact:true}).selectOption('2')
  assert((await page.getByRole('table').innerText()).includes('Saves'))
  await page.getByRole('button',{name:'Show second phase'}).click()
  await page.waitForFunction(()=>document.querySelector('input[aria-label="Replay position"]').value==='700')
  assert.equal(await slider.inputValue(),'700')
  await page.getByLabel('Show routes',{exact:true}).uncheck()
  await page.getByRole('link',{name:'Watch',exact:true}).click()
  await page.getByRole('link',{name:'Breakdown',exact:true}).click()
  assert.equal(await page.getByLabel('Second phase',{exact:true}).inputValue(),'2')
  assert.equal(await page.getByLabel('Show routes',{exact:true}).isChecked(),false)
  await page.goBack();await page.goBack()
  assert.equal(await slider.inputValue(),'700')
  results.push('Watch/Breakdown/history: same mounted pitch, exact seek, player, comparison and route preferences retained')
  // An actual HTMLAudioElement continues playing while the interface changes.
  await page.getByRole('link',{name:'Watch',exact:true}).click()
  await page.getByRole('button',{name:/^Listen/}).click()
  await page.getByRole('button',{name:/^Play highlight/}).click()
  await page.waitForFunction(()=>window.__audio.length===1&&!window.__audio[0].paused&&window.__audio[0].currentTime>.2)
  const audioTime=await page.evaluate(()=>window.__audio[0].currentTime)
  await page.getByRole('link',{name:'Breakdown',exact:true}).click()
  await page.waitForFunction(t=>window.__audio[0].currentTime>t+.3,audioTime)
  assert.equal(await page.evaluate(()=>window.__audio[0].paused),false)
  assert.equal(audioRequests,1)
  await page.getByRole('button',{name:/^Pause play/}).click()
  results.push('Instrumented narration: one recording, no refetch/restart/pause on view switch')
  await page.getByRole('button',{name:/^Sound off/}).click()
  await page.getByRole('button',{name:'Build-up',exact:true}).click()
  for(const [name,route,ready] of [
   ['watch','?story=last-gasp#matchday','.fan-pitch'],
   ['breakdown','?story=last-gasp#matchday/breakdown','.explore-insights'],
   ['centre','?match=wyscout-2058017#gi','.gi-overview'],
   ['clubhouse','#football','.fh-player-card'],
   ['footie','#assistant','.ft-composer textarea']]){
   await page.goto(base+'/'+route);await page.locator(ready).first().waitFor()
   if(name==='clubhouse')await page.locator('.fh-player-card').first().waitFor()
   for(const width of [1440,768,390,360]){
    await page.setViewportSize({width,height:1000})
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name+' overflow '+width)
    for(const control of await page.locator('.cp-navigation a').all()){
     const b=await control.boundingBox();assert(b&&b.x>=0&&b.x+b.width<=width,name+' hidden navigation')
    }
    await page.screenshot({path:`var/layout-validation/${name}-${width}.png`,fullPage:name!=='clubhouse'})
    if(width===360){await page.screenshot({path:`var/layout-validation/${name}-mobile-viewport.png`});if(name==='watch'||name==='breakdown')await page.locator('.fan-pitch').screenshot({path:`var/layout-validation/${name}-mobile-pitch.png`})}
   }
  }
  results.push('Watch, Breakdown, Match Centre, Clubhouse and Footie: no horizontal overflow; all main navigation visible at 1440/768/390/360px')
  await page.goto(base+'/?story=last-gasp#matchday/breakdown')
  await page.getByRole('complementary',{name:'Highlight insights'}).waitFor()
  await page.getByRole('combobox',{name:'Language',exact:true}).selectOption('zh-Hans')
  await page.getByRole('heading',{name:'机会是怎样形成的？'}).waitFor()
  await page.getByRole('button',{name:'比较',exact:true}).click()
  assert((await page.getByRole('table').innerText()).includes('扑救'))
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Chinese overflow')
  await page.getByLabel('第二阶段',{exact:true}).selectOption('2')
  await page.getByRole('button',{name:'查看第二阶段'}).click()
  await page.screenshot({path:'var/layout-validation/breakdown-zh-360.png',fullPage:true})
  results.push('Chinese at 360px: translated views, phase comparison and seek controls usable')
  await page.getByRole('combobox',{name:'Language',exact:true}).selectOption('en')
  await page.goto(base+'/?match=wyscout-2058017#gi')
  await page.getByRole('button',{name:'Moments',exact:true}).click()
  await page.getByRole('slider',{name:'Play sequence progress'}).waitFor()
  await page.getByRole('button',{name:/Shot map/}).click()
  const shot=page.locator('.gi-shot-pin').first();await shot.focus();await shot.press('Enter')
  await page.getByRole('button',{name:'Selected play',exact:true}).click()
  await page.getByRole('slider',{name:'Play sequence progress'}).fill('1')
  await page.getByRole('button',{name:'Ask Footie',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Ask Footie',exact:true})
  await dialog.getByRole('textbox',{name:'Ask a football question'}).waitFor()
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth),'Footie drawer overflow')
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('slider',{name:'Play sequence progress'}).inputValue(),'1')
  await page.getByText('Filters · club, player & half',{exact:true}).click()
  await page.getByRole('button',{name:'Northport',exact:true}).click()
  await page.getByRole('combobox',{name:'Player',exact:true}).selectOption({index:1})
  await page.getByRole('button',{name:'2nd half',exact:true}).click()
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'filtered moments overflow')
  results.push('Match Centre: keyboard shot map, animated replay, filters and Footie open/close preserve paused context at 360px')
  await page.goto(base+'/#football')
  await page.getByRole('textbox',{name:'Search players'}).fill('zz-no-player-zz')
  await page.getByRole('heading',{name:'No players found'}).waitFor()
  await page.getByRole('button',{name:'Show all players'}).click()
  await page.locator('.fh-player-card').first().waitFor()
  assert.equal(await page.locator('.fh-player-card').count(),44)
  let fail=true
  await page.route('**/api/scenarios/one-touch/snapshot?*',route=>fail?route.fulfill({status:503,json:{detail:'Test outage'}}):route.continue())
  await page.goto(base+'/?story=one-touch#explore')
  await page.getByRole('alert').waitFor()
  assert.equal(await page.getByRole('region',{name:'Match pitch',exact:true}).count(),0)
  fail=false;await page.getByRole('button',{name:'Try again',exact:true}).click()
  await page.getByRole('complementary',{name:'Highlight insights'}).waitFor()
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.getByRole('button',{name:/Show ball movement/}).click()
  assert(await page.getByRole('button',{name:/Show ball movement/}).isEnabled())
  await page.setViewportSize({width:720,height:500})
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'720 CSS pixel reflow overflow')
  results.push('Empty directory reset, snapshot outage/retry, legacy Explore link, reduced-motion controls and 720px reflow pass')
  assert.equal(aiRequests,0);assert.deepEqual(errors,[])
  console.log('PASS\n'+results.map(s=>'• '+s).join('\n')+'\nNo assistant requests or browser errors. Azure voice was stubbed; no paid synthesis.')
  fs.writeFileSync('var/layout-validation/results.json',JSON.stringify({results,canvasTop,audioRequests,aiRequests,errors},null,2))
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
