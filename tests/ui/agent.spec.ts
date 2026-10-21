import { test, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { openReaderTools } from '../reader-controls';

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
  if(!await page.getByLabel('Имя модели', {exact:true}).isVisible())await page.getByRole('button',{name:'Настройки агента',exact:true}).click();
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
    await openReaderTools(page);
    await page.getByRole('button', {name:'Контекст чтения', exact:false}).click();
    await expect(page.locator('.context-panel')).toBeVisible();
    const created = await (await request.post('/api/library/create', {headers:{'X-Grim-Viewer':book.writer_token},data:{title:'Отдельный разговор'}})).json();
    await page.goto(`/?book=${created.id}`);
    await openReaderTools(page);
    await page.getByRole('button', {name:'Чат с агентом'}).click();
    await expect(page.locator('.agent-note').filter({hasText:'Обсудите прочитанное'})).toBeVisible();
    await expect(page.locator('.agent-turn')).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {await writeFile(file, original);}
});

for(const width of [1440,390]) {
  test(`new chats keep old history and expose real book/model context at ${width}px`,async({page,request,context})=>{
    await page.setViewportSize({width,height:1000});
    const library=await(await request.get('/api/library')).json(), headers={'X-Grim-Viewer':library.writer_token};
    await request.put('/api/agent/settings',{headers,data:{model:'test-chat-model',api_token:'chat-debug-secret'}});
    const book=await(await request.post('/api/library/create',{headers,data:{title:'Книга для отладки чата'}})).json();
    const initial=(await(await request.get(`/api/books/${book.id}`)).json()).revision;
    await mkdir(path.join(book.root,'chapters'),{recursive:true});
    await writeFile(path.join(book.root,'chapters/oscillations.html'),'<h1>Глава о колебаниях</h1><p id="definition">Колебание — это изменение состояния.</p>');
    await writeFile(path.join(book.root,'book.json'),JSON.stringify({title:book.title,subtitle:'Автор И. Тестов',description:'Аннотация о чтении с агентом',pages:[{id:'oscillations',title:'Глава о колебаниях',path:'chapters/oscillations.html'}]}));
    await expect.poll(async()=>(await(await request.get(`/api/books/${book.id}`)).json()).revision).toBeGreaterThan(initial);
    const openChat=async(target=page)=>{if(width<600)await openReaderTools(target);await target.getByRole('button',{name:'Чат с агентом',exact:true}).click();};
    await page.goto(`/?book=${book.id}`);await openChat();
    await page.getByLabel('Сообщение о текущей книге').fill('Как называется эта книга?');
    await page.getByRole('button',{name:'Контекст агента',exact:true}).click();
    const preview=page.getByLabel('Предпросмотр запроса модели',{exact:true});
    await expect(preview).toHaveValue(/Книга для отладки чата/);
    const payload=JSON.parse(await preview.inputValue());
    expect(payload.messages).toHaveLength(2);
    expect(payload.tools.map((tool: any) => tool.function.name)).toEqual(expect.arrayContaining(['notes_list', 'notes_read', 'notes_create', 'notes_update', 'notes_delete']));
    expect(payload.messages[1].content).toContain('Аннотация о чтении с агентом');
    expect(payload.messages[1].content).toContain('Автор И. Тестов');
    expect(payload.messages[1].content).toContain('Как называется эта книга?');
    expect(await preview.inputValue()).not.toContain('chat-debug-secret');
    await page.getByRole('button',{name:'Вернуться к чату',exact:true}).click();
    await expect(page.getByLabel('Сообщение о текущей книге')).toHaveValue('Как называется эта книга?');
    await page.getByRole('button',{name:'Отправить',exact:true}).click();
    await expect(page.locator('.agent-message').last()).toHaveText('Уточнение записано в книгу.');
    const old=(await(await request.get(`/api/books/${book.id}/agent`)).json()).chat.id;
    await page.getByRole('button',{name:'Контекст агента',exact:true}).click();
    const sent=page.getByLabel('Последний запрос модели',{exact:true});
    await expect(sent).toBeVisible();
    const actual=JSON.parse(await sent.inputValue());
    expect(actual.messages.at(-1).role).toBe('tool');
    expect(actual.messages.some((message:{content?:string})=>message.content?.includes('Книга для отладки чата'))).toBe(true);
    expect(await sent.inputValue()).not.toContain('chat-debug-secret');
    await page.getByRole('button',{name:'Начать новый чат',exact:true}).click();
    await expect(page.locator('.agent-turn')).toHaveCount(0);
    await page.getByLabel('Сообщение о текущей книге').fill('Отдельный черновик');
    await page.getByRole('button',{name:'Старые чаты',exact:true}).click();
    await page.getByRole('navigation',{name:'Чаты этой книги'}).getByRole('button',{name:/Как называется эта книга/}).click();
    await expect(page.locator('.agent-turn')).toHaveCount(1);
    await expect(page.getByLabel('Сообщение о текущей книге')).toHaveValue('');
    await page.getByRole('button',{name:'Старые чаты',exact:true}).click();
    await page.getByRole('navigation',{name:'Чаты этой книги'}).getByRole('button',{name:/^Новый чат/}).click();
    await expect(page.getByLabel('Сообщение о текущей книге')).toHaveValue('Отдельный черновик');
    await page.getByRole('button',{name:'Старые чаты',exact:true}).click();
    await page.getByRole('navigation',{name:'Чаты этой книги'}).getByRole('button',{name:/Как называется эта книга/}).click();
    await expect(page.locator('.agent-turn')).toHaveCount(1);
    await page.reload();await openChat();
    await expect(page.locator('.agent-turn')).toHaveCount(1);
    expect((await(await request.get(`/api/books/${book.id}/agent`)).json()).chat.id).toBe(old);
    if(width===1440) {
      const other=await context.newPage();
      await other.goto(`/?book=${book.id}`);await openChat(other);
      await expect(other.locator('.agent-turn')).toHaveCount(1);
      await page.getByRole('button',{name:'Старые чаты',exact:true}).click();
      await page.getByRole('navigation',{name:'Чаты этой книги'}).getByRole('button',{name:/^Новый чат/}).click();
      await expect(page.locator('.agent-turn')).toHaveCount(0);
      await other.reload();await openChat(other);
      await expect(other.locator('.agent-turn')).toHaveCount(1);
      await other.close();
    }
  });
}

