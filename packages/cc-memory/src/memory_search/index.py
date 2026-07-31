"""Index SQLite : metadata + embeddings serialises."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cctk_core import cache_db

from .loader import MemoryEntry

DEFAULT_DB = cache_db("memory")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    path TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT,
    description TEXT,
    type TEXT,
    body TEXT,
    embedding TEXT,
    mtime REAL
);
CREATE INDEX IF NOT EXISTS idx_memory_project ON memory(project);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);
"""


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def upsert(
    conn: sqlite3.Connection,
    entry: MemoryEntry,
    embedding: list[float] | None,
    mtime: float,
) -> None:
    conn.execute(
        """
        INSERT INTO memory(path, project, slug, name, description, type, body, embedding, mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            project=excluded.project,
            slug=excluded.slug,
            name=excluded.name,
            description=excluded.description,
            type=excluded.type,
            body=excluded.body,
            embedding=excluded.embedding,
            mtime=excluded.mtime
        """,
        (
            entry.path,
            entry.project,
            entry.slug,
            entry.name,
            entry.description,
            entry.type,
            entry.body,
            json.dumps(embedding) if embedding is not None else None,
            mtime,
        ),
    )


def load_all(
    conn: sqlite3.Connection,
    project: str | None = None,
    type_: str | None = None,
) -> list[tuple[MemoryEntry, list[float] | None]]:
    where = []
    params: list[str] = []
    if project:
        where.append("project = ?")
        params.append(project)
    if type_:
        where.append("type = ?")
        params.append(type_)
    sql = "SELECT path, project, slug, name, description, type, body, embedding FROM memory"
    if where:
        sql += " WHERE " + " AND ".join(where)
    out: list[tuple[MemoryEntry, list[float] | None]] = []
    for row in conn.execute(sql, params):
        entry = MemoryEntry(
            path=row[0],
            project=row[1],
            slug=row[2],
            name=row[3] or "",
            description=row[4] or "",
            type=row[5] or "unknown",
            body=row[6] or "",
        )
        emb = json.loads(row[7]) if row[7] else None
        out.append((entry, emb))
    return out


def stale_entries(
    conn: sqlite3.Connection,
    older_than_days: int = 90,
    project: str | None = None,
    type_: str | None = None,
) -> list[tuple[MemoryEntry, float, int]]:
    """Retourne entries (entry, mtime, age_days) modifiees il y a plus de `older_than_days`.

    Tri par age decroissant (plus vieux en premier).
    """
    import time

    now = time.time()
    cutoff = now - (older_than_days * 86400)
    where = ["mtime < ?", "mtime > 0"]
    params: list[str | float] = [cutoff]
    if project:
        where.append("project = ?")
        params.append(project)
    if type_:
        where.append("type = ?")
        params.append(type_)
    sql = (
        "SELECT path, project, slug, name, description, type, body, mtime FROM memory"
        " WHERE " + " AND ".join(where) + " ORDER BY mtime ASC"
    )
    results: list[tuple[MemoryEntry, float, int]] = []
    for row in conn.execute(sql, params):
        entry = MemoryEntry(
            path=row[0],
            project=row[1],
            slug=row[2],
            name=row[3] or "",
            description=row[4] or "",
            type=row[5] or "unknown",
            body=row[6] or "",
        )
        mtime = row[7]
        age_days = int((now - mtime) / 86400)
        results.append((entry, mtime, age_days))
    return results


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    total = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    out["total"] = total
    for type_, n in conn.execute("SELECT type, COUNT(*) FROM memory GROUP BY type"):
        out[f"type:{type_}"] = n
    for project, n in conn.execute("SELECT project, COUNT(*) FROM memory GROUP BY project"):
        out[f"project:{project}"] = n
    return out
