/* Run alone: another browser audio player can take OS audio focus and pause this one.
 * Actual continuous Azure recordings. Checks the whole recording, not individual name calls. */
const {chromium}=require('playwright'),assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})})
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[]
  page.on('pageerror',e=>errors.push(e.message))
  await page.addInitScript(()=>{
   window.trackLog={plays:0,ends:0,requests:0,markers:[],observed:[],interruptions:0}
   document.addEventListener('click',e=>{if(e.target.closest('.fan-pitch-controls .fan-primary'))window.trackLog.clicked=performance.now()},true)
   const original=window.fetch,AudioNative=window.Audio
   window.fetch=async(...args)=>{
    const response=await original(...args)
    if(String(args[0]).endsWith('/api/voice/highlight')){window.trackLog.requests++;if(response.ok)window.trackLog.markers=(await response.clone().json()).markers}
    return response
   }
   window.Audio=function(...args){
    const audio=new AudioNative(...args),play=audio.play.bind(audio),pause=audio.pause.bind(audio)
    window.trackAudio=audio
    let seen=new Set(),running=false
    audio.play=async()=>{window.trackLog.plays++;await play();running=true
     const tick=()=>{
      if(!running)return
      for(const [i,mark] of window.trackLog.markers.entries())if(!seen.has(i)&&audio.currentTime>=mark.at){
       seen.add(i)
       requestAnimationFrame(()=>{const slider=document.querySelector('[aria-label="Replay position"],[aria-label="回放位置"]');window.trackLog.observed.push({...mark,value:Number(slider?.value)/100,time:audio.currentTime})})
      }
      requestAnimationFrame(tick)
     };requestAnimationFrame(tick)
    }
    audio.pause=()=>{if(running&&!audio.ended&&audio.duration-audio.currentTime>.05)window.trackLog.interruptions++;running=false;return pause()}
    audio.addEventListener('playing',()=>{if(window.trackLog.onset===undefined)window.trackLog.onset=performance.now()-window.trackLog.clicked})
    audio.addEventListener('ended',()=>{window.trackLog.ends++;running=false;window.trackLog.preservesPitch=audio.preservesPitch;window.trackLog.duration=audio.duration})
    return audio
   }
  })
  const base=process.argv[2]||'http://127.0.0.1:8014'
  const stories=(process.env.STORIES||'last-gasp,one-touch,breakaway,level-first,take-lead,level-late').split(',')
  for(const language of (process.env.LANGUAGES||'en,zh-Hans').split(','))for(const [i,story] of stories.entries()){
   await page.goto(`${base}/?story=${story}#matchday`)
   await page.evaluate(language=>localStorage.setItem('counterpress.matchday.preferences.v1',JSON.stringify({language})),language);await page.reload()
   const zh=language==='zh-Hans',listen=page.getByRole('button',{name:zh?'收听':'Listen',exact:true})
   await listen.waitFor();await page.waitForFunction(()=>!document.querySelector('.live-companion button').disabled)
   await listen.click()
   await page.getByText(zh?'解说已准备 · 跟随回放':'Commentary ready · follows playback',{exact:true}).waitFor({timeout:60000})
   await page.getByRole('combobox',{name:zh?'球场回放速度':'Pitch replay speed'}).selectOption(String(process.env.SPEED||[1,1.5,.5][i%3]))
   await page.getByRole('button',{name:zh?'播放集锦':'Play highlight',exact:true}).click()
   await page.waitForFunction(()=>window.trackLog.ends===1,{},{timeout:120000}).catch(async e=>{console.log(await page.evaluate(()=>({log:window.trackLog,at:window.trackAudio?.currentTime,duration:window.trackAudio?.duration,paused:window.trackAudio?.paused,ended:window.trackAudio?.ended})));throw e})
   await page.waitForTimeout(100)
   const log=await page.evaluate(()=>window.trackLog)
   assert.equal(log.plays,1,'Narration was restarted or fragmented')
   assert.equal(log.interruptions,0,'Narration was cut off')
   assert.equal(log.requests,1,'Narration requested again during play')
   assert(log.preservesPitch)
   assert(log.onset<500,`Delayed first voice: ${log.onset}ms`)
   assert.equal(log.observed.length,log.markers.length,'A spoken phrase was skipped')
   for(const mark of log.observed){
    assert(Math.abs(mark.value-mark.position)<.18,`Phrase drift: ${mark.text} ${mark.value} expected ${mark.position}`)
    if(!zh)assert(mark.text.trim().split(/\s+/).length>=2,'Name-only commentary')
   }
   assert(log.duration>10)
   console.log(`PASS ${story} ${language}: ${log.duration.toFixed(2)}s continuous audio; ${log.observed.length} complete phrase markers; one start (${Math.round(log.onset)}ms), natural end, zero cuts, pitch preserved`)
  }
  assert.deepEqual(errors,[])
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
