from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/notes")


class NoteIn(BaseModel):
    title: str
    body: str


class Note(NoteIn):
    id: int
    created_at: datetime


NOTES: dict[int, Note] = {}


@router.get("")
def list_notes() -> list[Note]:
    return sorted(NOTES.values(), key=lambda n: n.created_at, reverse=True)


@router.post("", status_code=201)
def create_note(data: NoteIn) -> Note:
    note = Note(id=len(NOTES) + 1, created_at=datetime.now(), **data.model_dump())
    NOTES[note.id] = note
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int) -> Response:
    if NOTES.pop(note_id, None) is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return Response(status_code=204)


@router.get("/search")
def search_notes(q: str) -> list[Note]:
    q = q.lower()
    return [n for n in NOTES.values() if q in n.title.lower() or q in n.body.lower()]
