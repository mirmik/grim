import { test, expect } from '@playwright/test';
import { openReaderTools } from './reader-controls';

export function mobileScenarios() {
  test('compact mobile navigation keeps actions and the active chapter accessible', async ({page}) => {
    await page.setViewportSize({width:360,height:800});
    await page.goto('/');
    await page.getByRole('button', {name:'Открыть книгу'}).first().click();
    for (const size of [{width:360,height:800},{width:390,height:844},{width:430,height:932},{width:720,height:360}]) {
      await page.setViewportSize(size);
      await expect(page.getByRole('button', {name:'Оглавление',exact:true})).toBeVisible();
      expect(await page.locator('header').evaluate(el=>el.getBoundingClientRect().height)).toBeLessThanOrEqual(50);
      expect(await page.locator('iframe').evaluate(el=>el.getBoundingClientRect().height)).toBeGreaterThan(size.height-100);
      expect(await page.locator('body').evaluate(el=>el.scrollWidth<=innerWidth)).toBe(true);
      await openReaderTools(page);
      await expect(page.getByLabel('Размер текста')).toBeVisible();
      await expect(page.getByRole('combobox', {name:'Тема оформления'})).toBeVisible();
      await page.getByRole('button', {name:/^Заметки/}).click();
      await expect(page.locator('.notes-panel')).toBeVisible();
      await expect(page.getByLabel('Размер текста')).not.toBeVisible();
      await page.getByRole('button', {name:'Закрыть заметки'}).click();
    }
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button', {name:'Оглавление',exact:true}).click();
    await page.getByRole('button', {name:/Лаборатория волны/}).click();
    await expect(page.locator('aside')).not.toBeVisible();
    await expect(page.frameLocator('iframe').locator('#amplitude')).toBeVisible();
    await page.getByRole('button', {name:'Оглавление',exact:true}).click();
    await expect(page.locator('nav .page-link.active')).toBeFocused();
    await expect(page.locator('nav .page-link.active')).toBeInViewport();
    await page.getByRole('button', {name:'Закрыть меню'}).click({position:{x:370,y:100}});
    await expect(page.locator('aside')).not.toBeVisible();
    await page.screenshot({path:test.info().outputPath('mobile-reader.png')});
  });

  test('text size preserves the reading anchor, interactive state and saved preference', async ({page,context}) => {
    await page.setViewportSize({width:390,height:844});
    await page.goto('/');
    await page.getByRole('button', {name:'Открыть книгу'}).first().click();
    const frame=page.frameLocator('iframe');
    await expect(frame.locator('#definition')).toHaveCSS('font-size','16px');
    await frame.locator('#definition').evaluate(el=>el.scrollIntoView());
    const before=await frame.locator('#definition').evaluate(el=>el.getBoundingClientRect().top);
    const src=await page.locator('iframe').getAttribute('src');
    await openReaderTools(page);
    await page.getByLabel('Размер текста').selectOption('20');
    await expect(frame.locator('#definition')).toHaveCSS('font-size','20px');
    expect(Math.abs(await frame.locator('#definition').evaluate(el=>el.getBoundingClientRect().top)-before)).toBeLessThan(2);
    expect(await page.locator('iframe').getAttribute('src')).toBe(src);
    await expect(frame.locator('.katex').first()).toBeAttached();
    // Book scripts cannot impersonate the parent or change reader preferences.
    await frame.locator('body').evaluate(()=>window.postMessage({grim:true,type:'reading-style',size:24},'*'));
    await expect(frame.locator('#definition')).toHaveCSS('font-size','20px');
    await page.getByRole('button', {name:'Настройки и действия'}).click();
    await expect.poll(()=>page.evaluate(()=>Object.keys(localStorage).filter(key=>key.startsWith('grim-reading:')).map(key=>JSON.parse(localStorage.getItem(key)!)).some(value=>value.position.anchor==='definition'))).toBe(true);
    await page.reload();
    await expect(frame.locator('#definition')).toHaveCSS('font-size','20px');
    await expect(frame.locator('#definition')).toBeInViewport();
    await frame.getByRole('link', {name:'измените волну в лаборатории →'}).click();
    await frame.locator('#amplitude').fill('1.8');
    await openReaderTools(page);
    await page.getByLabel('Размер текста').selectOption('14');
    await expect(frame.locator('#a-value')).toHaveText('1.8');
    await expect(frame.locator('html')).toHaveCSS('font-size','14px');
    // A second tab follows the preference without reloading its book.
    const other=await context.newPage();
    await other.goto(page.url());
    await expect(other.frameLocator('iframe').locator('html')).toHaveCSS('font-size','14px');
    await openReaderTools(other);
    await other.getByLabel('Размер текста').selectOption('18');
    await expect(frame.locator('html')).toHaveCSS('font-size','18px');
    await other.close();
    await page.getByLabel('Размер текста').selectOption('auto');
    await expect(frame.locator('html')).toHaveCSS('font-size','16px');
  });
}
