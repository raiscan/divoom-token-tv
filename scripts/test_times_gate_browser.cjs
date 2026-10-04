/* Five-screen gallery and appearance checks against a local fixture or live dashboard. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_PACKAGE || 'playwright');
const url = process.env.TOKEN_TV_TEST_URL || 'http://127.0.0.1:18789';
const out = process.env.TOKEN_TV_SCREENSHOTS || '.runtime/times-gate-browser';
fs.mkdirSync(out, {recursive:true});
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors = []; let posts = 0;
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {if (r.method() === 'POST') posts++});
  await page.goto(url);
  await page.waitForSelector('.gallery[data-device=times-gate] .theme-card[data-id=gameboy]');
  const styles = (await (await page.request.get(url+'/display')).json()).styles;
  assert.equal(styles.length, 7); assert(styles.includes('gameboy'));
  for (const thumb of await page.locator('.theme-thumb').all()) await thumb.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => [...document.querySelectorAll('.theme-thumb')].every(i => i.complete && i.naturalWidth === 640 && i.naturalHeight === 128));
  const dimensions = await page.locator('.theme-thumb').evaluateAll(nodes => nodes.map(i => {const r=i.getBoundingClientRect();return [r.width,r.height]}));
  assert(dimensions.every(([w,h]) => w >= 600 && Math.abs(w/h-5)<.01), 'desktop thumbnails must show readable five-screen strips');
  await page.screenshot({path:`${out}/gallery-desktop.png`,fullPage:true});
  for (const style of styles) {
   await page.locator(`.theme-card[data-id=${style}] button`).click();
   await page.waitForFunction(style => {const i=document.querySelector('#frame');return i.complete && i.naturalWidth===640 && i.naturalHeight===128 && i.currentSrc.includes('style='+style)}, style);
   assert.equal(await page.locator('#clock-style').inputValue(),style);
   assert.equal(await page.locator('#frame').evaluate(i=>{const r=i.getBoundingClientRect();return Math.abs(r.width/r.height-5)<.01}),true);
  }
  assert.equal(posts,0,'gallery previews must not change the physical clock');
  await page.screenshot({path:`${out}/gameboy-preview.png`,fullPage:true});
  for (const width of [320,375,768,1024,1440]) {
   await page.setViewportSize({width,height:1100});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow at ${width}`);
   assert.equal(await page.locator('.theme-thumb').first().evaluate(i=>{const r=i.getBoundingClientRect();return Math.abs(r.width/r.height-5)<.01}),true);
  }
  // A fixture accepts a real apply; live checks intercept it to leave the user's choice intact.
  await page.route('**/display/style', r => {assert.deepEqual(r.request().postDataJSON(),{style:'gameboy'});return r.fulfill({json:{style:'gameboy',applied_style:'gameboy',status:'ok',styles,device_type:'times-gate'}})});
  await page.locator('#apply').click();
  await page.waitForFunction(()=>document.querySelector('#display-state').textContent==='Image sent · Game Boy');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(`${out}/result.json`,JSON.stringify({styles,widths:[320,375,768,1024,1440],previewDoesNotApply:true,pageErrors:errors,passed:true},null,2));
  console.log('PASS: seven native appearances, wide five-screen gallery, five widths, preview/apply separation, no browser errors.');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
