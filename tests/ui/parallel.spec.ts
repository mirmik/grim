import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';

async function fixture(request:APIRequestContext, options:{ids?:boolean;extra?:boolean}={}) {
  const token=(await(await request.get('/api/library')).json()).writer_token;
  const headers={'X-Grim-Viewer':token};
  const book=await(await request.post('/api/library/create',{headers,data:{title:'Parallel translation'}})).json();
  const html=(translated=false)=>`<!doctype html><html><head><style>body{font:18px/1.6 Georgia;margin:24px}p{margin:20px 0}h1{font-size:26px}button{font:inherit}</style></head><body><h1 ${options.ids===false?'':'id="title"'}>${translated?'Перевод':'Original'}</h1>${Array.from({length:12},(_,i)=>`${translated && options.extra && i===3?'<p id="added">Дополнительное пояснение переводчика.</p>':''}<p ${options.ids===false?'':`id="p${i}"`}>${translated?`Перевод абзаца ${i}. `+'Более длинное объяснение на другом языке. '.repeat(i%3===0?12:2):`Original paragraph ${i}. `+'Some original text. '.repeat(options.ids===false?40:i%4===0?8:1)}</p>`).join('')}<button onclick="this.textContent='Kept'">Interactive</button><p><a href="two.html#end">Footnote</a></p></body></html>`;
  const original=html();
  await writeFile(path.join(book.root,'one.html'),original);
  await writeFile(path.join(book.root,'two.html'),'<h1>Second</h1><p id="end">Footnote text</p>');
  await writeFile(path.join(book.root,'book.json'),JSON.stringify({title:book.title,pages:[{id:'one',path:'one.html',title:'One'},{id:'two',path:'two.html',title:'Two'}]}));
  const response=await request.post(`/api/books/${book.id}/working-copy`,{headers});expect(response.ok()).toBeTruthy();
  const working=await(await request.get(`/api/books/${book.id}?version=working`)).json();
  await writeFile(path.join(working.root,'one.html'),html(true));
  // Finish preparing files before opening the reader, so the fixture's own
  // initial writes cannot be mistaken for the live edit under test.
  await expect.poll(async()=>(await(await request.get(`/api/books/${book.id}`)).json()).revision).toBeGreaterThan(working.revision);
  return {book,working,original,headers};
}
const source=(page:Page)=>page.frameLocator('iframe[title^="Оригинал:"]');
const working=(page:Page)=>page.frameLocator('iframe[title^="Рабочая копия:"]');
test.beforeEach(async({page})=>{
  page.on('pageerror',error=>{throw error;});
});
async function aligned(page:Page,ids=['p0','p1','p3','p6','p11']) {
  await expect.poll(async()=>{
    const tops=async(frame:ReturnType<typeof source>)=>Promise.all(ids.map(id=>frame.locator('#'+id).evaluate(el=>el.getBoundingClientRect().top+scrollY)));
    const [a,b]=await Promise.all([tops(source(page)),tops(working(page))]);
    return Math.max(...a.map((top,i)=>Math.abs(top-b[i])));
  }).toBeLessThan(2);
}

test('parallel paragraphs align and scroll together after resizing and changing typography',async({page,request})=>{
  const {book,original}=await fixture(request);
  await page.goto(`/?book=${book.id}`);
  await expect(page.locator('.parallel-reader iframe')).toHaveCount(2);
  await expect(source(page).locator('#p0')).toBeVisible();
  await aligned(page);
  await source(page).locator('#p6').evaluate(el=>el.scrollIntoView());
  await expect.poll(async()=>{
    const [a,b]=await Promise.all([source(page).locator('body').evaluate(()=>scrollY),working(page).locator('body').evaluate(()=>scrollY)]);return Math.abs(a-b);
  }).toBeLessThan(2);
  await page.setViewportSize({width:1600,height:900});await aligned(page);
  await page.getByRole('button',{name:'Настройки и действия'}).click();
  await page.getByLabel('Размер текста').selectOption('24');await aligned(page);
  await page.getByRole('button',{name:'Настройки и действия'}).click();
  await source(page).getByRole('button',{name:'Interactive',exact:true}).click();
  await page.getByLabel('Тема').selectOption('dark');
  await expect(source(page).getByRole('button',{name:'Kept',exact:true})).toHaveText('Kept');
  expect(await readFile(path.join(book.root,'one.html'),'utf8')).toBe(original);
});

