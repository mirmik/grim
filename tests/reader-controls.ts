import { type Page } from '@playwright/test';

export async function openReaderTools(page: Page) {
  const button = page.getByRole('button', {name:'Настройки и действия'});
  if (await button.getAttribute('aria-expanded') !== 'true') await button.click();
}

export async function selectTheme(page: Page, theme: string) {
  const picker = page.getByRole('combobox', {name:'Тема оформления'});
  const hidden = !await picker.isVisible();
  if (hidden) await openReaderTools(page);
  await picker.selectOption(theme);
  if (hidden) await page.getByRole('button', {name:'Настройки и действия'}).click();
}
