import { test, expect, type Page } from '@playwright/test';
import { readFile, writeFile, mkdir, mkdtemp, cp } from 'node:fs/promises';
import path from 'node:path';

async function openDemo(page:Page) {
  await page.goto('/');
  await page.getByRole('button',{name:'Открыть книгу'}).first().click();
}


test('selection → API → disk edit → live reload with reading position', async ({page, request}) => {
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await openDemo(page);
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('#definition')).toBeAttached();
  await frame.locator('#definition').evaluate(el=>{el.scrollIntoView();const range=document.createRange();range.selectNodeContents(el);const s=getSelection()!;s.removeAllRanges();s.addRange(range);});
  await expect.poll(async()=> (await (await request.get('/api/context')).json()).context?.selection).toContain('Колебание — это изменение');
  const before = (await (await request.get('/api/context')).json()).context;
  expect(before.visible_text).toContain('Колебание');
  expect(before.scroll_y).toBeGreaterThan(100);
  await page.getByRole('button',{name:'Контекст чтения',exact:false}).click();
  await expect(page.locator('.context-panel blockquote')).toContainText('Колебание');
  const root = (await (await request.get('/api/library')).json()).books[0].root;
  const file=path.join(root,before.page.path), original=await readFile(file,'utf8');
  try {
    await writeFile(file,original.replace('Колебание — это изменение','Колебание — это повторяющееся изменение'));
    await expect(frame.locator('#definition')).toContainText('повторяющееся изменение');
    await expect.poll(async()=> (await (await request.get('/api/context')).json()).context?.visible_text).toContain('повторяющееся изменение');
    const after = (await (await request.get('/api/context')).json()).context;
    expect(Math.abs(after.scroll_y-before.scroll_y)).toBeLessThan(120);
    expect(after.selection).toBe('');
  } finally {await writeFile(file,original);}
  expect(errors).toEqual([]);
});

test('mouse selection remains available when focus moves to the notes panel', async ({page}) => {
  await openDemo(page);
  const definition=page.frameLocator('iframe').locator('#definition');
  await definition.scrollIntoViewIfNeeded();
  await page.getByRole('button',{name:'Заметки',exact:true}).click();
  await expect(page.getByText('Чтобы добавить заметку')).toBeVisible();
  const box=await definition.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x+12,box!.y+18);
  await page.mouse.down();
  await page.mouse.move(box!.x+Math.min(box!.width-12,260),box!.y+18,{steps:8});
  await page.mouse.up();
  await expect(page.getByLabel('Новая заметка')).toBeVisible();
  await page.getByRole('button',{name:'Закрыть заметки'}).click();
  await expect(page.getByRole('button',{name:'＋ Заметка к выделению'})).toBeVisible();
  await page.getByRole('button',{name:'＋ Заметка к выделению'}).click();
  await expect(page.getByLabel('Новая заметка')).toBeVisible();
});

test('notes survive reload and follow a quoted block through a text edit', async ({page, request}) => {
  await openDemo(page);
  const frame=page.frameLocator('iframe'),definition=frame.locator('#definition');
  await expect(definition).toBeAttached();
  await definition.evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);const selection=getSelection()!;selection.removeAllRanges();selection.addRange(range);});
  await definition.evaluate(()=>{(window as any).grimParentMessages=[];addEventListener('message',event=>(window as any).grimParentMessages.push(event.data));});
  await page.getByRole('button',{name:'Заметки',exact:true}).click();
  await expect(page.getByRole('region',{name:'Заметки'})).toContainText('Колебание — это изменение');
  await page.getByLabel('Новая заметка').fill('Вернуться к этому определению');
  await page.getByRole('button',{name:'Сохранить заметку'}).click();
  await expect(page.locator('.note-card')).toContainText('Вернуться к этому определению');
  expect(await definition.evaluate(()=>JSON.stringify((window as any).grimParentMessages))).not.toContain('Вернуться к этому определению');
  await expect.poll(()=>definition.evaluate(()=>document.documentElement.dataset.grimNotesResolved)).toBe('1');

  await page.reload();
  await page.getByRole('button',{name:/Заметки/}).click();
  await expect(page.locator('.note-card')).toContainText('Вернуться к этому определению');

  const root=(await (await request.get('/api/library')).json()).books[0].root;
  const file=path.join(root,'chapters/oscillations.html'),original=await readFile(file,'utf8');
  try {
    const changed=original.replace('Колебание — это изменение','Колебание — это небольшое повторяющееся изменение');
    await writeFile(file,changed);
    await expect(definition).toContainText('небольшое повторяющееся');
    await expect.poll(()=>definition.evaluate(()=>document.documentElement.dataset.grimNotesResolved)).toBe('1');
    await expect(page.locator('.note-card .note-warning')).toHaveCount(0);
    await page.locator('.note-target').click();
    await expect(definition).toBeInViewport();
    const replaced=changed.replace(/<p id="definition">.*?<\/p>/,'<p id="replacement">Совершенно новое определение без прежней цитаты.</p>');
    await writeFile(file,replaced);
    await expect(frame.locator('#replacement')).toBeVisible();
    await expect(page.locator('.note-card .note-warning')).toBeVisible();
    await page.getByRole('button',{name:'Изменить'}).click();
    await page.getByLabel('Текст заметки').fill('Обновлённая заметка');
    await page.getByRole('button',{name:'Сохранить',exact:true}).click();
    await expect(page.locator('.note-card')).toContainText('Обновлённая заметка');
    await page.getByRole('button',{name:'Удалить'}).click();
    await expect(page.locator('.note-card')).toHaveCount(0);
  } finally {await writeFile(file,original);}
});

