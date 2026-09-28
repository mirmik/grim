"""Reader notes stored as viewer metadata inside a book directory."""
import json
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator

from .library import atomic_json, safe_file


NOTES_FILE = '.grim-notes.json'


class NoteAnchor(BaseModel):
    exact: str = Field(min_length=1, max_length=12000)
    prefix: str = Field(default='', max_length=240)
    suffix: str = Field(default='', max_length=240)
    element_id: str = Field(default='', max_length=300)
    block_text: str = Field(default='', max_length=24000)
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered_range(self):
        if self.end <= self.start:
            raise ValueError('anchor end must be greater than start')
        return self


class ReaderNote(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    page_id: str = Field(min_length=1, max_length=200)
    page_title: str = Field(default='', max_length=300)
    text: str = Field(default='', max_length=5000)
    anchor: NoteAnchor
    created_at: str = Field(default='', max_length=40)
    updated_at: str = Field(default='', max_length=40)


class NotesDocument(BaseModel):
    version: Literal[1] = 1
    notes: list[ReaderNote] = Field(default_factory=list, max_length=1000)

    @model_validator(mode='after')
    def unique_note_ids(self):
        ids = [note.id for note in self.notes]
        if len(ids) != len(set(ids)):
            raise ValueError('note IDs must be unique')
        return self


def read_notes(root: Path) -> NotesDocument:
    file = root / NOTES_FILE
    if not file.exists():
        return NotesDocument()
    try:
        data = json.loads(safe_file(root, NOTES_FILE).read_text(encoding='utf-8'))
        return NotesDocument.model_validate(data)
    except (json.JSONDecodeError, ValidationError, OSError, HTTPException) as exc:
        raise HTTPException(422, f'Не удалось прочитать {NOTES_FILE}: {exc}') from exc


def write_notes(root: Path, document: NotesDocument):
    try:
        atomic_json(root / NOTES_FILE, document.model_dump(mode='json'))
    except OSError as exc:
        raise HTTPException(422, f'Не удалось записать {NOTES_FILE}: {exc}') from exc
