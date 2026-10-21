// Browser audit of realistic playback, cut boundaries, source lineups and controls.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const r=require('../var/replay-review/replay-audit.cjs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const base=process.argv[2]||'http://127.0.0.1:8019',out='var/replay-motion-browser';fs.mkdirSync(out,{recursive:true});
 const errors=[],results=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/fan/assistant/ask',r=>r.abort());
  for(const id of ['wyscout-2058017','wyscout-2058007','synthetic-32fe41c5d304ce68d7d9']){
   await page.goto(`${base}/?match=${id}#gi`);await page.getByRole('button',{name:'Watch full match',exact:true}).click();
   const match=await page.evaluate(async id=>(await fetch('/api/gi/matches/'+id)).json(),id);
   const t=r.playTimeline(r.positionedActions(match.events,4418),match.players,4418);
   const progress=page.getByLabel('Full match progress'),root=page.locator('.gi-watch');
   // Native range values may normalize decimal strings; dispatch the same input events as dragging.
   const seek=value=>progress.evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},value);
   await page.getByLabel('Sequence playback speed').selectOption('1');
   const cases=[t.groups[0],t.groups.find(g=>g.actions.some(a=>a.event.detail==='Air duel'))||t.groups[1],t.groups.find(g=>g.actions.some(a=>a.event.goal_for!==null)),t.groups.find(g=>g.actions.some(a=>a.event.kind==='Carry'||a.event.detail==='Acceleration'))].filter(Boolean);
   for(const [ci,g] of cases.entries()){
    await seek((g.at/t.duration).toFixed(6));await root.getByRole('button',{name:'Play match',exact:true}).click();
    const dir=`${out}/${id}-${ci}`;fs.mkdirSync(dir,{recursive:true});const start=Date.now();
    for(let n=0;n<12;n++){
     await root.locator('.gi-pitch').screenshot({path:`${dir}/${String(n).padStart(2,'0')}.png`});
     await page.waitForTimeout(Math.max(0,start+(n+1)*400-Date.now()));
    }
    await root.getByRole('button',{name:'Pause',exact:true}).click();
    const p=await progress.getAttribute('value');await page.waitForTimeout(150);assert.equal(await progress.getAttribute('value'),p);
    results.push({id,case:ci,event:g.actions.at(-1).event.event_id,playPause:true});
   }
   // Exact substitutions: the outgoing player never reappears; keeper stays.
   for(const incoming of match.players.filter(p=>p.entered_at)){
    const first=t.groups.find(g=>r.sceneRoster(match.players,[],g.actions.at(-1).event).some(p=>p.player_id===incoming.player_id));
    for(const at of [first.at+300,Math.min(t.duration-1,first.at+12000)]){
     await seek((at/t.duration).toFixed(6));
     const frame=t.groups.find(g=>at>=g.at&&at<g.at+g.duration),expected=r.sceneRoster(match.players,[],frame.actions.at(-1).event);
     const rendered=await root.locator('.gi-replay-player').count();assert.equal(rendered,expected.length);
     assert.equal(await root.locator('[aria-label="Theo Ashford"]').count(),1);assert.equal(await root.locator('[aria-label="Arthur Wells"]').count(),1);
    }
   }
   await seek('1');assert.equal(await root.locator('.gi-watch-score strong').innerText(),match.teams.map(t=>t.score).join(' – '));
   await page.setViewportSize({width:390,height:844});await seek('.2');await root.screenshot({path:`${out}/${id}-mobile.png`});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.setViewportSize({width:1440,height:1000});
  }
  // Longer uninterrupted observation at 1x on the archive used for the original review.
  await page.goto(`${base}/?match=wyscout-2058017#gi`);await page.getByRole('button',{name:'Watch full match',exact:true}).click();
  await page.getByLabel('Sequence playback speed').selectOption('1');await page.locator('.gi-watch').getByRole('button',{name:'Play match',exact:true}).click();
  for(let n=0;n<45;n++){await page.locator('.gi-watch .gi-pitch').screenshot({path:`${out}/continuous-${String(n).padStart(2,'0')}.png`});await page.waitForTimeout(2000);if(n%15===0)console.log('Continuous playback sample',n);}
  assert.deepEqual(errors,[]);fs.writeFileSync(`${out}/results.json`,JSON.stringify({results,errors},null,2));console.log('PASS: 12 live motion scenarios across 3 matches, recorded substitutions, final scores, mobile bounds, and 90+ seconds uninterrupted 1x playback.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
