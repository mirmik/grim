import { test, expect } from '@playwright/test';

export function themeScenarios() {
  test('theme follows system, persists explicit choice and synchronizes tabs', async ({page, context}) => {
    await page.emulateMedia({colorScheme:'dark'});
    await page.goto('/');
    const picker = page.getByRole('combobox', {name:'Тема оформления'});
    await expect(picker).toHaveValue('system');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('.book-card').first()).toHaveCSS('background-color', 'rgb(23, 33, 29)');
    await page.screenshot({path:test.info().outputPath('library-dark.png')});
    await picker.selectOption('light');
    await page.reload();
    await expect(picker).toHaveValue('light');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    const other = await context.newPage();
    await other.goto('/');
    await other.getByRole('combobox', {name:'Тема оформления'}).selectOption('dark');
    await expect(picker).toHaveValue('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await other.close();
    await picker.selectOption('system');
    await page.emulateMedia({colorScheme:'light'});
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.emulateMedia({colorScheme:'dark'});
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  });

  test('book theme preserves position, selection, media, interactive state and sandbox', async ({page}) => {
    await page.goto('/');
    const picker = page.getByRole('combobox', {name:'Тема оформления'});
    await picker.selectOption('light');
    await page.getByRole('button', {name:'Открыть книгу'}).first().click();
    const frame = page.frameLocator('iframe');
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'light');
    await expect(frame.locator('.katex')).toBeAttached();
    const svgFill = await frame.locator('svg circle').first().getAttribute('fill');
    await frame.locator('#definition').evaluate(el => {
      el.scrollIntoView();
      const range = document.createRange();range.selectNodeContents(el);
      getSelection()!.removeAllRanges();getSelection()!.addRange(range);
    });
    const before = await frame.locator('body').evaluate(() => ({scroll:scrollY, selection:getSelection()!.toString()}));
    const src = await page.locator('iframe').getAttribute('src');
    await picker.selectOption('dark');
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'dark');
    await expect(frame.locator('html')).toHaveCSS('background-color', 'rgb(23, 33, 29)');
    await expect(frame.locator('#definition')).toHaveCSS('color', 'rgb(224, 233, 223)');
    await expect(frame.locator('.katex').first()).toHaveCSS('color', 'rgb(224, 233, 223)');
    expect(await frame.locator('body').evaluate(() => ({scroll:scrollY, selection:getSelection()!.toString()}))).toEqual(before);
    expect(await page.locator('iframe').getAttribute('src')).toBe(src);
    expect(await frame.locator('svg circle').first().getAttribute('fill')).toBe(svgFill);
    await expect(frame.locator('img').first()).toHaveCSS('filter', 'none');
    await expect(frame.locator('svg').first()).toHaveCSS('filter', 'none');
    // Messages from a book itself cannot impersonate the viewer.
    await frame.locator('body').evaluate(() => window.postMessage({grim:true,type:'theme',theme:'light'}, '*'));
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'dark');
    await frame.getByRole('link', {name:'измените волну в лаборатории →'}).click();
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'dark');
    await frame.locator('#amplitude').fill('1.8');
    await picker.selectOption('light');
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'light');
    await expect(frame.locator('#a-value')).toHaveText('1.8');
    await expect(frame.locator('html')).toHaveCSS('background-color', 'rgb(255, 254, 250)');
    await picker.selectOption('dark');
    await page.reload();
    await expect(frame.locator('html')).toHaveAttribute('data-grim-theme', 'dark');
    await page.setViewportSize({width:360,height:800});
    for (const control of [picker, page.getByRole('button', {name:'Оглавление', exact:true})]) {
      const box = await control.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(360);
    }
    expect(await page.locator('body').evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('button', {name:'Оглавление', exact:true}).click();
    const header = await page.locator('header').boundingBox();
    const sidebar = await page.locator('aside').boundingBox();
    expect(Math.abs(sidebar!.y - (header!.y + header!.height))).toBeLessThan(2);
    await page.getByRole('button', {name:'Оглавление', exact:true}).click();
    await page.screenshot({path:test.info().outputPath('reader-dark.png')});
  });

  test('unavailable storage does not prevent theme switching', async ({page}) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Storage blocked', 'SecurityError');}});
    });
    await page.goto('/');
    await page.getByRole('combobox', {name:'Тема оформления'}).selectOption('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.getByRole('button', {name:'Открыть книгу'}).first()).toBeVisible();
  });
}
