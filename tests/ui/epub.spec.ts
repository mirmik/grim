import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

test('EPUB upload, split chapters, figures, formulas, footnotes and live editing', async ({page, request}) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'grim-epub-ui-'));
  const file = path.join(directory, 'book.epub');
  execFileSync('python3', ['tests/epub_fixture.py', file, '--short-intro']);
  try {
    await page.goto('/');
    await page.getByRole('button', {name:'Импорт EPUB', exact:true}).click();
    await page.getByLabel('Файл EPUB').setInputFiles(file);
    await page.getByRole('button', {name:'Импортировать книгу', exact:true}).click();
    await expect(page.locator('.book-title')).toHaveText('Проверка EPUB');
    const frame = page.frameLocator('iframe');
    await expect(frame.locator('#book-intro')).toHaveText('Короткое введение');
    await expect(frame.locator('#intro')).toContainText('Первый абзац');
    await expect(frame.locator('mfrac')).toBeVisible();
    await expect(frame.locator('#diagram')).toBeVisible();
    await expect.poll(()=>frame.locator('img').evaluate((img:HTMLImageElement)=>img.naturalWidth)).toBeGreaterThan(0);
    await expect(frame.locator('#intro')).toHaveCSS('color', 'rgb(23, 45, 67)');
    await frame.getByRole('link', {name:'В конец главы'}).click();
    await expect(frame.locator('#end')).toBeInViewport();
    await frame.getByRole('link', {name:'Вернуться к началу'}).click();
    await expect(frame.locator('#intro')).toBeInViewport();
    await frame.getByRole('link', {name:'Сноска', exact:true}).click();
    await expect(frame.locator('#note')).toBeInViewport();
    await frame.getByRole('link', {name:'Назад к тексту'}).click();
    await expect(frame.locator('#intro')).toBeInViewport();
    await page.reload();
    await expect(frame.locator('#intro')).toBeVisible();
    const library = await (await request.get('/api/library')).json();
    const book = library.books.find((b:{title:string})=>b.title==='Проверка EPUB');
    const imported=JSON.parse(await readFile(path.join(book.root,'epub-import.json'),'utf8'));
    const first=imported.pages.find((p:{source:string})=>p.source==='OEBPS/intro.xhtml');
    const html = path.join(book.root, first.path);
    await writeFile(html, (await readFile(html,'utf8')).replace('Первый абзац.', 'Переведённый абзац.'));
    await expect(frame.locator('#intro')).toContainText('Переведённый абзац.');
    await page.getByRole('button',{name:'Библиотека',exact:true}).click();
    await expect(page.locator('.book-card').filter({hasText:'Проверка EPUB'})).toBeVisible();
  } finally {
    await rm(directory, {recursive:true, force:true});
  }
});

test('invalid EPUB shows an actionable error and permits retry', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name:'Импорт EPUB', exact:true}).click();
  await page.getByLabel('Файл EPUB').setInputFiles({name:'broken.epub', mimeType:'application/epub+zip', buffer:Buffer.from('not a zip')});
  await page.getByRole('button', {name:'Импортировать книгу', exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось импортировать EPUB');
  await expect(page.getByRole('button', {name:'Импортировать книгу', exact:true})).toBeEnabled();
});
