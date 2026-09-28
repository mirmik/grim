// Both shells use the same reader. Android reads an immutable, bundled snapshot;
// the desktop viewer reads the live library served by Python.
export const offline = import.meta.env.MODE === 'android';
// The live viewer may be reverse-proxied below a path such as /grim/.
// Keep browser history and brand links at the path where the app was opened.
export const appPath = offline ? '/' : location.pathname.endsWith('/') ? location.pathname : location.pathname + '/';

export function fetchLibrary(): Promise<Response> {
  return fetch(offline ? '/offline/library.json' : '/api/library');
}

export function fetchBook(id: string): Promise<Response> {
  return fetch(offline ? `/offline/books/${encodeURIComponent(id)}.json` : `/api/books/${encodeURIComponent(id)}`);
}
