import { test, expect } from '@playwright/test';

test('server address keeps its deployment path and survives relaunch', async ({page}) => {
  await page.route('https://reader.example.test/**', route=>route.fulfill({contentType:'text/html; charset=utf-8',body:'<h1>Серверная библиотека</h1>'}));
  await page.goto('/');
  await page.getByLabel('Адрес сервера').fill('https://reader.example.test/grim?book=123#chapter');
  await page.getByRole('button', {name:'Подключиться',exact:true}).click();
  await expect(page).toHaveURL('https://reader.example.test/grim/');
  await expect(page.getByRole('heading', {name:'Серверная библиотека'})).toBeVisible();
  await page.goto('/');
  await expect(page.getByLabel('Адрес сервера')).toHaveValue('https://reader.example.test/grim/');
  await expect(page.getByRole('button', {name:'Открыть книгу'}).first()).toBeVisible();
});

test('unsupported protocols and credentials are rejected without replacing the saved server', async ({page}) => {
  await page.goto('/');
  for (const address of ['ftp://reader.example.test/grim/', 'https://user:password@reader.example.test/']) {
    await page.getByLabel('Адрес сервера').fill(address);
    await page.getByRole('button', {name:'Подключиться',exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('Используйте HTTP или HTTPS');
    expect(await page.evaluate(()=>localStorage.getItem('grim-server-address'))).toBeNull();
  }
});
