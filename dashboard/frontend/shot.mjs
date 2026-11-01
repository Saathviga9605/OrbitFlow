// Visual QA: node shot.mjs <outdir>  (serve dist on :4173 first)
import puppeteer from 'puppeteer-core';
const out = process.argv[2];
const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--no-sandbox'], headless: 'new' });
for (const [name, w, h] of [['d', 1440, 900], ['m', 390, 844]]) {
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && errs.push(m.text()));
  await p.setViewport({ width: w, height: h });
  await p.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded' }); await p.waitForSelector('#ledger', { timeout: 60000 });
  await new Promise((r) => setTimeout(r, 2500));
  await p.screenshot({ path: `${out}/${name}-hero.png` });
  for (const id of ['chase', 'foresee', 'loop', 'mission', 'evidence', 'lab', 'knowledge', 'ledger']) {
    await p.evaluate((i) => { document.documentElement.style.scrollBehavior = 'auto'; document.getElementById(i).scrollIntoView(); }, id);
    if (id === 'mission') await p.evaluate(() => [...document.querySelectorAll('#mission .chip')].find((x) => x.textContent.startsWith('Cap arrives')).click());
    await new Promise((r) => setTimeout(r, 500));
    const el = await p.$(`#${id}`);
    await el.screenshot({ path: `${out}/${name}-${id}.png` });
  }
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(name, 'overflowX', overflow, 'errors', errs);
  await p.close();
}
await b.close();
