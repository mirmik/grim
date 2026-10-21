import { test, expect } from '@playwright/test';
import { openReaderTools } from '../reader-controls';

for(const width of [1440,390]) {
  test(`saved agent answers render readable and safe Markdown at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:1000});
    await page.addInitScript(()=>localStorage.setItem('grim-theme','dark'));
    const errors:string[]=[],remoteImages:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(request.url().includes('should-not-load'))remoteImages.push(request.url());});
    const library=await(await request.get('/api/library')).json(),headers={'X-Grim-Viewer':library.writer_token};
    await request.put('/api/agent/settings',{headers,data:{model:'test-markdown'}});
    const book=await(await request.post('/api/library/create',{headers,data:{title:'Оформление ответов'}})).json();
    const openChat=async()=>{
      if(width<600)await openReaderTools(page);
      await page.getByRole('button',{name:'Чат с агентом',exact:true}).click();
    };
    await page.goto(`/?book=${book.id}`);await openChat();
    await page.getByLabel('Сообщение о текущей книге').fill('Покажи форматирование: **мой исходный текст**');
    await page.getByRole('button',{name:'Отправить',exact:true}).click();
    const markdown=page.locator('.agent-markdown').last();
    await expect(markdown.locator('blockquote strong')).toHaveText('примерно раз в тера тау');
    await expect(markdown.locator('blockquote')).toContainText('концептор создавал гражданина');
    await expect(markdown.locator('em')).toHaveText(['tau','watt']);
    await expect(markdown.locator('p code').first()).toHaveText('translation.md');
    await expect(markdown.locator('p code').first()).toHaveCSS('display','inline');
    await expect(markdown.locator('ul ul li')).toHaveText('сохраняем принятое написание в переводе;');
    await expect(markdown.locator('ol > li')).toHaveCount(2);
    await expect(markdown.getByRole('heading',{level:2})).toHaveText('Проверка оформления');
    await expect(markdown.locator('del')).toHaveText('Прежняя гипотеза');
    await expect(markdown.locator('hr')).toHaveCount(1);
    await expect(markdown.locator('pre code')).toContainText('<p data-example=');
    await expect(markdown.locator('table th')).toHaveCount(5);
    await expect(markdown.getByRole('link',{name:'источник',exact:true})).toHaveAttribute('href','https://example.org/glossary');
    await expect(markdown.getByRole('link',{name:'источник',exact:true})).toHaveAttribute('rel','noopener noreferrer');
    await expect(markdown.locator('img,script,iframe,svg,input,style')).toHaveCount(0);
    await expect(markdown.locator('a[href^="javascript:"],a[href^="data:"]')).toHaveCount(0);
    await expect(page.locator('.agent-turn > p.agent-message')).toContainText('**мой исходный текст**');
    await expect(page.locator('.agent-turn > p.agent-message strong')).toHaveCount(0);
    expect(await page.evaluate(()=>Boolean((window as any).__markdownInjected))).toBe(false);
    expect(remoteImages).toEqual([]);
    expect(await markdown.locator('pre').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
    expect(await markdown.locator('.agent-table').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
    expect(await page.locator('.agent-conversation').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await markdown.locator('blockquote').scrollIntoViewIfNeeded();
    await page.screenshot({path:`/tmp/grim-markdown-after-${width}.png`});
    await page.reload();await openChat();
    await expect(page.locator('.agent-markdown blockquote strong')).toHaveText('примерно раз в тера тау');
    await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
    expect(errors).toEqual([]);
  });
}
