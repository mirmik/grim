// Both shells use the same reader. Android reads an immutable, bundled snapshot;
// the desktop viewer reads the live library served by Python.
export const offline = import.meta.env.MODE === 'android';

export function fetchLibrary(): Promise<Response> {
  return fetch(offline ? '/offline/library.json' : '/api/library');
}

export function fetchBook(id: string): Promise<Response> {
  return fetch(offline ? `/offline/books/${encodeURIComponent(id)}.json` : `/api/books/${encodeURIComponent(id)}`);
}
