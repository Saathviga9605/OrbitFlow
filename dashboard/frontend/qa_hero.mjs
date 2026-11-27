import puppeteer from 'puppeteer-core';
const out = process.argv[2]; const w = +process.argv[3] || 1440; const h = +process.argv[4] || 900;
const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-gl=swiftshader','--enable-webgl','--no-sandbox'], headless: 'new' });
const p = await b.newPage(); await p.setViewport({ width: w, height: h });
await p.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded' }); await p.waitForSelector('.acts');
for (const a of [0,1,2,3]) { await p.evaluate((i)=>document.querySelectorAll('.acts button')[i].click(), a); await new Promise(r=>setTimeout(r, a===2?2600:1800)); await p.screenshot({ path: `${out}/hero-${w}-${a}.png` }); }
await b.close();
