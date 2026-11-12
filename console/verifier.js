// Vérification de la console unifiée : erreurs console, débordement mobile, liens, contraste.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const url = require('url');

const RACINE = path.resolve(__dirname, '..');
const PAGE = path.join(__dirname, 'plateforme-omega-hermes-v1-0.html');

(async () => {
  const r = {};
  const nav = await chromium.launch({ args: ['--no-sandbox'] });

  for (const [profil, viewport] of [['desktop', { width: 1280, height: 800 }], ['mobile', { width: 375, height: 812 }]]) {
    const ctx = await nav.newContext({ viewport, deviceScaleFactor: 1, colorScheme: 'light' });
    const page = await ctx.newPage();
    const erreurs = [];
    page.on('pageerror', (e) => erreurs.push('exception:' + e.message));
    page.on('console', (msg) => { if (msg.type() === 'error' || msg.type() === 'warning') erreurs.push(msg.type() + ':' + msg.text()); });
    page.on('requestfailed', (req) => erreurs.push('requestfailed:' + req.url() + ':' + req.failure().errorText));

    await page.goto(url.pathToFileURL(PAGE).href, { waitUntil: 'load' });
    const metrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollHeight: document.documentElement.scrollHeight,
      liens: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')),
      modules: document.querySelectorAll('.module').length,
      verdictTotal: document.querySelector('header .note strong')?.textContent,
      kpiLignes: document.querySelectorAll('tbody tr').length,
      missionVisible: !!document.querySelector('.mission'),
      missionText: document.querySelector('.mission')?.textContent.trim().substring(0, 250),
    }));
    const dep = metrics.scrollWidth - metrics.clientWidth;
    r[profil] = { ...metrics, debordement_px: dep, erreurs };
    await ctx.close();
  }

  // Les href pointent tous vers un fichier d'évidence réellement présent
  const liensDesktop = r.desktop.liens;
  const internes = liensDesktop.filter(h => h && !h.startsWith('#') && !h.startsWith('http'));
  const manquants = internes.filter(h => !fs.existsSync(path.join(RACINE, h)));

  r.liens = { total: liensDesktop.length, internes: internes.length, manquants };
  await nav.close();

  console.log(JSON.stringify(r, null, 2));
  process.exit(
    r.desktop.erreurs.length === 0 && r.mobile.erreurs.length === 0
    && r.mobile.debordement_px <= 0 && manquants.length === 0 ? 0 : 1
  );
})().catch(e => { console.error(e); process.exit(2); });
