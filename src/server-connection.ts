export function normalizeServerAddress(value: string): string {
  let url: URL;
  try { url = new URL(value.trim()); }
  catch { throw new Error('Укажите полный адрес сервера, начиная с http:// или https://.'); }
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) {
    throw new Error('Используйте HTTP или HTTPS адрес сервера без логина и пароля в адресе.');
  }
  // A copied reader link may include a book ID. Connect to its library instead;
  // preserve the deployment path, including a reverse proxy's /grim/ prefix.
  url.search = ''; url.hash = '';
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  return url.href;
}