test('working selection owns agent context and notes; live edits refresh only the copy',async({page,request})=>{
  await page.setViewportSize({width:1800,height:1000});
  const {book,working:copy}=await fixture(request);
  await page.goto(`/?book=${book.id}`);await aligned(page);
  await working(page).locator('#p1').evaluate(el=>{
    const range=document.createRange();range.selectNodeContents(el);getSelection()!.removeAllRanges();getSelection()!.addRange(range);
  });
  await expect.poll(async()=>{
    const context=(await(await request.get(`/api/context?book_id=${book.id}`)).json()).context;
    return context?.version==='working' && context.selection.includes('Перевод абзаца 1');
  }).toBe(true);
  await page.getByRole('button',{name:'＋ Заметка к выделению'}).click();
  await page.getByLabel('Новая заметка').fill('Translation note');
  await page.getByRole('button',{name:'Сохранить заметку'}).click();
  await expect.poll(async()=>(await(await request.get(`/api/books/${book.id}/notes`)).json()).notes[0]?.text).toBe('Translation note');
  expect((await(await request.get(`/api/books/${book.id}/notes?version=source`)).json()).notes).toEqual([]);
  await page.getByRole('button',{name:'Закрыть заметки'}).click();
  await page.getByRole('button',{name:'Оригинал',exact:true}).last().click();
  await source(page).getByRole('button',{name:'Interactive',exact:true}).click();
  const sourceSrc=await page.locator('iframe[title^="Оригинал:"]').getAttribute('src');
  const text=await readFile(path.join(copy.root,'one.html'),'utf8');
  await writeFile(path.join(copy.root,'one.html'),text.replace('Перевод абзаца 0.','Новый перевод абзаца 0.'));
  await expect(working(page).locator('#p0')).toContainText('Новый перевод');
  expect(await page.locator('iframe[title^="Оригинал:"]').getAttribute('src')).toBe(sourceSrc);
  await expect(source(page).getByRole('button',{name:'Kept',exact:true})).toBeAttached();
  await aligned(page);
});

test('missing pages have an explicit empty pane instead of an unrelated chapter',async({page,request})=>{
  const {book,working:copy}=await fixture(request);
  await writeFile(path.join(copy.root,'book.json'),JSON.stringify({title:'Translation',pages:[{id:'two',path:'two.html',title:'Two'}]}));
  await page.goto(`/?book=${book.id}`);
  await expect(source(page).getByRole('heading',{name:'Original',exact:true})).toBeVisible();
  await expect(page.getByText('Соответствующей страницы в этой версии нет.')).toBeVisible();
  await expect(page.locator('iframe')).toHaveCount(1);
  await page.getByRole('button',{name:'Показывать оригинал и копию рядом'}).click();
  const metadata=page.waitForResponse(response=>response.url().endsWith(`/api/books/${book.id}?version=working`) && response.ok());
  await writeFile(path.join(copy.root,'book.json'),JSON.stringify({title:'Translation',pages:[{id:'one',path:'one.html',title:'One'},{id:'two',path:'two.html',title:'Two'}]}));
  await metadata;
  await page.getByRole('button',{name:'Показывать оригинал и копию рядом'}).click();
  await expect(working(page).locator('#p0')).toBeVisible();
  await page.getByRole('button',{name:'Далее →'}).click();
  await expect(source(page).locator('#end')).toBeVisible();
  await expect(working(page).locator('#end')).toBeVisible();
});

test('stable IDs survive an added paragraph and navigation pairs corresponding pages',async({page,request})=>{
  const {book}=await fixture(request,{extra:true});
  await page.goto(`/?book=${book.id}`);await aligned(page);
  await expect(page.getByRole('status')).toContainText('Часть абзацев без соответствия');
  await working(page).getByRole('link',{name:'Footnote',exact:true}).click();
  await expect(source(page).locator('#end')).toBeVisible();
  await expect(working(page).locator('#end')).toBeVisible();
  await page.getByRole('button',{name:'Вернуться',exact:true}).click();
  await expect(working(page).locator('#p0')).toBeAttached();await aligned(page);
});

test('unidentified paragraphs align by order; narrow screens and explicit single mode retain reading',async({page,request})=>{
  const {book}=await fixture(request,{ids:false});
  await page.goto(`/?book=${book.id}`);
  await expect(page.getByRole('status')).toContainText('по порядку');
  await expect.poll(async()=>{
    const [a,b]=await Promise.all([source(page).locator('p').nth(6).evaluate(el=>el.getBoundingClientRect().top+scrollY),working(page).locator('p').nth(6).evaluate(el=>el.getBoundingClientRect().top+scrollY)]);return Math.abs(a-b);
  }).toBeLessThan(2);
  await source(page).locator('p').nth(6).evaluate(el=>el.scrollIntoView());
  await expect.poll(()=>page.evaluate(id=>JSON.parse(localStorage.getItem(`grim-reading:${id}:source`)||'{}').position?.block_index,book.id)).toBe(7);
  await page.getByRole('button',{name:'Показывать оригинал и копию рядом'}).click();
  await expect(page.locator('iframe')).toHaveCount(1);
  await expect.poll(()=>page.frameLocator('iframe').locator('p').nth(6).evaluate(el=>Math.abs(el.getBoundingClientRect().top))).toBeLessThan(2);
  await page.reload();await expect(page.locator('iframe')).toHaveCount(1);
  await page.getByRole('button',{name:'Показывать оригинал и копию рядом'}).click();
  await expect(page.locator('iframe')).toHaveCount(2);
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('iframe')).toHaveCount(1);
  await page.getByRole('button',{name:'Оглавление',exact:true}).click();
  await page.getByRole('button',{name:'Рабочая копия',exact:true}).click();
  await expect(page.frameLocator('iframe').getByRole('heading',{name:'Перевод',exact:true})).toBeVisible();
  await page.setViewportSize({width:1440,height:1000});
  await expect(page.locator('iframe')).toHaveCount(2);
  await expect(working(page).getByRole('heading',{name:'Перевод',exact:true})).toBeVisible();
});
