// Visual QA per language: node qa_lang.mjs <outdir>   (preview on :4173)
import puppeteer from 'puppeteer-core';
const out = process.argv[2];
const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-gl=swiftshader', '--enable-webgl', '--no-sandbox'], headless: 'new' });
for (const lang of ['ar', 'hi', 'ta']) for (const [name, w, h] of [['d', 1440, 900], ['m', 390, 844]]) {
  const p = await b.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await p.setViewport({ width: w, height: h });
  await p.evaluateOnNewDocument((l) => localStorage.setItem('of-lang', l), lang);
  await p.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded' }); await p.waitForSelector('#ledger', { timeout: 60000 });
  await new Promise((r) => setTimeout(r, 2500));
  await p.screenshot({ path: `${out}/${lang}-${name}-hero.png` });
  for (const id of name === 'd' ? ['loop', 'mission', 'evidence', 'game', 'ops'] : ['loop']) {
    await p.evaluate((i) => { document.documentElement.style.scrollBehavior = 'auto'; document.getElementById(i).scrollIntoView(); document.querySelectorAll('.reveal').forEach((e) => e.classList.add('in')); }, id);
    await new Promise((r) => setTimeout(r, 1200));
    await (await p.$(`#${id}`)).screenshot({ path: `${out}/${lang}-${name}-${id}.png` });
  }
  const info = await p.evaluate(() => ({ dir: document.documentElement.dir, lang: document.documentElement.lang, overflow: document.documentElement.scrollWidth - window.innerWidth,
    untranslated: [...document.querySelectorAll('h1,h2,h4,.kicker,.lede,button,.navlinks a,th')].map((e) => e.textContent.trim()).filter((t) => /^[A-Z][a-z]+( [a-z]+){2,}/.test(t)).slice(0, 12) }));
  console.log(lang, name, JSON.stringify(info), 'errors', errs);
  await p.close();
}
await b.close();
