// Local-only layout/interaction audit: no model or speech requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const base=process.argv[2]||'http://127.0.0.1:8019',out='var/replay-layout';fs.mkdirSync(out,{recursive:true});
 const results=[],errors=[];
 try{
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/fan/assistant/ask',r=>r.abort());
 async function bounds(selector,min=16){
  const problems=await page.locator(selector).evaluate((root,min)=>{
   const r=root.getBoundingClientRect(),errors=[];
   for(const el of root.querySelectorAll('button,select,summary,input[type="range"],.gi-auto-toggle,.gi-replay-caption,.gi-watch-note')){
    if(!el.checkVisibility())continue;const b=el.getBoundingClientRect();
    if(b.left<r.left+min-1||b.right>r.right-min+1)errors.push(`${el.getAttribute('aria-label')||el.textContent?.trim()}: ${Math.round(b.left-r.left)}/${Math.round(r.right-b.right)}`);
   }
   return errors;
  },min);assert.deepEqual(problems,[],`${selector} content too close to widget edge`);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'page overflow');
 }
 for(const width of [1440,1024,800,390,360]){
  await page.setViewportSize({width,height:1000});await page.goto(base+'/?match=wyscout-2058017#gi');
  await page.getByRole('button',{name:'Moments',exact:true}).click();
  const goalIndex=await page.evaluate(async()=>{const m=await(await fetch('/api/gi/matches/wyscout-2058017')).json();return m.events.findIndex(e=>e.goal_for!==null&&e.period===2&&e.elapsed_ms>780000)});
  await page.getByLabel('Match timeline').fill(String(goalIndex));await page.locator('.gi-detail .gi-replay-dock').waitFor();
  const pause=page.locator('.gi-detail').getByRole('button',{name:'Pause',exact:true});if(await pause.count())await pause.click();
  await bounds('.gi-detail');
  const pitch=await page.locator('.gi-detail .gi-pitch').boundingBox(),tools=await page.locator('.gi-detail .gi-replay-tools').boundingBox();assert(tools.y>pitch.y+pitch.height,'Settings compete with pitch');
  await page.locator('.gi-detail').screenshot({path:`${out}/moments-${width}.png`});
  await page.locator('.gi-detail .pitch-display-settings summary').click();await page.getByLabel('Pitch player display').selectOption('initials');
  assert.equal(await page.locator('.gi-detail image').count(),0);await page.getByLabel('Pitch player display').selectOption('faces');
  await bounds('.gi-detail');await page.locator('.gi-detail .pitch-display-settings summary').click();
  const cards=page.locator('.gi-card-disclosure');if(await cards.count()){await cards.locator('summary').click();await bounds('.gi-detail');await cards.locator('summary').click()}
  const auto=page.getByLabel('Auto-play next sequence');await auto.check();assert(await auto.isChecked());await auto.uncheck();
  await page.getByRole('button',{name:'Watch full match',exact:true}).click();await page.getByLabel('Full match progress').fill('1');await bounds('.gi-watch');
  await page.locator('.gi-watch').screenshot({path:`${out}/watch-${width}.png`});
  await page.goto(base+'/?story=last-gasp#matchday');await page.locator('.fan-pitch .pitch-display-settings summary').click();await page.getByLabel('Pitch player display').selectOption('faces');await bounds('.fan-pitch',12);
  await page.locator('.fan-pitch .pitch-display-settings summary').click();await page.locator('.fan-pitch').evaluate(async root=>{await Promise.all([...root.querySelectorAll('image')].map(el=>new Promise(resolve=>{const i=new Image();i.onload=i.onerror=resolve;i.src=el.getAttribute('href')})))});await page.locator('.fan-pitch').screenshot({path:`${out}/matchday-${width}.png`});
  await page.goto(base+'/#football/following');await page.locator('button.fh-highlight-card').first().click();await page.getByLabel('Highlight progress').waitFor();
  await page.locator('.fh-replay-dialog .pitch-display-settings summary').click();await page.getByLabel('Pitch player display').selectOption('initials');await page.getByLabel('Highlight playback speed').selectOption('2');
  await bounds('.fh-replay-dialog',12);await page.locator('.fh-replay-dialog .pitch-display-settings summary').click();await page.locator('.fh-replay-dialog').screenshot({path:`${out}/clubhouse-${width}.png`});await page.getByRole('button',{name:'Close highlight'}).click();
  results.push({width,controls_inset:true,display:true,auto_toggle:true,full_match:true,matchday:true,clubhouse:true});
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(`${out}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify({status:'passed',results,page_errors:errors},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
