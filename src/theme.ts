import { writable } from 'svelte/store';

export type ThemePreference = 'system' | 'light' | 'dark';
export type Theme = 'light' | 'dark';
const storageKey = 'grim-theme';
const system = window.matchMedia('(prefers-color-scheme: dark)');
const valid = (value: unknown): ThemePreference => value === 'light' || value === 'dark' ? value : 'system';
let preference: ThemePreference = 'system';
try { preference = valid(localStorage.getItem(storageKey)); } catch {}

export const themePreference = writable<ThemePreference>(preference);
export const resolvedTheme = writable<Theme>('light');

function apply() {
  const theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#17211d' : '#183c32');
  resolvedTheme.set(theme);
}

export function setTheme(value: ThemePreference) {
  preference = valid(value);
  try { localStorage.setItem(storageKey, preference); } catch {}
  themePreference.set(preference);
  apply();
}

system.addEventListener('change', apply);
window.addEventListener('storage', event => {
  if (event.key !== storageKey && event.key !== null) return;
  preference = valid(event.newValue);
  themePreference.set(preference);
  apply();
});
apply();
