"""Minimal agent memory service: store facts, search them with decayed ranking."""

import math
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("MEMORY_DB", Path(__file__).with_name("memories.db")))

ASCII_TOKEN = re.compile(r"[a-z0-9_]{2,}")
CHINESE = re.compile(r"[\u4e00-\u9fff]")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    importance: int = Field(default=3, ge=1, le=5)


class MemoryOut(BaseModel):
    id: int
    content: str
    tags: list[str]
    importance: int
    created_at: str
    use_count: int


class SearchHit(MemoryOut):
    score: float


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                importance INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                use_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)")


def tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = ASCII_TOKEN.findall(lowered)
    chars = CHINESE.findall(lowered)
    bigrams = ["".join(pair) for pair in zip(chars, chars[1:])] if len(chars) > 1 else chars
    return list(dict.fromkeys(words + bigrams))


def row_to_memory(row: sqlite3.Row) -> MemoryOut:
    return MemoryOut(
        id=row["id"],
        content=row["content"],
        tags=[t for t in row["tags"].split(",") if t],
        importance=row["importance"],
        created_at=row["created_at"],
        use_count=row["use_count"],
    )


def score_memory(row: sqlite3.Row, query_tokens: list[str], now: datetime) -> float:
    content = row["content"].lower()
    tag_set = {t.lower() for t in row["tags"].split(",") if t}
    hits = sum(1.0 for token in query_tokens if token in content)
    hits += sum(1.5 for token in query_tokens if token in tag_set)
    if hits == 0:
        return 0.0
    created = datetime.fromisoformat(row["created_at"])
    age_days = max((now - created).total_seconds() / 86400, 0)
    recency = math.exp(-age_days / 30)
    # Relevance dominates, importance is a multiplier, recency is a tie-breaker.
    return round(hits * (1 + row["importance"] / 5) * (1 + 0.3 * recency), 3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Agent Memory Mini", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "db": str(DB_PATH.name)}


@app.post("/memories", response_model=MemoryOut, status_code=201)
def create_memory(payload: MemoryIn, db: Db):
    now = datetime.now(timezone.utc).isoformat()
    clean_tags = [t.strip().lower() for t in payload.tags if t.strip()]
    cursor = db.execute(
        "INSERT INTO memories (content, tags, importance, created_at) VALUES (?, ?, ?, ?)",
        (payload.content.strip(), ",".join(clean_tags), payload.importance, now),
    )
    db.commit()
    row = db.execute("SELECT * FROM memories WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_memory(row)


@app.get("/memories", response_model=list[MemoryOut])
def list_memories(db: Db, limit: int = Query(default=20, ge=1, le=100)):
    rows = db.execute(
        "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [row_to_memory(row) for row in rows]


@app.get("/memories/search", response_model=list[SearchHit])
def search_memories(
    db: Db,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=5, ge=1, le=20),
):
    query_tokens = tokens(q)
    if not query_tokens:
        raise HTTPException(status_code=400, detail="query has no searchable token")
    now = datetime.now(timezone.utc)
    rows = db.execute("SELECT * FROM memories").fetchall()
    scored = []
    for row in rows:
        score = score_memory(row, query_tokens, now)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:limit]
    if top:
        db.executemany(
            "UPDATE memories SET last_used_at = ?, use_count = use_count + 1 WHERE id = ?",
            [(now.isoformat(), row["id"]) for _, row in top],
        )
        db.commit()
        ids = [row["id"] for _, row in top]
        placeholders = ",".join("?" for _ in ids)
        fresh = {
            row["id"]: row
            for row in db.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})", ids
            ).fetchall()
        }
        top = [(score, fresh[row["id"]]) for score, row in top]
    return [
        SearchHit(**row_to_memory(row).model_dump(), score=score)
        for score, row in top
    ]
