import { cp, mkdir, readFile, readdir, writeFile, lstat } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(project, 'dist-android');
const demoId = createHash('sha256').update('grim:demo').digest('hex').slice(0, 32);
const books = [{id: demoId, root: path.join(project, 'demo')}, ...JSON.parse(process.env.GRIM_ANDROID_BOOKS || '[]')];
const bookPolicy = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'";
const injection = `<meta http-equiv="Content-Security-Policy" content="${bookPolicy}"><script src="/bridge.js"></script>`;

// Reject symlinks instead of accidentally packaging files outside the book.
async function copyBook(source, target) {
  if ((await lstat(source)).isSymbolicLink()) throw new Error(`Symlink in book: ${source}`);
  await mkdir(target, {recursive: true});
  for (const entry of await readdir(source, {withFileTypes: true})) {
    if (entry.name.startsWith('.') || ['node_modules', '__pycache__'].includes(entry.name) || entry.name.endsWith('.tmp')) continue;
    if (entry.isSymbolicLink()) throw new Error(`Symlink in book: ${path.join(source, entry.name)}`);
    if (/[?#\\]/.test(entry.name)) throw new Error(`Unsupported asset filename: ${entry.name}`);
    const from = path.join(source, entry.name), to = path.join(target, entry.name);
    if (entry.isDirectory()) await copyBook(from, to);
    else if (entry.isFile()) {
      if (/\.html?$/i.test(entry.name)) {
        const html = await readFile(from, 'utf8');
        // Policy and bridge precede book scripts, just as on the live server.
        const packed = /<head\b[^>]*>/i.test(html)
          ? html.replace(/<head\b[^>]*>/i, head => head + injection)
          : injection + html;
        await writeFile(to, packed);
      } else await cp(from, to);
    }
  }
}

async function validateManifest(manifest, root) {
  if (typeof manifest.title !== 'string' || !manifest.title.trim()) throw new Error('Book title required');
  const seen = new Set();
  let pageCount = 0;
  async function visit(nodes) {
    if (!Array.isArray(nodes)) throw new Error('pages/children must be arrays');
    for (const node of nodes) {
      if (!node || typeof node.id !== 'string' || !node.id || seen.has(node.id) || typeof node.title !== 'string') throw new Error('Invalid or duplicate page ID/title');
      seen.add(node.id);
      if ('path' in node) {
        const p = node.path;
        if (typeof p !== 'string' || path.posix.isAbsolute(p) || /[?#\\]/.test(p) || p.split('/').some(part => !part || part === '..' || part.startsWith('.')) || !/\.html?$/i.test(p)) throw new Error(`Invalid page path: ${p}`);
        if (!(await lstat(path.join(root, p))).isFile()) throw new Error(`Missing HTML page: ${p}`);
        pageCount++;
      }
      await visit(node.children ?? []);
    }
  }
  await visit(manifest.pages);
  return pageCount;
}

await mkdir(path.join(output, 'offline/books'), {recursive: true});
await cp(path.join(project, 'server/bridge.js'), path.join(output, 'bridge.js'));
await cp(path.join(project, 'node_modules/katex/dist'), path.join(output, 'vendor'), {recursive: true});
const entries = [], seen = new Set();
for (const entry of books) {
  if (!/^[a-f0-9]{32}$/.test(entry.id) || seen.has(entry.id) || typeof entry.root !== 'string') throw new Error('Books require unique 32-hex IDs and root paths');
  seen.add(entry.id);
  const root = path.resolve(entry.root);
  const manifest = JSON.parse(await readFile(path.join(root, 'book.json'), 'utf8'));
  const pageCount = await validateManifest(manifest, root);
  await copyBook(root, path.join(output, 'book', entry.id));
  // Never ship host filesystem paths or the server's ephemeral writer token.
  const metadata = {id: entry.id, title: manifest.title, subtitle: manifest.subtitle || '', pages: manifest.pages, root: '', revision: 0};
  await writeFile(path.join(output, 'offline/books', `${entry.id}.json`), JSON.stringify(metadata));
  entries.push({id: entry.id, title: metadata.title, subtitle: metadata.subtitle, root: '', page_count: pageCount, error: null});
}
await writeFile(path.join(output, 'offline/library.json'), JSON.stringify({books: entries}));
console.log(`Bundled ${entries.length} offline book(s): ${entries.map(book => book.title).join(', ')}`);
