// Local layout and navigation audit; no AI or speech calls.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const base=process.argv[2]||'http://127.0.0.1:8019';
 const out='var/moment-context-layout';fs.mkdirSync(out,{recursive:true});
 const errors=[],results=[];
 try{
  const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/fan/assistant/ask',r=>r.abort());
  for(const width of [1440,1024,768,390,360]){
   await page.setViewportSize({width,height:1000});
   await page.goto(base+'/?match=wyscout-2058017#gi');
   await page.getByRole('button',{name:'Moments',exact:true}).click();
   const cases=await page.evaluate(async()=>{
    const m=await(await fetch('/api/gi/matches/wyscout-2058017')).json();
    const counts=m.events.map(e=>m.events.filter(x=>x.period===e.period&&x.elapsed_ms>e.elapsed_ms-10000&&x.elapsed_ms<=e.elapsed_ms+10000).length);
    return [m.events.findIndex(e=>e.period===2&&e.elapsed_ms>=115000),0,counts.indexOf(Math.max(...counts))];
   });
   for(const [caseId,index] of cases.entries()){
    await page.getByLabel('Match timeline').fill(String(index));
    const pause=page.locator('.gi-detail').getByRole('button',{name:'Pause',exact:true});if(await pause.count())await pause.click();
    await page.locator('.gi-below').scrollIntoViewIfNeeded();
    const layout=await page.locator('.gi-below').evaluate(root=>{
     const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom,right:r.right}};
     const stats=rect(root.querySelector('.gi-stats')),context=rect(root.querySelector('.gi-context'));
     const cards=[...root.querySelectorAll('.gi-stat-strip button')].map(rect);
     const headings=[...root.querySelectorAll('h2')].map(rect),listRect=rect(root.querySelector('.gi-context ol'));
     const list=root.querySelector('.gi-context ol');
     const clipping=[...root.querySelectorAll('button')].filter(e=>e.scrollWidth>e.clientWidth+1).length;
     return {stats,context,cards,headings,listRect,clipping,scrolling:list.scrollHeight>list.clientHeight+1,selected:root.querySelectorAll('[aria-current=true]').length,overflow:document.documentElement.scrollWidth>innerWidth};
    });
    assert(!layout.overflow&&!layout.clipping,'Clipped content');
    assert.equal(layout.selected,1);assert.equal(layout.cards.length,4);
    if(width>800){
     assert(Math.abs(layout.headings[0].y-layout.headings[1].y)<1,'Headings not parallel');
     assert(Math.abs(layout.cards[0].y-layout.listRect.y)<2,'Lists not parallel');
     const panel=await page.locator('.gi-actions').evaluate(el=>{
      const r=el.getBoundingClientRect(),list=el.querySelector('.gi-action-list').getBoundingClientRect(),more=el.querySelector('.gi-more')?.getBoundingClientRect();
      return {height:r.height,listHeight:list.height,space:r.bottom-(more?.bottom??list.bottom)};
     });
     assert(panel.listHeight>410,'Actions do not use available height');assert(panel.space<3,'Blank space below actions');
    }else assert(layout.context.y>layout.stats.bottom,'Mobile sections overlap');
    if(caseId===0){await page.locator('.gi-below').screenshot({path:`${out}/${width}.png`});await page.locator('.gi-workspace').screenshot({path:`${out}/workspace-${width}.png`});}
    results.push({width,case:caseId,layout:'passed'});
   }
   const before=await page.locator('.gi-actions').boundingBox();
   const oldCount=await page.locator('.gi-action-list li').count();
   await page.locator('.gi-more').click();
   assert.equal(await page.locator('.gi-action-list li').count(),oldCount+40);
   if(width>800){const after=await page.locator('.gi-actions').boundingBox();assert(Math.abs(before.height-after.height)<2,'Loading actions grows panel beyond replay');}
   await page.locator('.gi-action-list li').last().scrollIntoViewIfNeeded();
   const reachable=await page.locator('.gi-action-list').evaluate(el=>Math.abs(el.scrollHeight-el.scrollTop-el.clientHeight)<3);assert(reachable,'Additional actions cannot be reached');
   await page.locator('.gi-stat-strip button').first().click();
   assert.equal(await page.getByRole('group',{name:'Explore actions'}).getByRole('button',{name:'All shots',exact:true}).getAttribute('aria-pressed'),'true');
   await page.getByLabel('Match timeline').fill(String(cases[0]));
   const target=page.locator('.gi-context button:not([aria-current])').first();
   const time=await target.locator('time').innerText();await target.click();
   assert.equal(await page.locator('.gi-context button[aria-current] time').innerText(),time);
   await page.getByRole('button',{name:'Overview',exact:true}).click();assert(await page.locator('.gi-below').isHidden());assert.equal(await page.locator('.gi-discipline').count(),0);
  }
  assert.deepEqual(errors,[]);fs.writeFileSync(`${out}/results.json`,JSON.stringify({results,errors},null,2));
  console.log(`PASS: ${results.length} responsive sparse/dense context checks; statistic filters and event navigation at 5 widths; parallel columns, filled action panel, no overview card tracker, clipping or browser errors.`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
