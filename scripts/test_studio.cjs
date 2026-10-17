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
  await page.getByText('Revoke this approval',{exact:true}).click();
  await page.getByText('Approval revoked',{exact:true}).waitFor();
  assert.equal(await page.getByRole('region',{name:'Approved clean preview'}).count(),0);
  await page.getByText('End Studio session',{exact:true}).click();
  assert.equal(await page.getByText('1. Review the story',{exact:true}).count(),0);
 }
 assert.deepEqual(errors,[]);
 console.log('PASS Studio fixture browser QA: 360/390/760/1365px, evidence table, approve, preview, revoke, session end; no overflow or page errors. Authentication is mocked.');
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
