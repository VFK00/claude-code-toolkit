"""Emplacement des caches SQLite locaux."""

from __future__ import annotations

from pathlib import Path


def cache_db(name: str, home: Path | None = None) -> Path:
    """Chemin du cache SQLite `cctk-<name>.db`, dossier parent cree au besoin."""
    root = home if home is not None else Path.home()
    cache_dir = root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"cctk-{name}.db"
