"""Cache SQLite local pour eviter le re-scan des transcripts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from cctk_core import cache_db

from .parser import UsageEntry
from .pricing import resolve

DEFAULT_DB = cache_db("spend")


class AnomalyAlert(TypedDict):
    """Une session signalee par `detect_anomalies`, avec ses raisons."""

    session_id: str
    project: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read: int
    reasons: list[str]

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    session_id TEXT NOT NULL,
    project TEXT NOT NULL,
    model TEXT NOT NULL,
    ts TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_5m INTEGER NOT NULL,
    cache_creation_1h INTEGER NOT NULL,
    cache_read INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    transcript TEXT NOT NULL,
    line_hash TEXT NOT NULL,
    PRIMARY KEY (transcript, line_hash)
);
CREATE INDEX IF NOT EXISTS idx_usage_project_ts ON usage(project, ts);
CREATE INDEX IF NOT EXISTS idx_usage_model ON usage(model);
CREATE INDEX IF NOT EXISTS idx_usage_session ON usage(session_id);

CREATE TABLE IF NOT EXISTS transcripts (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL
);
"""


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def transcript_needs_rescan(conn: sqlite3.Connection, path: Path) -> bool:
    stat = path.stat()
    row = conn.execute(
        "SELECT mtime, size FROM transcripts WHERE path = ?", (str(path),)
    ).fetchone()
    if row is None:
        return True
    return bool(row[0] != stat.st_mtime or row[1] != stat.st_size)


def mark_transcript(conn: sqlite3.Connection, path: Path) -> None:
    stat = path.stat()
    conn.execute(
        "INSERT OR REPLACE INTO transcripts(path, mtime, size) VALUES (?, ?, ?)",
        (str(path), stat.st_mtime, stat.st_size),
    )


def insert_entries(conn: sqlite3.Connection, entries: Iterable[UsageEntry]) -> int:
    rows = []
    for e in entries:
        # La date de l'entree, pas l'instant du scan : un tarif qui bascule ne
        # doit pas reecrire le cout des mois deja ecoules.
        pricing = resolve(e.model, e.timestamp)
        cost = (
            pricing.cost(
                e.input_tokens,
                e.output_tokens,
                e.cache_creation_5m,
                e.cache_creation_1h,
                e.cache_read,
            )
            if pricing
            else 0.0
        )
        line_hash = f"{e.session_id}:{e.timestamp.isoformat()}:{e.output_tokens}"
        rows.append(
            (
                e.session_id,
                e.project,
                e.model,
                e.timestamp.isoformat(),
                e.input_tokens,
                e.output_tokens,
                e.cache_creation_5m,
                e.cache_creation_1h,
                e.cache_read,
                cost,
                e.transcript_path,
                line_hash,
            )
        )
    conn.executemany(
        """
        INSERT OR IGNORE INTO usage
        (session_id, project, model, ts, input_tokens, output_tokens,
         cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def purge_transcript(conn: sqlite3.Connection, path: Path) -> None:
    conn.execute("DELETE FROM usage WHERE transcript = ?", (str(path),))


def since_to_timestamp(since: str) -> str:
    """Convertit `7d`, `30d`, `24h` en timestamp ISO UTC. Vide -> epoch."""
    if not since:
        return "1970-01-01T00:00:00+00:00"
    unit = since[-1].lower()
    try:
        value = int(since[:-1])
    except ValueError as exc:
        raise ValueError(f"since invalide : {since}") from exc
    delta_map = {"d": "days", "h": "hours", "w": "weeks", "m": "minutes"}
    if unit not in delta_map:
        raise ValueError(f"unite invalide : {unit}")
    delta = timedelta(**{delta_map[unit]: value})
    return (datetime.now(UTC) - delta).isoformat()


def unpriced_models(
    conn: sqlite3.Connection, since: str = "", project: str | None = None
) -> list[tuple[str, int, int]]:
    """Modeles presents dont le tarif est inconnu : `(modele, tokens, entrees)`.

    Un modele absent de la table produit un cout nul. Sans ce recensement, le
    total sous-estime la depense sans le dire — un resultat faux presente comme
    valide. Tout modele publie apres la derniere mise a jour des tarifs tombe
    dans ce cas.
    """
    where = ["ts >= ?"]
    params: list[str] = [since_to_timestamp(since)]
    if project:
        where.append("project = ?")
        params.append(project)
    sql = (
        "SELECT model, SUM(input_tokens + output_tokens + cache_read), COUNT(*)"
        " FROM usage WHERE " + " AND ".join(where) + " GROUP BY model"
    )
    out: list[tuple[str, int, int]] = []
    for model, tokens, entries in conn.execute(sql, params):
        if resolve(model) is None:
            out.append((model, int(tokens or 0), int(entries)))
    out.sort(key=lambda r: r[1], reverse=True)
    return out


def report_rows(
    conn: sqlite3.Connection,
    group_by: str,
    since: str = "",
    project: str | None = None,
    top: int | None = None,
) -> list[tuple[str, int, int, int, float]]:
    """Retourne (key, input, output, cache_read, cost)."""
    valid = {"project", "model", "session"}
    if group_by not in valid:
        raise ValueError(f"group_by doit etre dans {valid}")
    col = {"project": "project", "model": "model", "session": "session_id"}[group_by]
    where = ["ts >= ?"]
    params: list[str] = [since_to_timestamp(since)]
    if project:
        where.append("project = ?")
        params.append(project)
    sql = f"""
        SELECT {col} as k,
               SUM(input_tokens) as i,
               SUM(output_tokens) as o,
               SUM(cache_read) as r,
               SUM(cost_usd) as c
        FROM usage
        WHERE {" AND ".join(where)}
        GROUP BY k
        ORDER BY c DESC
    """
    if top:
        sql += f" LIMIT {int(top)}"
    return list(conn.execute(sql, params))


def daily_rows(
    conn: sqlite3.Connection,
    since: str = "30d",
    project: str | None = None,
) -> list[tuple[str, int, float]]:
    """Retourne (date, nb_entries, cost_usd) par jour, ordre chronologique."""
    where = ["ts >= ?"]
    params: list[str] = [since_to_timestamp(since)]
    if project:
        where.append("project = ?")
        params.append(project)
    sql = f"""
        SELECT substr(ts, 1, 10) as day, COUNT(*) as n, SUM(cost_usd) as c
        FROM usage
        WHERE {" AND ".join(where)}
        GROUP BY day
        ORDER BY day ASC
    """
    return list(conn.execute(sql, params))


def session_costs(
    conn: sqlite3.Connection,
    since: str = "30d",
    project: str | None = None,
) -> list[tuple[str, str, int, int, int, float]]:
    """Par session : (session_id, project, input, output, cache_read, cost).
    Utilise pour detection d'anomalies (calcul mediane cote Python)."""
    where = ["ts >= ?"]
    params: list[str] = [since_to_timestamp(since)]
    if project:
        where.append("project = ?")
        params.append(project)
    sql = f"""
        SELECT session_id, project,
               SUM(input_tokens), SUM(output_tokens),
               SUM(cache_read), SUM(cost_usd)
        FROM usage
        WHERE {" AND ".join(where)}
        GROUP BY session_id
        ORDER BY SUM(cost_usd) DESC
    """
    return list(conn.execute(sql, params))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]


