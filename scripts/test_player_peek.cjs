const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const base=process.argv[2]||'http://127.0.0.1:8019',out='var/player-peek';fs.mkdirSync(out,{recursive:true});const errors=[],results=[];
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/fan/assistant/ask',r=>r.abort());
 const records=(await(await page.request.get(base+'/api/data/players?featured=true&limit=100')).json()).items;
 async function verify(marker){
  const id=await marker.getAttribute('data-player-peek'),record=records.find(p=>p.player_id===id);assert(record);
  const card=page.getByRole('tooltip');await card.waitFor();await page.waitForFunction(name=>document.querySelector('.player-peek')?.textContent.includes(name),record.name);
  assert((await card.innerText()).includes('#'+record.number));assert((await card.innerText()).includes({GK:'Goalkeeper',DF:'Defender',MF:'Midfielder',FW:'Forward'}[record.role]));
  const b=await card.boundingBox(),v=page.viewportSize();assert(b.x>=11&&b.y>=11&&b.x+b.width<=v.width-11&&b.y+b.height<=v.height-11,'Card crossed viewport edge');return card;
 }
 for(const mode of ['matchday','moments','watch','clubhouse']){
  if(mode==='clubhouse'){await page.goto(base+'/#football/following');await page.locator('button.fh-highlight-card').first().click();await page.getByLabel('Highlight progress').waitFor();const pause=page.locator('.fh-replay-controls button');if((await pause.innerText()).includes('Pause'))await pause.click()}
  else if(mode==='matchday')await page.goto(base+'/?story=last-gasp#matchday');
  else{await page.goto(base+'/?match=wyscout-2058017#gi');await page.getByRole('button',{name:mode==='watch'?'Watch full match':'Moments',exact:true}).click();const pause=page.getByRole('button',{name:'Pause',exact:true});if(await pause.count())await pause.click()}
  const marker=page.locator('[data-player-peek]').first();await marker.waitFor();await marker.scrollIntoViewIfNeeded();await marker.hover();let card=await verify(marker);
  await page.screenshot({path:`${out}/${mode}.png`});
  await card.hover();await page.waitForTimeout(180);assert(await card.isVisible(),'Cannot enter tooltip');
  await page.keyboard.press('Escape');await page.getByRole('tooltip').waitFor({state:'hidden'});
  await marker.focus();await verify(marker);await page.keyboard.press('Escape');
  // Switch to initials without changing identity, then inspect again.
  await page.locator('.pitch-display-settings summary').filter({visible:true}).first().click();await page.getByLabel('Pitch player display').selectOption('initials');await marker.scrollIntoViewIfNeeded();await marker.hover();await verify(marker);await page.keyboard.press('Escape');
  const beforeFocus=mode==='clubhouse'?await page.getByLabel('Highlight player focus').inputValue():null;
  await marker.click();assert.equal(await marker.getAttribute('role'),'group');assert.equal(await marker.getAttribute('aria-pressed'),null);
  if(mode==='clubhouse')assert.equal(await page.getByLabel('Highlight player focus').inputValue(),beforeFocus,'Click changed player focus');
  const playback=page.locator(mode==='matchday'?'.fan-pitch-controls .fan-primary':mode==='clubhouse'?'.fh-replay-controls button':'.gi-playback button');
  const speedLabel=mode==='matchday'?'Pitch replay speed':mode==='clubhouse'?'Highlight playback speed':'Sequence playback speed';await page.getByLabel(speedLabel).selectOption('0.5');
  await playback.click();const moving=marker;const point=await moving.boundingBox();await page.mouse.move(point.x+point.width/2,point.y+point.height/2);await verify(moving);
  assert((await playback.innerText()).includes('Pause'),mode+': Hover interrupted playback');
  await page.mouse.down();await page.mouse.up();assert((await playback.innerText()).includes('Pause'),'Click interrupted playback');assert.equal(await moving.evaluate(e=>getComputedStyle(e).outlineStyle),'none');
  await playback.click();if(await page.getByRole('tooltip').count())await page.keyboard.press('Escape');
  if(mode==='clubhouse'){assert(await page.locator('dialog[open]').isVisible(),'Escape on the tooltip closed the replay dialog');await page.getByRole('button',{name:'Close highlight'}).click()}
  results.push({mode,hover:true,keyboard:true,initials:true,metadata:true,edge_clamp:true,live_hover:true,click_inert:true});
 }
 const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});mobile.on('pageerror',e=>errors.push(e.message));await mobile.goto(base+'/?match=wyscout-2058017#gi');await mobile.getByRole('button',{name:'Watch full match',exact:true}).click();
 const marker=mobile.locator('[data-player-peek="eb01"]');await marker.tap();await mobile.getByRole('tooltip').waitFor();await mobile.getByRole('tooltip').getByText('#1',{exact:false}).waitFor();
 const b=await mobile.getByRole('tooltip').boundingBox();assert(b.x>=11&&b.x+b.width<=379&&b.y>=11&&b.y+b.height<=833);await mobile.screenshot({path:`${out}/mobile.png`});
 await mobile.locator('.gi-watch h2').tap();await mobile.getByRole('tooltip').waitFor({state:'hidden'});results.push({mode:'mobile',touch:true,outside_dismiss:true});await mobile.close();
 assert.deepEqual(errors,[]);fs.writeFileSync(`${out}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify({status:'passed',results,page_errors:errors},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
