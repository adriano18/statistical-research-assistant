// Capture Stage 33 workspace screenshots from a running Flet web preview.
//
//   node tools/capture_workspace.js <url> <out.png> [width] [height] [scale] [waitMs]
//
// Uses the pre-installed Playwright Chromium with software GL (CanvasKit).
// `scale` is the device pixel ratio: 1, 1.25, 1.5 or 2 emulate 100–200 %
// Windows display scaling for the high-DPI checks.
const { chromium } = require('playwright');

async function capture(url, out, width, height, scale, wait) {
  const browser = await chromium.launch({
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: Number(width), height: Number(height) },
      deviceScaleFactor: Number(scale),
    });
    await page.goto(url, { waitUntil: 'networkidle', timeout: 180000 });
    await page.waitForTimeout(Number(wait));
    // One frame of the larger pages (Analyze) can take longer than
    // Playwright's default 30 s with software rendering on a busy runner.
    await page.screenshot({ path: out, timeout: 120000 });
  } finally {
    await browser.close().catch(() => {});
  }
}

(async () => {
  const [url, out, width = '1440', height = '900', scale = '1', wait = '9000'] =
    process.argv.slice(2);
  try {
    await capture(url, out, width, height, scale, wait);
  } catch (error) {
    // The software renderer occasionally crashes the browser tab on large
    // high-DPI canvases ("Page crashed") or delivers no frame in time on a
    // busy CI runner. Neither produces a picture of the app at all, so it is
    // retried once in a fresh browser; a second failure, and any other error,
    // fails. Rendered pages are still checked for blank, unrendered or error
    // content by workspace_screenshot_suite.py.
    if (!/Page crashed|Target crashed|screenshot: Timeout/i.test(String(error))) throw error;
    console.error(`no screenshot (${error.message.split('\n')[0]}); retrying once`);
    await capture(url, out, width, height, scale, wait);
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
