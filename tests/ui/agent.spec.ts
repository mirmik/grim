import { test, expect } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('chat edits the shared book through Nemor, keeps context and restores conversation', async ({page, request}) => {
  const runtime = await (await request.get('/api/agent/settings')).json();
  test.skip(!runtime.runtime_available, 'Install optional Nemor to test the real agent loop');
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('button', {name:'Открыть книгу'}).first().click();
  const bookId = new URL(page.url()).searchParams.get('book')!;
  const book = await (await request.get(`/api/books/${bookId}`)).json();
  const file = path.join(book.root, 'chapters/oscillations.html'), original = await readFile(file, 'utf8');
  const frame = page.frameLocator('iframe');
  await frame.locator('#definition').evaluate(el => {
    el.scrollIntoView();
    const range = document.createRange();range.selectNodeContents(el);
    getSelection()!.removeAllRanges();getSelection()!.addRange(range);
  });
  await expect.poll(async () => (await (await request.get(`/api/context?book_id=${bookId}`)).json()).context?.selection).toContain('Колебание — это изменение');
  await page.getByRole('button', {name:'Чат с агентом'}).click();
  await page.getByLabel('Имя модели', {exact:true}).fill('deterministic-test-model');
  await page.getByRole('button', {name:'Сохранить', exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('Настройки сохранены');
  await page.getByRole('button', {name:'Настройки агента', exact:true}).click();
  try {
    // The server accepts the job but the browser loses its POST response.
    await page.route('**/agent/jobs', async route => {await route.fetch();await route.abort();}, {times:1});
    await page.getByLabel('Сообщение о текущей книге').fill('Уточни определение колебания');
    await page.getByRole('button', {name:'Отправить', exact:true}).click();
    await expect(page.locator('.agent-message').last()).toHaveText('Уточнение записано в книгу.');
    await expect(page.getByLabel('Сообщение о текущей книге')).toHaveValue('');
    await expect(frame.locator('#definition')).toContainText('периодическое изменение');
    const jobs = (await (await request.get(`/api/books/${bookId}/agent`)).json()).jobs;
    expect(jobs).toHaveLength(1);
    expect(jobs[0].context.selection).toContain('Колебание — это изменение');
    await page.reload();
    await page.getByRole('button', {name:'Чат с агентом'}).click();
    await expect(page.locator('.agent-message').last()).toHaveText('Уточнение записано в книгу.');
    // The external editor sees and updates the same current file afterwards.
    await writeFile(file, (await readFile(file,'utf8')).replace('периодическое изменение', 'повторяющееся изменение'));
    await expect(frame.locator('#definition')).toContainText('повторяющееся изменение');
    await page.setViewportSize({width:390, height:844});
    await expect(page.getByRole('button', {name:'Закрыть чат'})).toBeInViewport();
    await page.screenshot({path:'test-results/grim-agent-mobile.png'});
    await page.getByRole('button', {name:'Закрыть чат'}).click();
    await page.getByRole('button', {name:'Контекст чтения', exact:false}).click();
    await expect(page.locator('.context-panel')).toBeVisible();
    const created = await (await request.post('/api/library/create', {headers:{'X-Grim-Viewer':book.writer_token},data:{title:'Отдельный разговор'}})).json();
    await page.goto(`/?book=${created.id}`);
    await page.getByRole('button', {name:'Чат с агентом'}).click();
    await expect(page.locator('.agent-note').filter({hasText:'Обсудите прочитанное'})).toBeVisible();
    await expect(page.locator('.agent-turn')).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {await writeFile(file, original);}
});
