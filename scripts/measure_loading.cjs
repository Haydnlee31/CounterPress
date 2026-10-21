// No request interception: Playwright routing disables the browser cache.
// Run against a built local preview; never submits questions or synthesizes voice.
const {chromium}=require('playwright'),fs=require('node:fs');
(async()=>{
  const base=process.argv[2]||'http://127.0.0.1:8019',label=process.argv[3]||'measurement';
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE});
  const results=[];
  try{
    for(const [name,path,selector] of [
      ['matchday','/?story=last-gasp#matchday','.fan-pitch'],
      ['match-centre','/?match=wyscout-2058017#gi','.gi-watch'],
      ['clubhouse','/#football/player/eb05','.fh-profile-hero'],
    ]){
      const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
      const cdp=await context.newCDPSession(page);
      await cdp.send('Network.enable');
      await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:80,downloadThroughput:1250000,uploadThroughput:625000});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      for(const visit of ['fresh','repeat']){
        const start=Date.now();
        if(visit==='repeat')await page.reload({waitUntil:'domcontentloaded',timeout:120000});
        else await page.goto(base+path,{waitUntil:'domcontentloaded',timeout:120000});
        if(name==='match-centre')await page.getByRole('button',{name:'Watch full match',exact:true}).click({timeout:120000});
        await page.locator(selector).waitFor({timeout:120000});
        const usableMs=Date.now()-start;
        await page.locator(selector).scrollIntoViewIfNeeded();
        await page.evaluate(async selector=>{
          const root=document.querySelector(selector);
          await Promise.all([...root.querySelectorAll('img'),...root.querySelectorAll('image'),...document.querySelectorAll('.cp-wordmark image')].map(async el=>{
            if(el instanceof HTMLImageElement){await el.decode();return}
            const img=new Image();img.src=el.getAttribute('href');await img.decode();
          }));
        },selector);
        const imagesReadyMs=Date.now()-start;
        await page.waitForTimeout(500);
        const resources=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>({path:new URL(r.name).pathname,transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize,duration:Math.round(r.duration)})));
        if(errors.length)throw Error(errors.join('; '));
        results.push({name,visit,usableMs,imagesReadyMs,transferBytes:resources.reduce((s,r)=>s+r.transfer,0),resources});
        fs.mkdirSync(`var/loading/${label}`,{recursive:true});
        await page.locator(selector).screenshot({path:`var/loading/${label}/${name}-${visit}.png`});
      }
      await context.close();
    }
    fs.writeFileSync(`var/loading/${label}/results.json`,JSON.stringify(results,null,2));
    console.log(JSON.stringify(results.map(({resources,...r})=>r),null,2));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
