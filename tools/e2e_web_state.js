// Real-browser checks that the workspace keeps the user's place.
//
//   node tools/e2e_web_state.js scroll <url> <out.json>
//   node tools/e2e_web_state.js type   <url> <out.json> <text>
//
// Drives a running Flet web preview with Playwright Chromium through Flutter's
// accessibility tree (the same semantics a screen reader uses), like a user:
//
// scroll: scrolls the page with the mouse wheel until the first checkbox is in
//   view, clicks it, and reports where that checkbox is before and after the
//   click. A page that is rebuilt jumps back to the top, moving the checkbox
//   down by the scrolled distance.
// type:   clicks the first text field, types <text> key by key and reports the
//   focused element and its value. A page rebuilt on every keystroke loses the
//   focus (and with it the rest of the typed text).
const { chromium } = require('playwright');

async function semanticNodes(page, role) {
  return page.evaluate((wanted) => Array.from(document.querySelectorAll('flt-semantics'))
    .filter((n) => n.getAttribute('role') === wanted)
    .map((n) => {
      const r = n.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height,
               label: (n.getAttribute('aria-label') || n.textContent || '').slice(0, 60),
               checked: n.getAttribute('aria-checked') };
    }), role);
}

async function openPage(url) {
  const browser = await chromium.launch({
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 180000 });
  await page.waitForTimeout(8000);
  await page.evaluate(() => {
    const placeholder = document.querySelector('flt-semantics-placeholder');
    if (placeholder) placeholder.click();
  });
  await page.waitForTimeout(2000);
  return { browser, page };
}

async function scrollCheck(url) {
  const { browser, page } = await openPage(url);
  try {
    let boxes = await semanticNodes(page, 'checkbox');
    if (!boxes.length) throw new Error('no checkbox on the page');
    const target = boxes[0];
    const distance = Math.max(0, Math.round(target.y - 450));
    await page.mouse.move(900, 500);
    for (let moved = 0; moved < distance; moved += 200) {
      await page.mouse.wheel(0, Math.min(200, distance - moved));
      await page.waitForTimeout(120);
    }
    await page.waitForTimeout(1200);
    boxes = await semanticNodes(page, 'checkbox');
    const before = boxes[0];
    await page.mouse.click(before.x, before.y);
    await page.waitForTimeout(2500);
    boxes = await semanticNodes(page, 'checkbox');
    const after = boxes[0];
    return { scrolled: distance, before_y: Math.round(before.y), after_y: Math.round(after.y),
             moved_by: Math.round(after.y - before.y), checked_before: before.checked,
             checked_after: after.checked, label: before.label };
  } finally {
    await browser.close();
  }
}

async function typeCheck(url, text) {
  const { browser, page } = await openPage(url);
  try {
    // Flutter web exposes text fields as real <input>/<textarea> elements
    // labelled with the field's label.
    const fields = await page.evaluate(() => Array.from(document.querySelectorAll('input, textarea'))
      .map((e) => {
        const r = e.getBoundingClientRect();
        return { x: r.x + Math.min(r.width / 2, 200), y: r.y + r.height / 2, w: r.width,
                 label: e.getAttribute('aria-label') || '' };
      }).filter((f) => f.w > 0 && f.y > 0 && f.y < 900));
    if (!fields.length) throw new Error('no text field on the page');
    await page.mouse.click(fields[0].x, fields[0].y);
    await page.waitForTimeout(800);
    for (const ch of text) {
      await page.keyboard.type(ch);
      await page.waitForTimeout(150);
    }
    await page.waitForTimeout(1500);
    const focus = await page.evaluate(() => {
      const el = document.activeElement;
      return { tag: el ? el.tagName : null, value: el && 'value' in el ? el.value : null };
    });
    return { typed: text, focused_tag: focus.tag, focused_value: focus.value,
             kept_everything: focus.value === text, label: fields[0].label };
  } finally {
    await browser.close();
  }
}

async function nodeByLabel(page, fragment) {
  return page.evaluate((wanted) => {
    const node = Array.from(document.querySelectorAll('flt-semantics'))
      .find((n) => (n.getAttribute('aria-label') || n.textContent || '').includes(wanted)
                   && n.getAttribute('role') === 'button');
    if (!node) return null;
    const r = node.getBoundingClientRect();
    return { x: r.x + Math.min(r.width / 2, 120), y: r.y + r.height / 2 };
  }, fragment);
}

