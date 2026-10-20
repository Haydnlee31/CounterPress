// Check the rendered local pages for clipping and the reported mascot collision.
// This does not send questions, synthesize audio or sign into Studio.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs')
;(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
 const base=process.argv[2]||'http://127.0.0.1:8017',results=[],errors=[]
 fs.mkdirSync('var/spacing-validation',{recursive:true})
 try{
  for(const [name,url,ready] of [
   ['footie','#assistant','.ft-start'],['watch','?story=last-gasp#matchday','.fan-pitch'],
   ['breakdown','?story=last-gasp#matchday/breakdown','.explore-insights'],['centre','?match=wyscout-2058017#gi','.gi-overview'],
   ['clubhouse','#football','.fh-player-card'],['profile','#football/player/rh09','.fh-tiles'],['club','#football/club/redhaven','.fh-tiles'],
   ['following','#football/following','.fh-welcome'],['compare','#football/compare','.fh-compare-selectors'],
   ['tools','#tools','.tools-grid'],['studio','#studio','.studio'],['evidence','#analysis','.playback'],['fullmatch','#live','.live-controls']]){
   const page=await browser.newPage({viewport:{width:1440,height:1000}})
   page.on('pageerror',e=>errors.push(name+': '+e.message))
   await page.route('**/api/fan/assistant/ask',r=>r.abort())
   await page.route('**/api/voice/**',r=>r.fulfill({json:{azure:false}}))
   await page.goto(base+'/'+url);await page.locator(ready).first().waitFor()
   for(const width of [1440,768,390,360]){
    await page.setViewportSize({width,height:1000})
    const layout=await page.evaluate(()=>{
     const clipped=[]
     for(const el of document.querySelectorAll('button,select,input,textarea')){
      const box=el.getBoundingClientRect();if(!box.width||!box.height||getComputedStyle(el).visibility==='hidden'||el.closest('[hidden]')||el.matches('[type=checkbox],[type=radio]'))continue
      for(let p=el.parentElement;p&&p!==document.body;p=p.parentElement){
       const style=getComputedStyle(p),rect=p.getBoundingClientRect()
       // Scroll containers are deliberate (timelines, histories, comparison tables).
       if([style.overflowX,style.overflowY].some(v=>v==='auto'||v==='scroll'))break
       if(['hidden','clip'].includes(style.overflowX)&&(box.left<rect.left-2||box.right>rect.right+2))clipped.push({control:el.getAttribute('aria-label')||el.textContent?.trim().slice(0,70),container:p.className})
      }
     }
     return {overflow:document.documentElement.scrollWidth>innerWidth,clipped,headers:[...document.querySelectorAll('.cp-shell')].filter(e=>e.getBoundingClientRect().height).length}
    })
    assert.equal(layout.overflow,false,`${name} page overflow at ${width}`)
    assert.deepEqual(layout.clipped,[],`${name} clipped controls at ${width}`)
    assert.equal(layout.headers,1,`${name} duplicate header at ${width}`)
    if(name==='footie'){
     const gap=await page.evaluate(()=>document.querySelector('.ft-start h2').getBoundingClientRect().top-document.querySelector('.ft-welcome-mascot .footie-mascot').getBoundingClientRect().bottom)
     assert(gap>=20,`Footie artwork/title gap ${gap}px at ${width}`)
    }
    if(name==='watch'){
     const gap=await page.evaluate(()=>document.querySelector('.companion-current').getBoundingClientRect().top-document.querySelector('.companion-heading').getBoundingClientRect().bottom)
     assert(gap>=12,'Commentary copy touches its controls')
    }
    if(name==='profile'||name==='club'){
     const boxes=await page.locator('.fh-profile-actions > *').evaluateAll(elements=>elements.map(e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,right:r.right,bottom:r.bottom}}))
     for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++)assert(!(boxes[i].x<boxes[j].right&&boxes[j].x<boxes[i].right&&boxes[i].y<boxes[j].bottom&&boxes[j].y<boxes[i].bottom),'Overlapping profile actions')
    }
    if(name==='breakdown'){
     const gap=await page.evaluate(()=>document.querySelector('.explore-explanation').getBoundingClientRect().top-document.querySelector('.explore-phases').getBoundingClientRect().bottom)
     assert(gap>=16,'Breakdown explanation touches phase controls')
    }
    await page.screenshot({path:`var/spacing-validation/${name}-${width}.png`})
   }
   results.push(name);console.log('PASS spacing: '+name+' (1440, 768, 390, 360px)')
   await page.close()
  }
  assert.deepEqual(errors,[])
  fs.writeFileSync('var/spacing-validation/results.json',JSON.stringify({pages:results,widths:[1440,768,390,360],errors},null,2))
  console.log('PASS all 13 page layouts: no horizontal overflow, clipped controls or duplicate headers; mascot separation and profile actions verified. No AI calls.')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
