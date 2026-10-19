/* Actual Azure MP3 + Web Audio playback. No speech or timing mocks. */
const {chromium}=require('playwright'),assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})})
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[]
  page.on('pageerror',e=>errors.push(e.message))
  await page.addInitScript(()=>{
   window.voiceChecks=[];window.voiceRequests=0;window.scheduled=[]
   document.addEventListener('click',e=>{if(e.target.closest('.fan-pitch-controls .fan-primary'))window.playPressed=performance.now()},true)
   const fetchNative=window.fetch,decoded=new WeakMap()
   window.fetch=async(...args)=>{
    if(String(args[0]).endsWith('/api/voice/commentary')){window.voiceRequests++;window.voiceRequest=JSON.parse(args[1].body)}
    return fetchNative(...args)
   }
   const decode=AudioContext.prototype.decodeAudioData,create=AudioContext.prototype.createBufferSource
   AudioContext.prototype.decodeAudioData=async function(...args){const meta=window.voiceRequest,b=await decode.apply(this,args);decoded.set(b,meta);return b}
   // Trimming copies decoded buffers; retain the source metadata for onset checks.
   const createBuffer=AudioContext.prototype.createBuffer
   AudioContext.prototype.createBuffer=function(...args){const b=createBuffer.apply(this,args);decoded.set(b,window.voiceRequest);return b}
   AudioContext.prototype.createBufferSource=function(){
    const context=this,node=create.call(this),start=node.start.bind(node),stop=node.stop.bind(node)
    let cancelled=false
    node.stop=(...args)=>{cancelled=true;return stop(...args)}
    node.start=(when,offset=0)=>{
     const meta=decoded.get(node.buffer),schedule={when,offset,meta,duration:node.buffer.duration,speed:node.playbackRate.value}
     window.scheduled.push(schedule)
     const check=()=>{
      if(cancelled)return
      if(context.currentTime<when){requestAnimationFrame(check);return}
      const slider=document.querySelector('[aria-label="Replay position"], [aria-label="回放位置"]')
      // Wait one frame for the pitch render using the same audio clock.
      requestAnimationFrame(()=>window.voiceChecks.push({...schedule,clock:context.currentTime,value:Number(slider?.value),wall:performance.now()}))
     }
     requestAnimationFrame(check);return start(when,offset)
    }
    return node
   }
  })
  const base=process.argv[2]||'http://127.0.0.1:8012'
  const stories=(process.env.STORIES||'last-gasp,one-touch,breakaway,level-first,take-lead,level-late').split(',')
  for(const language of (process.env.LANGUAGES||'en,zh-Hans').split(','))for(const [storyIndex,story] of stories.entries()){
   await page.goto(`${base}/?story=${story}#matchday`)
   await page.evaluate(language=>{
    const key='counterpress.matchday.preferences.v1'
    localStorage.setItem(key,JSON.stringify({...JSON.parse(localStorage.getItem(key)||'{}'),language}))
   },language)
   await page.reload()
   const zh=language==='zh-Hans'
   const listen=page.getByRole('button',{name:zh?'收听':'Listen',exact:true})
   await listen.waitFor();await page.waitForFunction(zh=>!document.querySelector(`[aria-label="${zh?'随场解说':'Live Companion'}"] button`)?.disabled,zh)
   assert.equal(await page.getByText('Full-match archive',{exact:true}).count(),0)
   await listen.click()
   await page.getByText(zh?'解说已准备 · 跟随回放':'Commentary ready · follows playback',{exact:true}).waitFor({timeout:180000})
   const speed=[1,1.5,.5][storyIndex%3]
   await page.getByRole('combobox',{name:zh?'球场回放速度':'Pitch replay speed'}).selectOption(String(speed))
   const requestCount=await page.evaluate(()=>window.voiceRequests)
   await page.getByRole('button',{name:zh?'播放集锦':'Play highlight',exact:true}).click()
   await page.waitForFunction(()=>window.voiceChecks.length>0)
   const onset=await page.evaluate(()=>window.voiceChecks[0].wall-window.playPressed)
   assert(onset<350,`First voice lag ${onset}ms`)
   await page.getByRole('button',{name:zh?'播放集锦':'Play highlight',exact:true}).waitFor({timeout:90000})
   const checks=await page.evaluate(()=>window.voiceChecks)
   const resultCalls=checks.filter(c=>c.meta.delivery==='highlight-result')
   assert(resultCalls.length>0)
   for(const c of resultCalls){
    const progress=c.value%100
    assert(progress>=57&&progress<70,`${story} reaction out of sync: ${progress}%`)
    assert(c.clock-c.when<.2,`Late audio onset ${c.clock-c.when}`)
   }
   assert.equal(await page.evaluate(()=>window.voiceRequests),requestCount,'Playback made a voice network request')
   assert.equal(await page.locator('.fan-pitch-player').count(),22)
   console.log(`PASS ${story} ${language} ${speed}x: first voice ${Math.round(onset)}ms; ${resultCalls.length} shot reactions at ${resultCalls.map(c=>(c.value%100).toFixed(1)+'%').join(', ')}; zero playback fetches`)
  }
  assert.deepEqual(errors,[])
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
