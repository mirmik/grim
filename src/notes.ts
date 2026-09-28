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

export function loadNotes(bookId: string): ReaderNote[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(key(bookId)) || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, 1000).flatMap((value: unknown) => {
      if (!value || typeof value !== 'object') return [];
      const n = value as Record<string, unknown>, anchor = validAnchor(n.anchor);
      if (!anchor || typeof n.id !== 'string' || typeof n.page_id !== 'string') return [];
      return [{
        id: n.id.slice(0, 100), page_id: n.page_id.slice(0, 200), page_title: string(n.page_title, 300),
        text: string(n.text, 5000), anchor, created_at: string(n.created_at, 40), updated_at: string(n.updated_at, 40)
      }];
    });
  } catch { return []; }
}

export function saveNotes(bookId: string, notes: ReaderNote[]) {
  try { localStorage.setItem(key(bookId), JSON.stringify(notes)); } catch {}
}
