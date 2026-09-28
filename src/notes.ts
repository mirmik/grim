export type NoteAnchor = {
  exact: string;
  prefix: string;
  suffix: string;
  element_id: string;
  block_text: string;
  start: number;
  end: number;
};

export type ReaderNote = {
  id: string;
  page_id: string;
  page_title: string;
  text: string;
  anchor: NoteAnchor;
  created_at: string;
  updated_at: string;
};

const key = (bookId: string) => `grim-notes:${bookId}`;
const string = (value: unknown, limit: number) => typeof value === 'string' ? value.slice(0, limit) : '';

function validAnchor(value: unknown): NoteAnchor | null {
  if (!value || typeof value !== 'object') return null;
  const a = value as Record<string, unknown>;
  if (!Number.isFinite(a.start) || !Number.isFinite(a.end)) return null;
  const anchor = {
    exact: string(a.exact, 12000), prefix: string(a.prefix, 240), suffix: string(a.suffix, 240),
    element_id: string(a.element_id, 300), block_text: string(a.block_text, 24000),
    start: Math.max(0, Number(a.start)), end: Math.max(0, Number(a.end))
  };
  return anchor.exact && anchor.end > anchor.start ? anchor : null;
}

export function noteAnchor(value: unknown): NoteAnchor | null {
  return validAnchor(value);
}

function parseNotes(value: unknown): ReaderNote[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 1000).flatMap((item: unknown) => {
    if (!item || typeof item !== 'object') return [];
    const n = item as Record<string, unknown>, anchor = validAnchor(n.anchor);
    if (!anchor || typeof n.id !== 'string' || typeof n.page_id !== 'string') return [];
    return [{
      id: n.id.slice(0, 100), page_id: n.page_id.slice(0, 200), page_title: string(n.page_title, 300),
      text: string(n.text, 5000), anchor, created_at: string(n.created_at, 40), updated_at: string(n.updated_at, 40)
    }];
  });
}

function localNotes(bookId: string): {notes: ReaderNote[]; raw: string | null} {
  try {
    const raw = localStorage.getItem(key(bookId));
    return {notes: parseNotes(JSON.parse(raw || '[]')), raw};
  } catch { return {notes: [], raw: null}; }
}

export function loadLocalNotes(bookId: string): ReaderNote[] {
  return localNotes(bookId).notes;
}

export function saveLocalNotes(bookId: string, notes: ReaderNote[]) {
  try { localStorage.setItem(key(bookId), JSON.stringify(notes)); } catch {}
}

function mergeNotes(fileNotes: ReaderNote[], legacyNotes: ReaderNote[]): ReaderNote[] {
  const byId = new Map(fileNotes.map(note => [note.id, note]));
  for (const note of legacyNotes) {
    const stored = byId.get(note.id);
    if (!stored || stored.updated_at <= note.updated_at) byId.set(note.id, note);
  }
  const order = [...legacyNotes, ...fileNotes].map(note => note.id);
  return [...new Set(order)].map(id => byId.get(id)!);
}

async function putNotes(bookId: string, token: string, notes: ReaderNote[]) {
  const response = await fetch(`/api/books/${encodeURIComponent(bookId)}/notes`, {
    method: 'PUT', headers: {'Content-Type': 'application/json', 'X-Grim-Viewer': token},
    body: JSON.stringify({version: 1, notes})
  });
  if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось сохранить заметки');
}

function clearLocalIfUnchanged(bookId: string, raw: string | null) {
  if (raw === null) return;
  try { if (localStorage.getItem(key(bookId)) === raw) localStorage.removeItem(key(bookId)); } catch {}
}

export async function loadNotes(bookId: string, token: string): Promise<ReaderNote[]> {
  const response = await fetch(`/api/books/${encodeURIComponent(bookId)}/notes`);
  if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось загрузить заметки');
  const data = await response.json();
  const stored = parseNotes(data?.notes), legacy = localNotes(bookId);
  if (!legacy.notes.length) return stored;
  const merged = mergeNotes(stored, legacy.notes);
  await putNotes(bookId, token, merged);
  clearLocalIfUnchanged(bookId, legacy.raw);
  return merged;
}

export async function saveNotes(bookId: string, token: string, notes: ReaderNote[]) {
  const raw = JSON.stringify(notes);
  try { localStorage.setItem(key(bookId), raw); } catch {}
  await putNotes(bookId, token, notes);
  clearLocalIfUnchanged(bookId, raw);
}
