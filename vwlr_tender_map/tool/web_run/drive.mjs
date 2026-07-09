// Drives the built Flutter web app (served at http://127.0.0.1:8080) through
// every screen and captures screenshots, for headless verification on a host
// where the real backend / font+canvaskit CDNs are unreachable.
//
// Prereqs (see README.md):
//   - build:  flutter build web --release --no-web-resources-cdn   (bundles canvaskit)
//   - point Config.supabaseUrl at the mock (http://127.0.0.1:54321) for the run
//   - node tool/web_run/mock_supabase.js &                         (:54321)
//   - python3 -m http.server 8080 --directory build/web &          (:8080)
//   - PW=$(npm root -g)/playwright/index.mjs PW_EXEC=<chromium> node tool/web_run/drive.mjs
//
// Notes on the two CDN work-arounds (only needed on locked-down networks; a
// normal phone/browser reaches both automatically):
//   - CanvasKit: build with --no-web-resources-cdn so it loads from canvaskit/.
//   - Roboto:    CanvasKit fetches it from fonts.gstatic.com; we route that
//                request to a local Roboto-Regular.ttf so text paints.
import fs from 'node:fs';

const FONT_PATH = process.env.FONT
  || '/opt/flutter/engine/src/flutter/txt/third_party/fonts/Roboto-Regular.ttf';
const { chromium } = await import(process.env.PW);
const FONT = fs.existsSync(FONT_PATH) ? fs.readFileSync(FONT_PATH) : null;
const W = 430, H = 932, navY = H - 40;

const b = await chromium.launch({
  executablePath: process.env.PW_EXEC,
  args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'],
});
const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: 'light' });
if (FONT) await ctx.route(/gstatic\.com\//, r =>
  (/\.(woff2?|ttf|otf)(\?|$)/i.test(r.request().url()) || /roboto/i.test(r.request().url()))
    ? r.fulfill({ status: 200, headers: { 'access-control-allow-origin': '*' }, contentType: 'font/ttf', body: FONT })
    : r.continue());

const p = await ctx.newPage();
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0, 140)));
const press = async (x, y, ms = 2600) => { await p.mouse.move(x, y); await p.mouse.down(); await p.waitForTimeout(90); await p.mouse.up(); await p.waitForTimeout(ms); };

await p.goto('http://127.0.0.1:8080', { waitUntil: 'load' });
await p.waitForTimeout(16000);                 // software-canvas first paint
await p.screenshot({ path: 'run_01_map.png' });
await press(W * 0.50, navY);                    // -> Tenders
await p.screenshot({ path: 'run_02_list.png' });
await press(215, 385);                          // open first card -> detail
await p.screenshot({ path: 'run_03_detail.png' });
await p.mouse.wheel(0, 900); await p.waitForTimeout(1500);
await p.screenshot({ path: 'run_04_detail_bottom.png' });
await press(22, 46, 1600);                      // back
await press(W * 0.84, navY);                    // -> Dashboard
await p.screenshot({ path: 'run_05_dashboard.png' });
await press(W * 0.50, navY);                    // -> Tenders
await press(W - 30, 341);                       // toggle a heart (write-back -> PATCH 204)
await p.screenshot({ path: 'run_06_after_heart.png' });

console.log('PAGEERRORS:', errs.length ? errs.join(' || ') : 'none');
await ctx.close();
await b.close();
