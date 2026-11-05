// Capture Stage 33 workspace screenshots from a running Flet web preview.
//
//   node tools/capture_workspace.js <url> <out.png> [width] [height] [scale] [waitMs]
//
// Uses the pre-installed Playwright Chromium with software GL (CanvasKit).
// `scale` is the device pixel ratio: 1, 1.25, 1.5 or 2 emulate 100–200 %
// Windows display scaling for the high-DPI checks.
const { chromium } = require('playwright');

(async () => {
  const [url, out, width = '1440', height = '900', scale = '1', wait = '9000'] =
    process.argv.slice(2);
  const browser = await chromium.launch({
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const page = await browser.newPage({
    viewport: { width: Number(width), height: Number(height) },
    deviceScaleFactor: Number(scale),
  });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 180000 });
  await page.waitForTimeout(Number(wait));
  await page.screenshot({ path: out });
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
