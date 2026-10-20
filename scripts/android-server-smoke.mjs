// Requires a disposable Grim server on host port 8001 and an installed debug APK.
import { _android as android } from 'playwright';
import { expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const device = (await android.devices({omitDriverInstall:true})).find(item=>item.serial()===(process.env.ANDROID_SERIAL||'emulator-5554'));
if (!device) throw new Error('Android emulator unavailable');
const pkg='dev.mirmik.grim', server='http://127.0.0.1:8001/';
await mkdir('test-results/android-native', {recursive:true});
async function launch() {
  await device.shell(`am start -n ${pkg}/.MainActivity`);
  return (await device.webView({pkg}, {timeout:15000})).page();
}
try {
  await device.shell(`am force-stop ${pkg}`);
  let page=await launch();
  await page.goto('http://tauri.localhost/');
  await page.getByLabel('Адрес сервера').fill(server);
  await page.getByRole('button', {name:'Подключиться',exact:true}).click();
  await expect(page).toHaveURL(server);
  await expect(page.getByRole('button', {name:'Импорт EPUB',exact:true})).toBeVisible();
  await page.getByRole('button', {name:'Открыть книгу'}).first().click();
  let frame=page.frameLocator('iframe');
  await expect(frame.locator('.katex')).toBeAttached();
  await frame.locator('#definition').evaluate(el=>el.scrollIntoView());
  await expect.poll(()=>page.evaluate(async()=>{
    const {context}=await (await fetch('/api/context')).json();
    return context?.visible_text;
  })).toContain('Колебание');
  await page.getByRole('button', {name:'Настройки и действия'}).click();
  await page.getByRole('button', {name:'Чат с агентом',exact:true}).click();
  await expect(page.locator('.agent-panel')).toBeVisible();
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.locator('.agent-panel')).toHaveCount(0);
  await expect(page.locator('iframe')).toBeVisible();
  // The same-origin server view can use its API, but its books remain isolated.
  expect(await frame.locator('body').evaluate(()=>{
    try { void parent.document.body;return true; } catch { return false; }
  })).toBe(false);
  expect(await page.evaluate(async()=>{
    const api=window.__TAURI_INTERNALS__;
    if (!api) return false;
    try { await api.invoke('plugin:app|version');return true; } catch { return false; }
  })).toBe(false);
  await page.screenshot({path:'test-results/android-native/server-reader.png'});
  await device.shell(`am force-stop ${pkg}`);
  page=await launch();
  await expect(page.getByLabel('Адрес сервера')).toHaveValue(server);
  await page.getByRole('button', {name:'Подключиться',exact:true}).click();
  await page.getByRole('button', {name:'Открыть книгу'}).first().click();
  frame=page.frameLocator('iframe');
  await expect(frame.locator('#definition')).toBeInViewport();
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.locator('.book-card').first()).toBeVisible();
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page).toHaveURL('http://tauri.localhost/');
  await expect(page.getByLabel('Адрес сервера')).toHaveValue(server);
  // Failed connections must still offer a way back to the editable address.
  await page.getByLabel('Адрес сервера').fill('http://127.0.0.1:1/');
  await page.getByRole('button', {name:'Подключиться',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>location.href)).not.toContain('tauri.localhost');
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.getByLabel('Адрес сервера')).toBeVisible();
  await page.getByLabel('Адрес сервера').fill(server);
  await page.screenshot({path:'test-results/android-native/connection.png'});
  console.log('Android server smoke passed: connection, live library, context, chat, sandbox, no native IPC, cold restart, saved position, Back and connection failure recovery.');
} finally { await device.close(); }
// Playwright's shared Android transport may keep discovery sockets alive.
process.exit(0);