test('local assets, KaTeX, relative links, slider and fragment navigation', async({page})=>{
  await openDemo(page);
  const frame=page.frameLocator('iframe');
  await expect(frame.locator('.katex')).toBeAttached();
  await page.screenshot({path:'test-results/grim-desktop.png'});
  expect(await frame.locator('img').evaluate((el:HTMLImageElement)=>el.complete && el.naturalWidth>0)).toBe(true);
  await frame.getByRole('link',{name:'измените волну в лаборатории →'}).click();
  await expect(frame.locator('#amplitude')).toBeVisible();
  await frame.locator('#amplitude').fill('1.8');
  await expect(frame.locator('#a-value')).toHaveText('1.8');
  await frame.getByRole('link',{name:'← Вернуться к формуле'}).click();
  await expect(frame.locator('#language')).toBeInViewport();
  await page.getByRole('button',{name:'Вопросы и открытия',exact:false}).click();
  const downloadPromise=page.waitForEvent('download');
  await frame.getByRole('link',{name:'Скачать памятку эксперимента ↓'}).click();
  expect((await downloadPromise).suggestedFilename()).toBe('experiment.txt');
});

test('book scripts cannot access parent DOM or control API',async({page})=>{
  await openDemo(page);
  const frame=page.frameLocator('iframe');
  await expect(frame.locator('#world')).toBeVisible();
  const result=await frame.locator('body').evaluate(async()=>{
    let dom=false,api=false;
    try {void parent.document.body;dom=true;}catch{}
    try {await fetch('/api/library');api=true;}catch{}
    return {dom,api,origin:window.origin};
  });
  expect(result).toEqual({dom:false,api:false,origin:'null'});
});

test('manifest changes recover and mobile navigation works',async({page,request})=>{
  await page.setViewportSize({width:390,height:844});await openDemo(page);
  const root=(await (await request.get('/api/library')).json()).books[0].root;
  const file=path.join(root,'book.json'),original=await readFile(file,'utf8');
  try {
    await writeFile(file,'{');
    await expect(page.getByRole('alert')).toBeVisible();
    await writeFile(file,original);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.getByRole('button',{name:'Оглавление',exact:true}).click();
    await page.getByRole('button',{name:'Лаборатория волны',exact:false}).click();
    await expect(page.frameLocator('iframe').locator('#amplitude')).toBeVisible();
    await page.screenshot({path:'test-results/grim-mobile.png'});
  } finally {await writeFile(file,original);}
});

test('SSE reconnect refreshes the book after a closed event stream',async({page,request})=>{
  let first = true;
  let release!: () => void;
  const gate = new Promise<void>(resolve => {release = resolve;});
  const demo=(await (await request.get('/api/library')).json()).books[0];
  await page.route('**/api/books/*/events',async route=>{
    if (first) {
      first = false;
      await route.fulfill({status:200,contentType:'text/event-stream',body:`data: ${JSON.stringify({book_id:demo.id,revision:0,changed:[]})}\n\n`});
    } else {await gate; await route.continue();}
  });
  await openDemo(page);
  await expect(page.frameLocator('iframe').locator('#world')).toBeVisible();
  const root=(await (await request.get('/api/library')).json()).books[0].root;
  const file=path.join(root,'chapters/oscillations.html'),original=await readFile(file,'utf8');
  try {
    await expect(page.locator('.connection')).toContainText('Восстанавливаем');
    await writeFile(file,original.replace('Мир в ритме<br>колебаний','Мир непрерывных<br>колебаний'));
    release();
    await expect(page.frameLocator('iframe').locator('#world')).toContainText('Мир непрерывных', {timeout:15000});
    await expect(page.locator('.connection')).toContainText('Книга обновляется');
  } finally {release();await writeFile(file,original);}
});

