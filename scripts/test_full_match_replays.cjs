const {chromium}=require('playwright'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const base=process.argv[2]||'http://127.0.0.1:8019';fs.mkdirSync('var/fan-feedback',{recursive:true});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),out=[];
 for(const [match,expected] of [['wyscout-2058017','4 – 2'],['wyscout-2058007','3 – 2'],['synthetic-32fe41c5d304ce68d7d9','2 – 2']]){
  await page.goto(`${base}/?match=${match}#gi`);await page.getByRole('button',{name:'Watch full match',exact:true}).click();
  await page.getByLabel('Full match progress').fill('1');const score=await page.locator('.gi-watch-score strong').innerText();if(score!==expected)throw Error('Wrong score '+match+' '+score);
  const box=await page.locator('.gi-watch .gi-pitch').boundingBox();if(box.height<=box.width)throw Error('Mobile pitch must be portrait');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Match overflow');
  out.push({match,score,mobile_pitch:'portrait'});
 }
 await page.goto(base+'/#football/standings');await page.getByRole('table').waitFor();
 const points=page.locator('.league-table thead th').last();if(!await points.isVisible())throw Error('Points hidden');
 const box=await points.boundingBox();if(box.x+box.width>390)throw Error('Points offscreen');
 await page.getByRole('button',{name:'Show all columns'}).click();if(!await page.locator('.league-table th').filter({hasText:'GF'}).isVisible())throw Error('Full table unavailable');
 await page.getByRole('button',{name:'Compact table'}).click();
 await page.screenshot({path:'var/fan-feedback/standings-mobile-final.png',fullPage:true});
 fs.writeFileSync('var/fan-feedback/full-matches.json',JSON.stringify(out,null,2));console.log(JSON.stringify({status:'passed',matches:out,mobile_points_visible:true,all_columns_toggle:true},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
