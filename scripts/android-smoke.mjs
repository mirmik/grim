// Run against an installed debug APK and a running emulator. No driver APK needed.
import { _android as android } from 'playwright';
import { expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const devices = await android.devices({omitDriverInstall: true});
const serial = process.env.ANDROID_SERIAL || 'emulator-5554';
const device = devices.find(candidate => candidate.serial() === serial);
if (!device) throw new Error(`Android device ${serial} unavailable`);
const pkg = 'dev.mirmik.grim';
await mkdir('test-results/android-native', {recursive: true});
async function launch() {
  await device.shell(`am start -n ${pkg}/.MainActivity`);
  return (await device.webView({pkg}, {timeout: 15000})).page();
}

try {
  await device.shell(`am force-stop ${pkg}`);
  let page = await launch();
  await page.goto('http://tauri.localhost/');
  await page.locator('.book-card').filter({hasText: 'Математика движения'}).getByRole('button', {name: 'Открыть книгу'}).click();
  let frame = page.frameLocator('iframe');
  await expect(frame.locator('.katex')).toBeAttached();
  await frame.locator('body').evaluate(() => document.fonts.ready.then(() => undefined));
  expect(await frame.locator('body').evaluate(() => [...document.fonts].filter(font => font.status === 'error').map(font => font.family))).toEqual([]);
  await frame.locator('#definition').evaluate(el => {
    el.scrollIntoView();const range = document.createRange();range.selectNodeContents(el);
    getSelection().removeAllRanges();getSelection().addRange(range);
  });
  await page.getByRole('button', {name: 'Фрагмент'}).click();
  await expect(page.locator('.context-panel blockquote')).toContainText('Колебание');
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.locator('.context-panel')).toHaveCount(0);
  await expect(page.locator('iframe')).toBeVisible();
  await page.getByRole('button', {name: 'Оглавление', exact: true}).click();
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.locator('aside')).not.toBeVisible();
  // Fully restart the Android process, not just reload the DOM.
  await device.shell(`am force-stop ${pkg}`);
  page = await launch();
  await page.locator('.book-card').filter({hasText: 'Математика движения'}).getByRole('button', {name: 'Открыть книгу'}).click();
  frame = page.frameLocator('iframe');
  await expect(frame.locator('#definition')).toBeInViewport();
  await frame.getByRole('link', {name: 'измените волну в лаборатории →'}).click();
  await frame.locator('#amplitude').fill('1.8');
  await expect(frame.locator('#a-value')).toHaveText('1.8');
  await page.screenshot({path: 'test-results/android-native/laboratory.png'});
  const isolation = await frame.locator('body').evaluate(async () => {
    let parentAccess = false, networkAccess = false;
    try {void parent.document.body;parentAccess = true;} catch {}
    try {await fetch('/offline/library.json');networkAccess = true;} catch {}
    return {parentAccess, networkAccess, origin: window.origin};
  });
  expect(isolation).toEqual({parentAccess: false, networkAccess: false, origin: 'null'});
  await device.shell('input keyevent KEYCODE_BACK');
  await expect(page.locator('.book-card').first()).toBeVisible();
  await page.screenshot({path: 'test-results/android-native/library.png'});
  console.log('Android smoke passed: local fonts, selection, cold restart, interactive lab, sandbox, native Back.');
} finally {
  await device.close();
}
