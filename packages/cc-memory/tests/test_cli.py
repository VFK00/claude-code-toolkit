import os
import shutil
import time
from pathlib import Path

import pytest

from memory_search.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "sample_projects"


def test_cli_index_no_embed(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    rc = main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    assert rc == 0
    assert "indexe" in capsys.readouterr().out


def test_cli_index_missing_base(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "db.sqlite"), "index", "--base", "/nope"])
    assert rc == 1


def test_cli_index_empty_base(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = main(["--db", str(tmp_path / "db.sqlite"), "--no-embed", "index", "--base", str(empty)])
    assert rc == 0
    assert "No memory file found" in capsys.readouterr().out


def _memory_dir(tmp_path: Path) -> Path:
    home_prefix = str(Path.home()).rstrip("/").replace("/", "-")
    memory = tmp_path / "base" / f"{home_prefix}-Claude-projets-alpha" / "memory"
    memory.mkdir(parents=True)
    return memory


def test_cli_index_fichier_casse_non_fatal(tmp_path, capsys):
    """Defaut 3 : un frontmatter non-mapping annulait l'indexation complete."""
    import sqlite3

    memory = _memory_dir(tmp_path)
    (memory / "ok1.md").write_text("---\nname: A\n---\nbody")
    (memory / "casse.md").write_text("---\n- foo\n- bar\n---\nCorps.")
    (memory / "boucle.md").symlink_to("boucle.md")
    (memory / "ok2.md").write_text("---\nname: B\n---\nbody")
    db = tmp_path / "db.sqlite"

    rc = main(["--db", str(db), "--no-embed", "index", "--base", str(tmp_path / "base")])

    assert rc == 0
    out = capsys.readouterr().out
    assert "discarded" in out.lower()
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0] == 3
    conn.close()


def test_cli_index_commit_incremental(tmp_path, monkeypatch, capsys):
    """C3 : l'indexation deja faite ne doit pas dependre de la fin du run."""
    import sqlite3

    from memory_search import cli as cli_mod

    memory = _memory_dir(tmp_path)
    (memory / "a.md").write_text("---\nname: A\n---\nbody")
    (memory / "b.md").write_text("---\nname: B\n---\nbody")
    db = tmp_path / "db.sqlite"

    vus: list[int] = []
    vrai_upsert = cli_mod.upsert

    def espion(conn, entry, emb, mtime):
        temoin = sqlite3.connect(db)
        vus.append(temoin.execute("SELECT COUNT(*) FROM memory").fetchone()[0])
        temoin.close()
        return vrai_upsert(conn, entry, emb, mtime)

    monkeypatch.setattr(cli_mod, "upsert", espion)
    rc = main(["--db", str(db), "--no-embed", "index", "--base", str(tmp_path / "base")])

    assert rc == 0
    assert vus == [0, 1], "la 1re entree doit etre committee avant la 2e"


def test_cli_query_nf525(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    capsys.readouterr()
    rc = main(["--db", str(db), "--no-embed", "query", "nf525"])
    assert rc == 0
    assert "project_nf525" in capsys.readouterr().out


def test_cli_query_empty_index(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "fresh.sqlite"), "--no-embed", "query", "x"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Empty index" in out
    assert "cc-memory index" in out
    assert "memory-search" not in out


def test_cli_query_filter_project(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    capsys.readouterr()
    rc = main(["--db", str(db), "--no-embed", "query", "agent", "--project", "gamma"])
    assert rc == 0


def test_cli_grep(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    capsys.readouterr()
    rc = main(["--db", str(db), "--no-embed", "grep", "NF525"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "project_nf525" in out


def test_cli_grep_no_match(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    capsys.readouterr()
    rc = main(["--db", str(db), "--no-embed", "grep", "zzzinexistant"])
    assert rc == 0
    assert "No match" in capsys.readouterr().out


def test_cli_stats(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(FIXTURES)])
    capsys.readouterr()
    rc = main(["--db", str(db), "stats"])
    assert rc == 0
    assert "total" in capsys.readouterr().out


def test_cli_version():
    with pytest.raises(SystemExit):
        main(["--version"])


def test_cli_prog_name_help(capsys):
    """Defaut 4 : --help annoncait encore l'ancien nom de binaire memory-search."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "usage: cc-memory" in out
    assert "memory-search" not in out


def test_cli_prog_name_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out
    assert out.startswith("cc-memory")


def test_cli_stale_none(tmp_path, capsys):
    # Copie des fixtures avec mtime force a maintenant : le mtime des fichiers
    # versionnes vieillit, un test qui suppose « recent » finit par echouer
    # (constate le 2026-07-28, fixtures datees du 2026-04-22).
    base = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, base)
    now = time.time()
    for path in base.rglob("*.md"):
        os.utime(path, (now, now))

    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "--no-embed", "index", "--base", str(base)])
    capsys.readouterr()
    rc = main(["--db", str(db), "stale", "--older-than", "1"])
    assert rc == 0
    assert "No stale memory" in capsys.readouterr().out


def test_cli_stale_detected(tmp_path, capsys):
    """Force mtime ancien directement en DB puis stale."""
    from memory_search.index import connect as mc_connect
    from memory_search.index import upsert
    from memory_search.loader import iter_memory as mc_iter

    db = tmp_path / "db.sqlite"
    conn = mc_connect(db)
    import time

    old = time.time() - (150 * 86400)
    for e in mc_iter(FIXTURES):
        upsert(conn, e, None, old)
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "stale", "--older-than", "90"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Stale memories" in out
