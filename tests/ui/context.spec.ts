import { test, expect, type Page } from '@playwright/test';
import katex from 'katex';

const sentence = 'Локальная параметризация r(u,v) позволяет использовать два независимых параметра.';
const metric = 'g=J^{\\mathsf T}J';

async function openContextFixture(page: Page) {
  await page.goto('/');
  await page.getByRole('button', {name: 'Открыть книгу'}).first().click();
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('.katex')).toBeAttached();
  await frame.locator('body').evaluate((body, html) => {
    body.innerHTML = html;
    scrollTo(0, 0);
  }, `<p id="sentence">Локальная параметризация ${katex.renderToString('r(u,v)')} позволяет использовать два независимых параметра.</p>
    <blockquote><p id="metric">Метрика ${katex.renderToString(metric)}.</p></blockquote>
    <div id="display">${katex.renderToString('\\frac{a}{b}', {displayMode: true})}</div>
    <p id="repeated">${katex.renderToString('x')} и ${katex.renderToString('x')}</p>
    <p id="plain">Первая <em>строка</em><br>Вторая строка</p>`);
  return frame;
}

test('context serializes each KaTeX formula once, including nested and display blocks', async ({page, request}) => {
  const frame = await openContextFixture(page);
  await frame.locator('#sentence').evaluate(el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    getSelection()!.removeAllRanges();
    getSelection()!.addRange(range);
  });
  const context = async () => (await (await request.get('/api/context')).json()).context;
  await expect.poll(async () => (await context())?.selection).toBe(sentence);
  expect((await context()).visible_text).toBe(`${sentence}\nМетрика ${metric}.\n\\frac{a}{b}\nx и x\nПервая строка\nВторая строка`);

  // A range can contain just the visual layer, excluding the MathML annotation.
  await frame.locator('#metric .katex-html').evaluate(el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    getSelection()!.removeAllRanges();
    getSelection()!.addRange(range);
  });
  await expect.poll(async () => (await context())?.selection).toBe(metric);
});

test('context preserves partial formula and ordinary text selections', async ({page, request}) => {
  const frame = await openContextFixture(page);
  const selected = async () => (await (await request.get('/api/context')).json()).context?.selection;
  await frame.locator('#sentence .katex-html').evaluate(el => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let u: Node | null = null, v: Node | null = null;
    while (walker.nextNode()) {
      if (walker.currentNode.textContent === 'u') u = walker.currentNode;
      if (walker.currentNode.textContent === 'v') v = walker.currentNode;
    }
    const range = document.createRange();
    range.setStart(u!, 0);
    range.setEnd(v!, 1);
    getSelection()!.removeAllRanges();
    getSelection()!.addRange(range);
  });
  await expect.poll(selected).toBe('u,v');

  await frame.locator('#sentence').evaluate(el => {
    const range = document.createRange();
    range.setStart(el.firstChild!, 'Локальная '.length);
    range.setEnd(el.lastChild!, ' позволяет'.length);
    getSelection()!.removeAllRanges();
    getSelection()!.addRange(range);
  });
  await expect.poll(selected).toBe('параметризация r(u,v) позволяет');

  await frame.locator('#plain').evaluate(el => {
    const range = document.createRange();
    range.setStart(el.firstChild!, 3);
    range.setEnd(el.lastChild!, 6);
    getSelection()!.removeAllRanges();
    getSelection()!.addRange(range);
  });
  await expect.poll(selected).toBe('вая строка\nВторая');
  await frame.locator('body').evaluate(() => getSelection()!.removeAllRanges());
  await expect.poll(selected).toBe('');
});