for(const width of [1440,390]) {
  test(`manual compaction and system refresh preserve chat and draft at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:1000});
    const library=await(await request.get('/api/library')).json(),headers={'X-Grim-Viewer':library.writer_token};
    await request.put('/api/agent/settings',{headers,data:{model:'test-maintenance',system_prompt:'Свежие указания для теста'}});
    const book=await(await request.post('/api/library/create',{headers,data:{title:'Проверка сжатия'}})).json();
    const route=`/api/books/${book.id}/agent`;
    const initial=(await(await request.get(`/api/books/${book.id}`)).json()).revision;
    await mkdir(path.join(book.root,'chapters'),{recursive:true});
    await writeFile(path.join(book.root,'chapters/oscillations.html'),'<p id="definition">Колебание — это изменение состояния.</p>');
    await writeFile(path.join(book.root,'book.json'),JSON.stringify({title:book.title,pages:[{id:'oscillations',title:'Колебания',path:'chapters/oscillations.html'}]}));
    await expect.poll(async()=>(await(await request.get(`/api/books/${book.id}`)).json()).revision).toBeGreaterThan(initial);
    const chat=(await(await request.get(route)).json()).chat.id;
    for(let i=0;i<4;i++) {
      const job_id=crypto.randomUUID();
      expect((await request.post(route+'/jobs',{headers,data:{job_id,chat_id:chat,message:`Вопрос ${i}`,reader_id:'maintenance-test',context:{page_id:'oscillations'}}})).ok()).toBeTruthy();
      await expect.poll(async()=>(await(await request.get(route)).json()).jobs.find((job:{id:string})=>job.id===job_id).status).toBe('completed');
    }
    await page.goto(`/?book=${book.id}`);
    if(width<600)await openReaderTools(page);
    await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
    await expect(page.locator('.agent-turn')).toHaveCount(4);
    await page.getByLabel('Сообщение о текущей книге').fill('Не потерять черновик');
    await page.getByRole('button',{name:'Обновить системные инструкции',exact:true}).click();
    await expect(page.getByRole('status')).toHaveText('Системные инструкции обновлены. Модели ничего не отправлено.');
    expect((await(await request.get(route)).json()).jobs).toHaveLength(4);
    await page.route('**/compact',async route=>{await route.fetch();await route.abort();},{times:1});
    await page.getByRole('button',{name:'Компактизировать чат',exact:true}).click();
    await expect(page.locator('.agent-message').last()).toContainText('Контекст сжат');
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('.agent-turn')).toHaveCount(5);
    await expect(page.getByLabel('Сообщение о текущей книге')).toHaveValue('Не потерять черновик');
    await page.getByRole('button',{name:'Контекст агента',exact:true}).click();
    const sent=JSON.parse(await page.getByLabel('Последний запрос модели',{exact:true}).inputValue());
    expect(sent.tool_choice).toBe('none');
    await page.getByRole('button',{name:'Следующий запрос',exact:true}).click();
    const preview=JSON.parse(await page.getByLabel('Предпросмотр запроса модели',{exact:true}).inputValue());
    expect(preview.messages[0].content).toContain('Свежие указания для теста');
    expect(preview.messages[1].content).toContain('[Previous conversation summary');
    const content=JSON.stringify(preview.messages);
    expect(content).not.toContain('Вопрос 0');expect(content).not.toContain('Вопрос 1');
    expect(content).toContain('Вопрос 2');expect(content).toContain('Вопрос 3');
    expect(content).toContain('Не потерять черновик');
    expect((await(await request.get(route+`/chats/${chat}/archives`,{headers})).json()).archives).toHaveLength(1);
    await page.reload();
    if(width<600)await openReaderTools(page);
    await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
    await expect(page.locator('.agent-turn')).toHaveCount(5);
    await expect(page.locator('.agent-message').last()).toContainText('Контекст сжат');
  });
}

for(const width of [1440,390]) {
  test(`web research opens sources and renders safe clickable citations at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:1000});
    const library=await(await request.get('/api/library')).json(),headers={'X-Grim-Viewer':library.writer_token};
    await request.put('/api/agent/settings',{headers,data:{model:'test-web'}});
    const book=await(await request.post('/api/library/create',{headers,data:{title:'Интернет-источники'}})).json();
    await page.goto(`/?book=${book.id}`);
    if(width<600)await openReaderTools(page);
    await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
    await page.getByLabel('Сообщение о текущей книге').fill('Поищи в интернете и прочитай источник');
    await page.getByRole('button',{name:'Отправить',exact:true}).click();
    const response=page.locator('.agent-message').last();
    await expect(response.getByRole('link',{name:'Источник',exact:true})).toHaveAttribute('href','https://example.org/research');
    await expect(response.getByRole('link',{name:'Статья',exact:true})).toHaveAttribute('href','https://example.org/topic_(term)');
    await expect(response.getByRole('link',{name:'https://example.org/other',exact:true})).toHaveAttribute('rel','noopener noreferrer');
    await expect(response.locator('a')).toHaveCount(3);
    await expect(response.locator('img,script')).toHaveCount(0);
    await expect(response).toContainText('<img src=x');
    const state=await(await request.get(`/api/books/${book.id}/agent`)).json();
    expect(state.jobs[0].events.map((event:{name:string})=>event.name)).toEqual(['web_search','fetch_webpage']);
    await page.getByRole('button',{name:'Контекст агента',exact:true}).click();
    const actual=JSON.parse(await page.getByLabel('Последний запрос модели',{exact:true}).inputValue());
    expect(actual.tools.map((tool:{function:{name:string}})=>tool.function.name)).toEqual(expect.arrayContaining(['web_search','fetch_webpage']));
    expect(JSON.parse(actual.messages.at(-1).content).title).toBe('Источник');
    await page.getByRole('button',{name:'Вернуться к чату',exact:true}).click();
    await page.reload();
    if(width<600)await openReaderTools(page);
    await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
    await expect(page.getByRole('link',{name:'Источник',exact:true})).toHaveAttribute('href','https://example.org/research');
  });
}