test('create empty book, persist library and add first page live',async({page,request})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'+ Новая книга',exact:true}).click();
  await page.getByLabel('Название книги').fill('Моя новая книга');
  await page.getByRole('button',{name:'Создать книгу',exact:true}).click();
  await expect(page.locator('.empty-book')).toContainText('Моя новая книга');
  const id=new URL(page.url()).searchParams.get('book')!;
  const book=(await (await request.get('/api/books/'+id)).json());
  expect(book.pages).toEqual([]);
  await expect.poll(async()=> (await (await request.get('/api/context?book_id='+id)).json()).context?.book.id).toBe(id);
  await writeFile(path.join(book.root,'start.html'),'<html><head></head><body><h1 id="start">Первая мысль</h1><p id="idea">Написано внешним агентом.</p></body></html>');
  await writeFile(path.join(book.root,'book.json'),JSON.stringify({title:book.title,pages:[{id:'start',title:'Начало',path:'start.html'}]}));
  await expect(page.frameLocator('iframe').locator('#start')).toHaveText('Первая мысль');
  await page.getByRole('button',{name:'← Библиотека',exact:true}).click();
  await expect.poll(async()=> (await (await request.get('/api/context?book_id='+id)).json()).context).toBeNull();
  await page.reload();
  await expect(page.locator('.book-card').filter({hasText:'Моя новая книга'})).toBeVisible();
  await page.locator('.book-card').filter({hasText:'Моя новая книга'}).getByRole('button',{name:'Открыть книгу'}).click();
  await expect(page.frameLocator('iframe').locator('#start')).toHaveText('Первая мысль');
});

test('add folder and keep two reader tabs, edits and saved positions independent',async({page,context,request})=>{
  const demo=(await (await request.get('/api/library')).json()).books[0];
  const folder=await mkdtemp(path.join(path.dirname(demo.root),'attached-'));
  await cp(demo.root,folder,{recursive:true});
  const toc=JSON.parse(await readFile(path.join(folder,'book.json'),'utf8'));
  toc.title='Другая книга';
  await writeFile(path.join(folder,'book.json'),JSON.stringify(toc));
  const secondFile=path.join(folder,'chapters/oscillations.html');
  await writeFile(secondFile,(await readFile(secondFile,'utf8')).replace('Колебание — это изменение','Вторая книга — это другое изменение'));
  await openDemo(page);
  const tab=await context.newPage();await tab.goto('/');
  await tab.getByRole('button',{name:'Добавить папку',exact:true}).click();
  await tab.getByLabel('Путь к папке на этом компьютере').fill(folder);
  await tab.getByRole('button',{name:'Подключить папку',exact:true}).click();
  await expect(tab.frameLocator('iframe').locator('#definition')).toContainText('Вторая книга');
  const secondId=new URL(tab.url()).searchParams.get('book')!;
  for(const p of [page,tab]) {
    await p.frameLocator('iframe').locator('#definition').evaluate(el=>{el.scrollIntoView();const r=document.createRange();r.selectNodeContents(el);getSelection()!.removeAllRanges();getSelection()!.addRange(r);});
  }
  await expect.poll(async()=> (await (await request.get('/api/context?book_id='+demo.id)).json()).context?.selection).toContain('Колебание');
  await expect.poll(async()=> (await (await request.get('/api/context?book_id='+secondId)).json()).context?.selection).toContain('Вторая книга');
  const before=(await (await request.get('/api/context?book_id='+demo.id)).json()).context;
  const other=(await (await request.get('/api/context?book_id='+secondId)).json()).context;
  expect(before.reader_id).not.toBe(other.reader_id);expect(other.book.root).toBe(folder);
  const firstSrc=await page.locator('iframe').getAttribute('src');
  const secondSrc=await tab.locator('iframe').getAttribute('src');
  await writeFile(secondFile,(await readFile(secondFile,'utf8')).replace('Вторая книга — это другое изменение','Вторая книга обновлена независимо'));
  await expect(tab.frameLocator('iframe').locator('#definition')).toContainText('обновлена независимо');
  expect(await tab.locator('iframe').getAttribute('src')).not.toBe(secondSrc);
  expect(await page.locator('iframe').getAttribute('src')).toBe(firstSrc);
  expect((await (await request.get('/api/context?reader_id='+before.reader_id)).json()).context.selection).toContain('Колебание');
  // Returning through the library restores this book's position, even after reload.
  await page.getByRole('button',{name:'← Библиотека',exact:true}).click();
  await expect(page.locator('.book-card').filter({hasText:demo.title})).toBeVisible();
  await page.screenshot({path:'test-results/grim-library.png'});
  await page.locator('.book-card').filter({hasText:demo.title}).getByRole('button',{name:'Открыть книгу'}).click();
  await page.reload();
  await expect(page.frameLocator('iframe').locator('#definition')).toBeInViewport();
  await expect.poll(async()=> (await (await request.get('/api/context?book_id='+demo.id)).json()).context?.scroll_y).toBeGreaterThan(100);
  await expect(tab.frameLocator('iframe').locator('#definition')).toContainText('обновлена независимо');
  // The book itself cannot use postMessage to register another folder.
  await tab.frameLocator('iframe').locator('body').evaluate(()=>parent.postMessage({grim:true,type:'add',root:'/tmp'},'*'));
  expect((await (await request.get('/api/library')).json()).books.some((b:any)=>b.root==='/tmp')).toBe(false);
});
