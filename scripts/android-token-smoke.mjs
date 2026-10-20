// Read-only smoke against a real HTTPS library; never put the token in argv.
import { _android as android } from 'playwright';
import { expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const pkg = 'dev.mirmik.grim';
const server = new URL(process.env.GRIM_TEST_SERVER || 'https://192.168.0.61:8444/');
if (server.protocol !== 'https:' || server.username || server.password || server.search || server.hash) {
  throw new Error('GRIM_TEST_SERVER must be an HTTPS URL without credentials, query or fragment');
}
const device = (await android.devices({ omitDriverInstall: true }))
  .find(item => item.serial() === process.env.ANDROID_SERIAL);
if (!device) throw new Error('Set ANDROID_SERIAL to an attached debug device');
let stage = 'launch', failed = false;
async function launch() {
  stage = 'start Android activity';
  await device.shell(`am start -n ${pkg}/.MainActivity`);
  stage = 'attach Android WebView';
  return (await device.webView({ pkg }, { timeout: 15000 })).page();
}
try {
  await device.shell(`am force-stop ${pkg}`);
  let page = await launch();
  stage = 'open bundled launcher';
  await page.goto('http://tauri.localhost/');
  stage = 'set server address';
  await page.getByLabel('Адрес сервера').fill(server.href);
  stage = 'navigate to HTTPS server';
  await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  stage = 'HTTPS and token login';
  await expect(page.locator('#access-token, .book-card').first()).toBeVisible({ timeout: 20000 });
  if (await page.locator('#access-token').count()) {
    if (!process.env.GRIM_TEST_TOKEN_FILE) throw new Error('Set GRIM_TEST_TOKEN_FILE');
    const token = (await readFile(process.env.GRIM_TEST_TOKEN_FILE, 'utf8')).trim();
    await page.getByLabel('Токен доступа').fill(token);
    await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  }
  await expect(page.locator('.book-card').first()).toBeVisible();
  const cookie = (await page.context().cookies(server.href)).find(item => item.name === 'grim-mobile-session');
  expect(Boolean(cookie?.secure && cookie?.httpOnly && cookie?.sameSite === 'Lax')).toBe(true);
  stage = 'book and sandbox';
  await page.getByRole('button', { name: 'Открыть книгу' }).first().click();
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('body')).toBeVisible();
  expect(await frame.locator('body').evaluate(() => {
    try { void parent.document.body; return true; } catch { return false; }
  })).toBe(false);
  stage = 'cold restart';
  await device.shell(`am force-stop ${pkg}`);
  page = await launch();
  await expect(page.getByLabel('Адрес сервера')).toHaveValue(server.href);
  await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  await expect(page.locator('.book-card').first()).toBeVisible({ timeout: 20000 });
  console.log('Android HTTPS/token smoke passed: library, protected cookie, book isolation and login retained after hard restart.');
} catch (error) {
  // Playwright call logs may include filled secrets: report only the stage/type.
  console.error(`Android token smoke failed at ${stage}: ${error.name}`);
  failed = true;
} finally {
  await device.close();
}
process.exit(failed ? 1 : 0);