def detect_anomalies(
    conn: sqlite3.Connection,
    since: str = "30d",
    project: str | None = None,
    cost_factor: float = 3.0,
    min_cache_ratio: float = 3.0,
) -> list[AnomalyAlert]:
    """Detecte les sessions en anomalie :
    - cout > cost_factor * mediane du projet
    - ratio cache_read / input_tokens < min_cache_ratio (si input > 0)
    Retourne une liste d'alertes triees par severite (cout decroissant).
    """
    rows = session_costs(conn, since=since, project=project)
    if not rows:
        return []
    # Mediane globale (ou par projet si filtre)
    by_project: dict[str, list[float]] = {}
    for _, proj, *_rest, cost in rows:
        by_project.setdefault(proj, []).append(cost)
    median_by_proj = {p: _median(costs) for p, costs in by_project.items()}

    alerts: list[AnomalyAlert] = []
    for session_id, proj, inp, out, cache, cost in rows:
        reasons: list[str] = []
        median = median_by_proj.get(proj, 0.0)
        if median > 0 and cost > cost_factor * median:
            reasons.append(f"cost {cost_factor:.1f}x mediane projet ({cost:.2f} vs {median:.2f})")
        if inp > 0:
            ratio = cache / inp if inp else 0
            if ratio < min_cache_ratio and cache + inp > 1000:
                reasons.append(f"cache ratio {ratio:.1f} (cible >= {min_cache_ratio})")
        if out > 50_000:
            reasons.append(f"output tokens eleves ({out:,})")
        if reasons:
            alerts.append(
                {
                    "session_id": session_id,
                    "project": proj,
                    "cost_usd": cost,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_read": cache,
                    "reasons": reasons,
                }
            )
    alerts.sort(key=lambda a: a["cost_usd"], reverse=True)
    return alerts
