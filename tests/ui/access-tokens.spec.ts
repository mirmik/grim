import { test, expect } from '@playwright/test';

const secret='grim_disposable_UI_test_credential_123456789';
for (const width of [1440,390]) {
  test(`manage device tokens at ${width}px`,async({page,context})=>{
    await page.setViewportSize({width,height:900});
    await context.grantPermissions(['clipboard-read','clipboard-write']);
    let entries=[{id:'legacy',name:'Первоначальный токен',prefix:'',created_at:1700000000,last_used_at:null,revoked_at:null as number|null}];
    await page.route('**/api/library',async route=>{
      const response=await route.fetch();
      await route.fulfill({response,json:{...await response.json(),can_manage_access:true}});
    });
    await page.route('**/api/access-tokens**',async route=>{
      expect(route.request().headers()['x-grim-viewer']).toBeTruthy();
      const method=route.request().method();
      if(method==='POST'){
        const entry={id:'a'.repeat(32),name:route.request().postDataJSON().name,prefix:'grim_disposa',created_at:1700000001,last_used_at:null,revoked_at:null};
        entries=[entry,...entries];
        await route.fulfill({status:201,json:{token:secret,entry}});
      }else if(method==='DELETE'){
        const id=route.request().url().split('/').at(-1);
        entries=entries.map(entry=>entry.id===id?{...entry,revoked_at:1700000002}:entry);
        await route.fulfill({json:{revoked:true}});
      }else await route.fulfill({json:{tokens:entries}});
    });
    await page.goto('/');
    await page.getByRole('button',{name:'Токены доступа',exact:true}).click();
    await page.getByLabel('Название устройства').fill('Основной смартфон');
    await page.getByRole('button',{name:'Создать токен',exact:true}).click();
    await expect(page.getByLabel('Токен для входа')).toHaveValue(secret);
    await page.getByRole('button',{name:'Скопировать токен'}).click();
    await expect(page.getByRole('status')).toHaveText('Токен скопирован');
    expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(secret);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('button',{name:'Закрыть токены доступа'}).click();
    await page.getByRole('button',{name:'Токены доступа',exact:true}).click();
    await expect(page.getByLabel('Токен для входа')).toHaveCount(0);
    const row=page.getByRole('listitem').filter({hasText:'Основной смартфон'});
    await expect(row).toContainText('Действует');
    await row.getByRole('button',{name:'Отозвать: Основной смартфон'}).click();
    await row.getByRole('button',{name:'Отозвать токен',exact:true}).click();
    await expect(row).toContainText('Отозван');
    await expect(row.getByRole('button')).toHaveCount(0);
  });
}

test('ordinary client library does not offer token administration',async({page})=>{
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Открыть книгу'}).first()).toBeVisible();
  await expect(page.getByRole('button',{name:'Токены доступа',exact:true})).toHaveCount(0);
});
