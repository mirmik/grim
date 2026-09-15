import { test, expect } from '@playwright/test';

test('bundled book reads without API, preserves position, and runs local interactive assets', async ({page}) => {
  const apiRequests: string[] = [], errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', route => {apiRequests.push(route.request().url());return route.abort();});
  await page.goto('/');
  await expect(page.getByRole('button', {name: 'Добавить папку'})).toHaveCount(0);
  await page.locator('.book-card').filter({hasText: 'Математика движения'}).getByRole('button', {name: 'Открыть книгу'}).click();
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('.katex')).toBeAttached();
  await expect.poll(() => frame.locator('img').first().evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  await frame.locator('#definition').evaluate(el => {
    el.scrollIntoView();const r = document.createRange();r.selectNodeContents(el);
    getSelection()!.removeAllRanges();getSelection()!.addRange(r);
  });
  await page.getByRole('button', {name: 'Фрагмент'}).click();
  await expect(page.locator('.context-panel blockquote')).toContainText('Колебание');
  await expect(page.locator('.context-badge')).toHaveText('Чтение на устройстве');
  await page.getByRole('button', {name: 'Закрыть контекст'}).click();
  await page.reload();
  await expect(frame.locator('#definition')).toBeInViewport();
  await frame.getByRole('link', {name: 'измените волну в лаборатории →'}).click();
  await frame.locator('#amplitude').fill('1.8');
  await expect(frame.locator('#a-value')).toHaveText('1.8');
  await page.reload();
  await expect(frame.locator('#amplitude')).toBeAttached();
  await frame.getByRole('link', {name: '← Вернуться к формуле'}).click();
  await expect(frame.locator('#language')).toBeInViewport();
  await page.getByRole('button', {name: 'Оглавление', exact: true}).click();
  await page.getByRole('button', {name: 'Вопросы и открытия', exact: false}).click();
  await expect(page.locator('iframe')).toHaveAttribute('title', 'Вопросы и открытия');
  await page.screenshot({path: 'test-results/grim-android-reader.png'});
  await page.setViewportSize({width: 844, height: 390});
  await expect(page.getByRole('button', {name: 'Оглавление', exact: true})).toBeVisible();
  await expect(page.locator('aside')).not.toBeVisible();
  expect(await page.locator('footer').evaluate(el => el.getBoundingClientRect().bottom <= innerHeight)).toBe(true);
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
});

test('book sandbox and Android back action keep the reader isolated and navigable', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name: 'Открыть книгу'}).first().click();
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('#world')).toBeVisible();
  const result = await frame.locator('body').evaluate(async () => {
    let dom = false, api = false;
    try {void parent.document.body;dom = true;} catch {}
    try {await fetch('/offline/library.json');api = true;} catch {}
    return {dom, api, origin: window.origin};
  });
  expect(result).toEqual({dom: false, api: false, origin: 'null'});
  await page.getByRole('button', {name: 'Оглавление', exact: true}).click();
  expect(await page.evaluate(() => window.dispatchEvent(new Event('grim-back', {cancelable: true})))).toBe(false);
  await expect(page.locator('aside')).not.toBeVisible();
  await expect(page.locator('iframe')).toBeVisible();
  expect(await page.evaluate(() => window.dispatchEvent(new Event('grim-back', {cancelable: true})))).toBe(false);
  await expect(page.locator('.book-card').first()).toBeVisible();
  expect(await page.evaluate(() => window.dispatchEvent(new Event('grim-back', {cancelable: true})))).toBe(true);
});