// list: scroll a long questionnaire list to <target>, select it, then edit its
//   wording: the selected row must stay where it was and the caret must stay
//   in the wording field while typing.
async function listCheck(url, target, suffix, fieldLabel = 'Question text',
                         anchor = 'Fictional statement 1.') {
  const { browser, page } = await openPage(url);
  try {
    let node = await nodeByLabel(page, target);
    const first = await nodeByLabel(page, anchor);
    if (!first) throw new Error('questionnaire list not found');
    await page.mouse.move(first.x, first.y + 120);
    for (let i = 0; i < 80 && (!node || node.y > 700 || node.y < 120); i += 1) {
      await page.mouse.wheel(0, 240);
      await page.waitForTimeout(150);
      node = await nodeByLabel(page, target);
    }
    if (!node) throw new Error(`${target} never came into view`);
    await page.waitForTimeout(800);
    node = await nodeByLabel(page, target);
    await page.mouse.click(node.x, node.y);
    await page.waitForTimeout(2500);
    const after = await nodeByLabel(page, target);
    // The wording field is labelled; its value is only in the DOM while focused.
    const field = await page.evaluate((label) => {
      const el = Array.from(document.querySelectorAll('textarea, input'))
        .find((e) => e.getAttribute('aria-label') === label);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }, fieldLabel);
    let typed = null;
    let shown = null;
    if (field) {
      await page.mouse.click(field.x, field.y);
      await page.waitForTimeout(600);
      shown = await page.evaluate(() => (document.activeElement || {}).value || null);
      await page.keyboard.press('End');
      for (const ch of suffix) {
        await page.keyboard.type(ch);
        await page.waitForTimeout(150);
      }
      await page.waitForTimeout(1500);
      typed = await page.evaluate(() => {
        const el = document.activeElement;
        return { tag: el ? el.tagName : null, value: el && 'value' in el ? el.value : null };
      });
    }
    return { target, before_y: Math.round(node.y), after_y: after ? Math.round(after.y) : null,
             moved_by: after ? Math.round(after.y - node.y) : null,
             editor_shows_item: Boolean(shown && shown.includes(target)),
             focused_tag: typed && typed.tag, final_value: typed && typed.value,
             kept_typing: Boolean(typed && typed.value && typed.value.includes(target)
                                  && typed.value.endsWith(suffix)) };
  } finally {
    await browser.close();
  }
}

// expand: opens the section whose header contains <text>, then clicks the
//   first checkbox; the section must still be open afterwards.
async function expandCheck(url, header) {
  const { browser, page } = await openPage(url);
  try {
    const countNodes = () => page.evaluate(() => document.querySelectorAll('flt-semantics').length);
    let node = await nodeByLabel(page, header);
    await page.mouse.move(900, 500);
    for (let i = 0; i < 40 && (!node || node.y > 650); i += 1) {
      await page.mouse.wheel(0, 200);
      await page.waitForTimeout(150);
      node = await nodeByLabel(page, header);
    }
    if (!node) throw new Error(`${header} not found`);
    // A section's content is on screen when its fields or texts are in the
    // accessibility tree; the count of nodes is the simplest common signal.
    const collapsed = await countNodes();
    await page.mouse.click(node.x, node.y);
    await page.waitForTimeout(1500);
    const expanded = await countNodes();
    const boxes = await semanticNodes(page, 'checkbox');
    const box = boxes.find((b) => b.y > 80 && b.y < 860) || boxes[0];
    await page.mouse.click(box.x, box.y);
    await page.waitForTimeout(2500);
    const afterCheck = await countNodes();
    return { header, nodes_collapsed: collapsed, nodes_expanded: expanded,
             nodes_after_check: afterCheck,
             opened: expanded > collapsed, still_open: expanded > collapsed && afterCheck > collapsed };
  } finally {
    await browser.close();
  }
}

(async () => {
  const [mode, url, out, text = 'Fictional stress study', fieldLabel, anchor] = process.argv.slice(2);
  if (mode === 'expand') {
    const result = await expandCheck(url, text);
    require('fs').writeFileSync(out, JSON.stringify(result, null, 1));
    console.log(JSON.stringify(result));
    return;
  }
  const result = mode === 'scroll' ? await scrollCheck(url)
    : mode === 'list' ? await listCheck(url, text, ' (edited)', fieldLabel || undefined,
                                         anchor || undefined)
      : await typeCheck(url, text);
  require('fs').writeFileSync(out, JSON.stringify(result, null, 1));
  console.log(JSON.stringify(result));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
