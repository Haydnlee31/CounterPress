const {chromium}=require('playwright'),assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})})
 try{
  const page=await browser.newPage()
  await page.addInitScript(()=>{
   const NativeAudio=window.Audio;window.audioCompletions=[]
   window.Audio=function(...args){const a=new NativeAudio(...args);a.addEventListener('ended',()=>window.audioCompletions.push(a.duration));return a}
  })
  const base=process.argv[2]||'http://127.0.0.1:8011'
  await page.goto(`${base}/#live`)
  await page.getByRole('button',{name:'Play match',exact:true}).waitFor()
  const panel=page.getByRole('region',{name:'Live Companion',exact:true})
  await panel.getByRole('button',{name:/Follow the play/}).click()
  await page.getByRole('combobox',{name:'Commentary voice'}).waitFor()
  for(const language of ['en','zh-Hans']){
   await page.getByRole('combobox',{name:'Commentary language'}).selectOption(language)
   await page.getByRole('slider',{name:'Match clock'}).evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'1207000');el.dispatchEvent(new Event('input',{bubbles:true}))})
   if(language==='en')await panel.getByRole('button',{name:/Listen/}).click()
   const response=page.waitForResponse(r=>r.url().endsWith('/api/voice/commentary')&&r.request().method()==='POST')
   await page.getByRole('button',{name:language==='en'?'Play match':'播放比赛',exact:true}).click()
   assert.equal((await response).status(),200)
   const expected=language==='en'?1:2
   await page.waitForFunction(count=>window.audioCompletions.length>=count,expected,{timeout:30000})
   await page.getByRole('button',{name:language==='en'?'Pause match':'暂停比赛',exact:true}).click()
  }
  const durations=await page.evaluate(()=>window.audioCompletions)
  assert(durations.every(d=>Number.isFinite(d)&&d>1))
  console.log('PASS real Azure MP3 playback completed in English and Mandarin:',durations.map(d=>d.toFixed(2)+'s').join(', '))
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
