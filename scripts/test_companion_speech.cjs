const {chromium}=require('playwright')
const assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})})
 try{
  const page=await browser.newPage()
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  // A deliberately slow four-second voice tests real playback against speech completion.
  // This verifies scheduling, not audible voice quality on the user's device.
  await page.addInitScript(()=>{
   let current=null,timer=null
   window.voiceLog=[]
   window.SpeechSynthesisUtterance=class {constructor(text){this.text=text}}
   Object.defineProperty(window,'speechSynthesis',{value:{
    getVoices:()=>[],
    cancel:()=>{if(current){window.voiceLog.push({kind:'interrupted',text:current.text});clearTimeout(timer);current=null}},
    speak:u=>{if(current)throw Error('Overlapping speech');current=u;window.voiceLog.push({kind:'start',text:u.text});timer=setTimeout(()=>{current=null;window.voiceLog.push({kind:'end',text:u.text});u.onend?.()},4000)},
   }})
  })
  const base=process.argv[2]||'http://127.0.0.1:8010'
  for(const story of ['last-gasp','level-first','level-late']){
   await page.goto(`${base}/?story=${story}#matchday`)
   const panel=page.getByRole('region',{name:'Live Companion',exact:true})
   await panel.waitFor()
   const config=await (await page.request.get(`${base}/api/voice/config`)).json()
   if(config.azure){await panel.getByRole('button',{name:/Follow the play/}).click();await page.getByRole('combobox',{name:'Commentary voice'}).selectOption('device')}
   await page.getByRole('combobox',{name:'Pitch replay speed'}).selectOption('1.5')
   await page.getByRole('button',{name:/Listen/}).click()
   await page.getByRole('button',{name:/Play highlight/}).click()
   await page.getByRole('button',{name:/Pause play/}).waitFor()
   await page.getByRole('button',{name:/Play highlight/}).waitFor({timeout:60000})
   await page.waitForTimeout(8500)
   const log=await page.evaluate(()=>window.voiceLog)
   assert.equal(log.filter(e=>e.kind==='interrupted').length,0,JSON.stringify(log))
   assert(log.filter(e=>e.kind==='end').length>=2,JSON.stringify(log))
   assert.equal(log.filter(e=>e.kind==='start').length,log.filter(e=>e.kind==='end').length)
   assert(log.some(e=>e.kind==='end'&&e.text.includes('fires it home')),JSON.stringify(log))
   console.log(`PASS ${story}: ${log.filter(e=>e.kind==='end').length} complete spoken updates, zero interruptions at 1.5x with a 4-second voice.`)
  }
  assert.deepEqual(errors,[])
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
