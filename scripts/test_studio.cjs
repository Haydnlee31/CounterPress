const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({...(process.env.CHROME_EXECUTABLE ? {executablePath:process.env.CHROME_EXECUTABLE} : {}),headless:true});
 try {
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const width of [360,390,760,1365]){
  await page.setViewportSize({width,height:1000});await page.goto((process.argv[2] || 'http://127.0.0.1:5173') + '/var/studio-qa.html');
  await page.getByText('Sign in with Microsoft',{exact:true}).click();
  await page.getByText('Needs your review',{exact:true}).waitFor();
  assert.equal(await page.getByText('Download approved snapshot',{exact:true}).isDisabled(),true);
  await page.getByText('Evidence reference · revision 1').first().click();
  await page.getByRole('table').first().waitFor();
  assert.equal(await page.locator('.studio-events td').first().evaluate(e=>getComputedStyle(e).color),'rgb(23, 61, 52)');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow at ${width}`);
  if(width===1365)await page.screenshot({path:'var/studio-desktop.png',fullPage:true});
  if(width===390)await page.screenshot({path:'var/studio-mobile.png',fullPage:true});
  await page.getByText('I reviewed this version · Approve',{exact:true}).click();
  await page.getByText('Approved for this snapshot',{exact:true}).waitFor();
  await page.getByText('Open clean preview',{exact:true}).click();
  await page.getByRole('region',{name:'Approved clean preview'}).waitFor();
  await page.getByText('Preview broadcast format',{exact:true}).click();
  const broadcast=page.getByRole('region',{name:'Approved broadcast preview'});
  await broadcast.waitFor();
  assert.equal(await broadcast.getByText('A comparison of recorded recoveries. It does not establish whether pressure was effective.',{exact:true}).count(),1);
  await page.getByRole('combobox',{name:'Output format',exact:true}).selectOption('lower-third');
  assert.equal(await broadcast.getByRole('heading',{name:'Lower-third preview',exact:true}).count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`broadcast overflow at ${width}`);
  if(width===1365)await page.screenshot({path:'var/studio-broadcast-desktop.png',fullPage:true});
  if(width===390)await page.screenshot({path:'var/studio-broadcast-mobile.png',fullPage:true});
  const choices=await page.getByRole('combobox',{name:'Broadcast story',exact:true}).locator('option').allTextContents();
  assert.equal(choices.length,3);
  await page.getByRole('combobox',{name:'Broadcast story',exact:true}).selectOption({index:1});
  assert.equal(await broadcast.getByText('Sustained possessions with less than 15 m of observed forward gain. This does not measure passing quality or tactical value.',{exact:true}).count(),1);
  await page.getByText('Revoke this approval',{exact:true}).click();
  await page.getByText('Approval revoked',{exact:true}).waitFor();
  assert.equal(await page.getByRole('region',{name:'Approved clean preview'}).count(),0);
  assert.equal(await broadcast.count(),0);
  assert.equal(await page.getByText('Download broadcast format',{exact:true}).isDisabled(),true);
  await page.getByRole('combobox',{name:'Story language',exact:true}).selectOption('zh-Hans');
  await page.getByText('Needs your review',{exact:true}).waitFor();
  await page.getByText('I reviewed this version · Approve',{exact:true}).click();
  await page.getByText('Approved for this snapshot',{exact:true}).waitFor();
  await page.getByText('Preview broadcast format',{exact:true}).click();
  await page.getByRole('combobox',{name:'Output format',exact:true}).selectOption('lower-third');
  assert.equal(await broadcast.locator('article[lang="zh-Hans"]').count(),1);
  await page.evaluate(()=>document.documentElement.style.fontSize='200%');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`Chinese/text-size overflow at ${width}`);
  await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.getByText('End Studio session',{exact:true}).click();
  assert.equal(await page.getByText('1. Review the story',{exact:true}).count(),0);
 }
 assert.deepEqual(errors,[]);
 console.log('PASS Studio fixture browser QA: 360/390/760/1365px, evidence table, approve, clean/cue/lower-third previews, story selection, revoke, Chinese/200% text, session end; no overflow or page errors. Authentication is mocked.');
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