test('agent settings save the fingerprint before probing, validate and clear it',async({page,request})=>{
  const pin='ab'.repeat(32), formatted=Array(32).fill('AB').join(':');
  const library=await(await request.get('/api/library')).json();
  const book=await(await request.post('/api/library/create',{headers:{'X-Grim-Viewer':library.writer_token},data:{title:'TLS settings'}})).json();
  await page.goto(`/?book=${book.id}`);
  await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
  if(!await page.getByLabel('Адрес сервера модели').isVisible())await page.getByRole('button',{name:'Настройки агента',exact:true}).click();
  await page.getByLabel('Адрес сервера модели').fill('https://model.test:8090/v1');
  await page.getByLabel('Имя модели',{exact:true}).fill('tls-model');
  await page.getByLabel('Fingerprint сертификата SHA-256').fill(formatted);
  await page.getByLabel('API-токен',{exact:false}).fill('disposable-ui-token');
  let probes=0;
  await page.route('**/api/agent/probe',async route=>{
    const saved=await(await request.get('/api/agent/settings')).json();
    expect(saved.tls_fingerprint).toBe(pin);expect(saved.endpoint).toBe('https://model.test:8090/v1');expect(saved.has_token).toBe(true);
    probes++;
    await route.fulfill({json:{models:['tls-model']}});
  });
  await page.getByRole('button',{name:'Сохранить и проверить',exact:true}).click();
  await expect(page.locator('.agent-notice')).toHaveText('Доступные модели: tls-model');
  expect(probes).toBe(1);
  await expect(page.getByLabel('Fingerprint сертификата SHA-256')).toHaveValue(pin);
  await page.reload();
  await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
  await page.getByRole('button',{name:'Настройки агента',exact:true}).click();
  await expect(page.getByLabel('Fingerprint сертификата SHA-256')).toHaveValue(pin);
  await page.getByLabel('Адрес сервера модели').fill('http://model.test:8090/v1');
  await page.getByRole('button',{name:'Сохранить и проверить',exact:true}).click();
  await expect(page.locator('.agent-panel [role="alert"]')).toContainText('https://');
  expect(probes).toBe(1);
  await page.getByLabel('Fingerprint сертификата SHA-256').fill('wrong');
  await page.getByLabel('Адрес сервера модели').fill('https://model.test:8090/v1');
  await page.getByRole('button',{name:'Сохранить',exact:true}).click();
  await expect(page.locator('.agent-panel [role="alert"]')).toContainText('64');
  await page.getByLabel('Fingerprint сертификата SHA-256').fill('');
  await page.getByRole('button',{name:'Сохранить',exact:true}).click();
  await expect(page.locator('.agent-notice')).toHaveText('Настройки сохранены');
  const saved=await(await request.get('/api/agent/settings')).json();
  expect(saved.tls_fingerprint).toBe('');expect(saved.has_token).toBe(true);
});
