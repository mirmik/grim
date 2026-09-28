import { test, expect } from '@playwright/test';
import { themeScenarios } from '../theme-scenarios';
themeScenarios();

test('context and agent panels use dark surfaces', async ({page}) => {
  await page.goto('/');
  await page.getByRole('combobox', {name:'Тема оформления'}).selectOption('dark');
  await page.getByRole('button', {name:'Открыть книгу'}).first().click();
  await page.getByRole('button', {name:'Контекст чтения', exact:false}).click();
  await expect(page.locator('.context-panel')).toHaveCSS('background-color', 'rgb(30, 43, 36)');
  await page.getByRole('button', {name:'Чат с агентом'}).click();
  await expect(page.locator('.agent-panel')).toHaveCSS('background-color', 'rgb(30, 43, 36)');
  await expect(page.locator('.agent-panel input, .agent-panel textarea').first()).toHaveCSS('background-color', 'rgb(23, 33, 29)');
});
