import { writable } from 'svelte/store';

export type ReadingSize = number | 'auto';
const key = 'grim-reading-size';
export const readingSizes = [14, 15, 16, 17, 18, 20, 22, 24];
function valid(value: unknown): ReadingSize {
  const size = Number(value);
  return readingSizes.includes(size) ? size : 'auto';
}
let initial: ReadingSize = 'auto';
try { initial = valid(localStorage.getItem(key)); } catch {}
export const readingSize = writable<ReadingSize>(initial);
export function setReadingSize(value: ReadingSize) {
  const size = valid(value);
  try { localStorage.setItem(key, String(size)); } catch {}
  readingSize.set(size);
}
window.addEventListener('storage', event => {
  if (event.key === key || event.key === null) readingSize.set(valid(event.newValue));
});
