const {chromium}=require('playwright');const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],results=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.argv[2]||'http://127.0.0.1:8019';fs.mkdirSync('var/fan-feedback',{recursive:true});
 try{
 await page.goto(base+'/?match=wyscout-2058017#gi');await page.getByRole('heading',{name:'Bookings & send-offs'}).waitFor();
 if(await page.locator('.gi-bookings button').count()!==3)throw Error('Expected three recorded bookings');
 await page.screenshot({path:'var/fan-feedback/overview-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Moments',exact:true}).click();
 await page.locator('.gi-detail image').first().waitFor();
 const faces=await page.locator('.gi-detail image').count();if(faces<18)throw Error('Portraits missing');
 await page.getByLabel('Sequence playback speed').selectOption('2');await page.getByLabel('Auto-play next sequence').check();
 const heading=await page.locator('.gi-detail-heading').innerText();
 // Restart this short initial sequence if it finished while the page loaded.
 const replay=page.getByRole('button',{name:'Replay sequence',exact:true});if(await replay.count())await replay.click();
 await page.waitForFunction(before=>document.querySelector('.gi-detail-heading')?.innerText!==before,heading,{timeout:30000});
 if(await page.getByLabel('Sequence playback speed').inputValue()!=='2')throw Error('Speed was reset on auto-next');
 await page.getByLabel('Auto-play next sequence').uncheck();
 await page.screenshot({path:'var/fan-feedback/moments-desktop.png',fullPage:false});
 await page.getByRole('button',{name:'Watch full match',exact:true}).click();
 await page.getByRole('button',{name:'Play match',exact:true}).waitFor();
 await page.getByRole('button',{name:'Play match',exact:true}).click();
 await page.waitForFunction(()=>Number(document.querySelector('[aria-label="Full match progress"]')?.value)>0);
 await page.getByRole('button',{name:'Pause',exact:true}).click();
 await page.getByLabel('Full match progress').fill('1');
 await page.getByRole('button',{name:'Replay match',exact:true}).waitFor();
 const score=await page.locator('.gi-watch-score strong').innerText();if(score!=='4 – 2')throw Error('Final score mismatch '+score);
 await page.screenshot({path:'var/fan-feedback/watch-desktop.png',fullPage:false});results.push({match:'wyscout-2058017',faces,auto_next:true,speed_persisted:true,full_match_score:score});
 await page.getByRole('link',{name:'Season standings'}).click().catch(()=>page.goto(base+'/#football/standings'));
 await page.getByRole('table').waitFor();const rows=await page.locator('.league-table tbody tr').count();if(rows!==12)throw Error('League clubs '+rows);
 await page.screenshot({path:'var/fan-feedback/standings-desktop.png',fullPage:true});
 await page.getByLabel('Standings season').selectOption('2025-26');await page.locator('caption').filter({hasText:'2025-26'}).waitFor();
 results.push({standings_clubs:rows,season_switch:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'var/fan-feedback/standings-mobile.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Standings page overflows');
 await page.goto(base+'/?match=wyscout-2058017#gi');await page.getByRole('button',{name:'Watch full match',exact:true}).click();await page.locator('.gi-watch image').first().waitFor();
 await page.locator('.gi-watch').scrollIntoViewIfNeeded();await page.screenshot({path:'var/fan-feedback/watch-mobile.png',fullPage:false});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Watch page overflows');
 await page.goto(base+'/?story=last-gasp#matchday');await page.locator('.fan-pitch .pitch-display-settings summary').click();await page.getByLabel('Pitch player display').first().waitFor();
 await page.getByLabel('Pitch replay speed').selectOption('2');await page.getByLabel('Pitch player display').selectOption('initials');
 if(await page.locator('.fan-pitch-player image').count())throw Error('Initials mode did not apply');
 await page.getByLabel('Pitch player display').selectOption('faces');await page.locator('.fan-pitch-player image').first().waitFor();
 await page.locator('.fan-pitch').scrollIntoViewIfNeeded();await page.screenshot({path:'var/fan-feedback/matchday-mobile.png',fullPage:false});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Matchday page overflows');
 if(errors.length)throw Error(JSON.stringify(errors));console.log(JSON.stringify({status:'passed',results,page_errors:errors},null,2));fs.writeFileSync('var/fan-feedback/results.json',JSON.stringify({status:'passed',results,page_errors:errors},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
