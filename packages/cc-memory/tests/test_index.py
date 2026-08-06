import os
from pathlib import Path

import pytest

from memory_search.index import connect, load_all, prune, stats, upsert
from memory_search.loader import iter_memory


@pytest.fixture(autouse=True)
def _workspace_declare(monkeypatch):
    """Les fixtures de ce module simulent un poste groupant ses projets sous
    `Claude/projets`. Le workspace se declare, il ne se devine plus."""
    monkeypatch.setenv("CCTK_WORKSPACE", "Claude/projets")


FIXTURES = Path(__file__).parent / "fixtures" / "sample_projects"


def test_upsert_and_load(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    entries = list(iter_memory(FIXTURES))
    for e in entries:
        upsert(conn, e, embedding=None, mtime=os.path.getmtime(e.path))
    loaded = load_all(conn)
    assert len(loaded) == len(entries)


def test_upsert_with_embedding(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    entries = list(iter_memory(FIXTURES))[:1]
    upsert(conn, entries[0], embedding=[0.1, 0.2, 0.3], mtime=1.0)
    loaded = load_all(conn)
    assert loaded[0][1] == [0.1, 0.2, 0.3]


def test_upsert_is_idempotent(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    entries = list(iter_memory(FIXTURES))[:1]
    upsert(conn, entries[0], None, 1.0)
    upsert(conn, entries[0], None, 2.0)
    loaded = load_all(conn)
    assert len(loaded) == 1


def test_load_all_filter_by_project(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, os.path.getmtime(e.path))
    alpha_only = load_all(conn, project="alpha")
    assert all(e.project == "alpha" for e, _ in alpha_only)
    assert len(alpha_only) >= 2


def test_load_all_filter_by_type(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, os.path.getmtime(e.path))
    feedbacks = load_all(conn, type_="feedback")
    assert all(e.type == "feedback" for e, _ in feedbacks)


def test_stats(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, os.path.getmtime(e.path))
    s = stats(conn)
    assert s["total"] >= 3
    assert any(k.startswith("project:") for k in s)
    assert any(k.startswith("type:") for k in s)


def test_stale_entries_none(tmp_path):
    from memory_search.index import stale_entries

    conn = connect(tmp_path / "db.sqlite")
    import time

    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, time.time())  # mtime = maintenant
    results = stale_entries(conn, older_than_days=1)
    assert results == []


def test_stale_entries_old(tmp_path):
    from memory_search.index import stale_entries

    conn = connect(tmp_path / "db.sqlite")
    import time

    very_old = time.time() - (200 * 86400)  # 200 jours
    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, very_old)
    results = stale_entries(conn, older_than_days=90)
    assert len(results) >= 3
    # Tri par age decroissant (plus vieux en premier)
    ages = [age for _, _, age in results]
    assert all(a >= 90 for a in ages)


def test_stale_entries_filter_project(tmp_path):
    from memory_search.index import stale_entries

    conn = connect(tmp_path / "db.sqlite")
    import time

    old = time.time() - (200 * 86400)
    for e in iter_memory(FIXTURES):
        upsert(conn, e, None, old)
    filtered = stale_entries(conn, older_than_days=90, project="alpha")
    assert all(e.project == "alpha" for e, _, _ in filtered)


def test_stale_entries_mixed(tmp_path):
    from memory_search.index import stale_entries

    conn = connect(tmp_path / "db.sqlite")
    import time

    entries = list(iter_memory(FIXTURES))
    # Premiere = recente, les autres = vieilles
    upsert(conn, entries[0], None, time.time())
    for e in entries[1:]:
        upsert(conn, e, None, time.time() - (100 * 86400))
    results = stale_entries(conn, older_than_days=50)
    assert len(results) == len(entries) - 1


def test_stale_entries_mtime_zero_ignored(tmp_path):
    """Les entries avec mtime=0 (jamais loaded correctement) doivent etre ignorees."""
    from memory_search.index import stale_entries

    conn = connect(tmp_path / "db.sqlite")
    entries = list(iter_memory(FIXTURES))
    upsert(conn, entries[0], None, 0)
    results = stale_entries(conn, older_than_days=1)
    assert results == []


# --- Elagage : l'index ne doit pas conserver ce qui a disparu ---


def _seed(conn, path, project="p"):
    from memory_search.loader import MemoryEntry
    upsert(conn, MemoryEntry(path=path, project=project, slug="s"), None, 1.0)
    conn.commit()


def test_prune_retire_les_entrees_disparues(tmp_path):
    """`upsert` n'ajoute que : sans elagage l'index ne fait que grossir.

    Mesure du 2026-08-06 : 141 entrees pour 57 fichiers reels.
    """
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn, "/base/a.md")
    _seed(conn, "/base/disparu.md")

    removed = prune(conn, seen={"/base/a.md"}, base="/base")

    assert removed == 1
    assert [e.path for e, _ in load_all(conn)] == ["/base/a.md"]


def test_prune_borne_au_sous_arbre(tmp_path):
    """Indexer un projet ne doit pas effacer l'index des autres."""
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn, "/projet-a/x.md")
    _seed(conn, "/projet-b/y.md")

    removed = prune(conn, seen={"/projet-a/x.md"}, base="/projet-a")

    assert removed == 0
    assert {e.path for e, _ in load_all(conn)} == {"/projet-a/x.md", "/projet-b/y.md"}


def test_prune_sans_base_elague_tout(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn, "/x/a.md")
    _seed(conn, "/y/b.md")

    assert prune(conn, seen={"/x/a.md"}) == 1
    assert [e.path for e, _ in load_all(conn)] == ["/x/a.md"]


def test_prune_index_deja_propre(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    _seed(conn, "/base/a.md")

    assert prune(conn, seen={"/base/a.md"}, base="/base") == 0
