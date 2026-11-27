// Visual QA of the operations console: node qa_console.mjs <outdir>  (API on :8000 serving dist)
import puppeteer from 'puppeteer-core';
const out = process.argv[2];
const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-gl=swiftshader', '--no-sandbox'], headless: 'new' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (p, sel, text) => p.evaluate((s, t) => { const el = [...document.querySelectorAll(s)].find((x) => x.textContent.includes(t)); if (!el) throw new Error(`no ${s} ${t}`); el.click(); }, sel, text);
for (const [name, w, h] of [['d', 1440, 1000], ['m', 390, 844]]) {
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && errs.push(m.text()));
  await p.setViewport({ width: w, height: h });
  await p.goto('http://localhost:8000/', { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('#ops', { timeout: 60000 });
  await p.evaluate(() => { localStorage.removeItem('of-lang'); document.documentElement.style.scrollBehavior = 'auto'; document.getElementById('ops').scrollIntoView(); });
  await sleep(1500);
  const shot = async (tag) => { const el = await p.$('#ops'); await el.screenshot({ path: `${out}/${name}-${tag}.png` }); };
  await shot('scenarios-en');
  if (name === 'd') {
    await click(p, '#ops .chip', 'Agent failure');
    await sleep(300);
    await click(p, '#ops button.cue', 'Run live');
    await p.waitForFunction(() => document.querySelector('#ops').textContent.includes('Newly executed'), { timeout: 60000 });
    await shot('s6-live');
    for (const [t, tag] of [['Agents', 'agents'], ['Policy profiles', 'policies'], ['Standards', 'standards'], ['Validation', 'validation']]) {
      await click(p, '#ops .tabs .chip', t); await sleep(500); await shot(tag);
    }
    await click(p, '#ops .tabs .chip', 'Scenarios');
  }
  await click(p, '#ops .chip', 'العربية'); await sleep(500);
  await shot('scenarios-ar');
  const dir = await p.evaluate(() => document.getElementById('ops').getAttribute('dir'));
  if (name === 'd') {
    await p.type('#ops .askform input', 'நெரிசல் இந்தியா 15 வாட்');
    await click(p, '#ops .askform button', '');
    await p.waitForFunction(() => document.querySelector('#ops .askform').parentElement.textContent.includes('S3_congestion'), { timeout: 60000 });
    await sleep(500);
    const el = await p.$('#ops .askform'); const box = await el.evaluateHandle((x) => x.parentElement);
    await box.asElement().screenshot({ path: `${out}/${name}-interpret.png` });
  }
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(name, 'dir', dir, 'overflowX', overflow, 'errors', errs);
  await p.close();
}
await b.close();
