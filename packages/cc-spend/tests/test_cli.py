import shutil
from pathlib import Path

import pytest

from cost_tracker.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def setup_projects(tmp_path: Path) -> Path:
    projects = tmp_path / "projects"
    home_prefix = str(Path.home()).rstrip("/").replace("/", "-")
    proj = projects / f"{home_prefix}-Claude-projets-alpha"
    proj.mkdir(parents=True)
    shutil.copy(FIXTURE, proj / "session1.jsonl")
    return projects


def test_cli_scan_and_report(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects), "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "scannes" in out or "scanne" in out
    rc = main(["--db", str(db), "report", "--by", "project"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "TOTAL" in out


def test_cli_export_csv(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    capsys.readouterr()
    out_file = tmp_path / "out.csv"
    rc = main(["--db", str(db), "export", "--format", "csv", "-o", str(out_file)])
    assert rc == 0
    content = out_file.read_text()
    assert "project" in content.splitlines()[0]


def test_cli_export_json_stdout(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    capsys.readouterr()
    rc = main(["--db", str(db), "export", "--format", "json"])
    assert rc == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["cost_usd"] > 0


def test_cli_scan_missing_dir(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "db.sqlite"), "scan", "--projects-dir", "/nope"])
    assert rc == 1


def test_cli_report_empty(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "empty.sqlite"), "report"])
    assert rc == 0
    assert "Aucune" in capsys.readouterr().out


def test_cli_force_rescan(tmp_path):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects), "--force"])
    assert rc == 0


def test_cli_version():
    with pytest.raises(SystemExit):
        main(["--version"])


# --- Defaut 1 : les transcripts de sous-agents comptent dans le total ---


def test_cli_scan_compte_les_transcripts_de_sous_agents(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    subagents = proj / "5f2f6548-f8bc-4254-af14-730602a96bac" / "subagents"
    subagents.mkdir(parents=True)
    shutil.copy(FIXTURE, subagents / "agent-a913d36f1.jsonl")
    db = tmp_path / "db.sqlite"

    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0
    assert "scannes : 2" in capsys.readouterr().out


def test_cli_scan_sous_agent_attribue_au_projet_reel(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    subagents = proj / "session-uuid" / "subagents"
    subagents.mkdir(parents=True)
    shutil.copy(FIXTURE, subagents / "agent-x.jsonl")
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    capsys.readouterr()

    rc = main(["--db", str(db), "report", "--by", "project"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "subagents" not in out
    assert "session-uuid" not in out


def test_cli_scan_sous_agent_rattache_a_la_session_parente(tmp_path, capsys):
    """Les lignes d'un transcript de sous-agent portent le sessionId du parent."""
    import sqlite3

    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    subagents = proj / "session-uuid" / "subagents"
    subagents.mkdir(parents=True)
    shutil.copy(FIXTURE, subagents / "agent-x.jsonl")
    db = tmp_path / "db.sqlite"

    main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    conn = sqlite3.connect(db)
    sessions = {r[0] for r in conn.execute("SELECT DISTINCT session_id FROM usage")}
    rows = conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
    conn.close()
    # Le cout du sous-agent s'ajoute a la session parente : pas de session parasite.
    assert sessions == {"abc-123", "def-456"}
    assert rows == 8


# --- Defaut 3 : tolerance a l'ingestion + commit incremental ---


def test_cli_scan_ligne_fautive_non_fatale(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    (proj / "zz_bad.jsonl").write_text(
        '{"type":"assistant","message":{"model":"m","usage":{"input_tokens":"abc"}},'
        '"timestamp":"2026-04-20T10:00:00Z","sessionId":"s9"}\n'
    )
    db = tmp_path / "db.sqlite"

    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "ecarte" in out.lower()


def test_cli_scan_conserve_le_travail_deja_fait(tmp_path, capsys):
    """C2 : un fichier fautif ne doit pas annuler les fichiers deja inseres."""
    import sqlite3

    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    (proj / "zz_bad.jsonl").write_text("42\n{pas du json\n")
    db = tmp_path / "db.sqlite"

    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0] == 4
    conn.close()


def test_cli_scan_commit_par_fichier(tmp_path, monkeypatch, capsys):
    """C2 : le travail deja indexe doit etre durable avant la fin du run.

    Une connexion independante ne voit que ce qui est committe : elle sert de
    temoin qu'un fichier traite est en base avant que le suivant ne commence.
    """
    import sqlite3

    from cost_tracker import cli as cli_mod

    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    shutil.copy(FIXTURE, proj / "session2.jsonl")
    db = tmp_path / "db.sqlite"

    vus: list[int] = []
    vrai_insert = cli_mod.insert_entries

    def espion(conn, entries):
        temoin = sqlite3.connect(db)
        vus.append(temoin.execute("SELECT COUNT(*) FROM usage").fetchone()[0])
        temoin.close()
        return vrai_insert(conn, entries)

    monkeypatch.setattr(cli_mod, "insert_entries", espion)
    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0
    assert vus == [0, 4], "le 1er fichier doit etre committe avant le 2e"


def test_cli_scan_erreur_sqlite_non_fatale(tmp_path, monkeypatch, capsys):
    """Un echec d'ecriture sur un transcript ne doit pas emporter le run."""
    import sqlite3

    from cost_tracker import cli as cli_mod

    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    shutil.copy(FIXTURE, proj / "session2.jsonl")
    db = tmp_path / "db.sqlite"

    appels = {"n": 0}
    vrai_insert = cli_mod.insert_entries

    def capricieux(conn, entries):
        appels["n"] += 1
        if appels["n"] == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return vrai_insert(conn, entries)

    monkeypatch.setattr(cli_mod, "insert_entries", capricieux)
    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "scannes : 1" in out
    assert "indexation impossible" in out
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0] == 4
    conn.close()


def test_cli_scan_fichier_binaire_non_fatal(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    proj = next(projects.iterdir())
    (proj / "zz_binaire.jsonl").write_bytes(b"\x00\xff\xfe garbage\n")
    db = tmp_path / "db.sqlite"

    rc = main(["--db", str(db), "scan", "--projects-dir", str(projects)])

    assert rc == 0


def test_cli_daily(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    capsys.readouterr()
    rc = main(["--db", str(db), "daily", "--since", ""])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TOTAL" in out
    assert "2026-04-20" in out


def test_cli_daily_empty(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "empty.sqlite"), "daily"])
    assert rc == 0
    assert "Aucune" in capsys.readouterr().out


def test_cli_anomalies_none(tmp_path, capsys):
    projects = setup_projects(tmp_path)
    db = tmp_path / "db.sqlite"
    main(["--db", str(db), "scan", "--projects-dir", str(projects)])
    capsys.readouterr()
    rc = main(["--db", str(db), "anomalies", "--since", ""])
    assert rc == 0
    # Fixture : 4 entrees de cout similaire, aucune anomalie
    assert "Aucune anomalie" in capsys.readouterr().out


def test_cli_anomalies_json(tmp_path, capsys):
    import json as _json

    db = tmp_path / "db.sqlite"
    # Seed manuel pour garantir une anomalie
    import sqlite3

    from cost_tracker.store import SCHEMA

    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute(
        """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
           cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
           VALUES('huge', 'p', 'claude-opus-4-7', '2026-04-20T10:00:00+00:00',
                  100, 100000, 0, 0, 500, 10.0, 't1', 'h1')""",
    )
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "anomalies", "--since", "", "--format", "json"])
    assert rc == 0
    data = _json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["session_id"] == "huge"


def _seed_multi_days(db_path, day_cost_pairs):
    """Seed manuel : liste de (date ISO, cost)."""
    import sqlite3

    from cost_tracker.store import SCHEMA

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    for i, (day, cost) in enumerate(day_cost_pairs):
        conn.execute(
            """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
               cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
               VALUES(?, 'p', 'claude-opus-4-7', ?, 100, 100, 0, 0, 500, ?, 't1', ?)""",
            (f"s{i}", f"{day}T10:00:00+00:00", cost, f"h{i}"),
        )
    conn.commit()
    conn.close()


def test_cli_budget_no_limits(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed_multi_days(db, [("2026-04-20", 100.0), ("2026-04-21", 120.0)])
    rc = main(["--db", str(db), "budget", "--since", ""])
    assert rc == 0
    out = capsys.readouterr().out
    assert "$220" in out
    assert "Moyenne/jour" in out


def test_cli_budget_daily_over(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed_multi_days(db, [("2026-04-20", 300.0), ("2026-04-21", 50.0)])
    rc = main(["--db", str(db), "budget", "--since", "", "--daily", "100"])
    # Un jour a 300 > 100 -> exit 2
    assert rc == 2
    out = capsys.readouterr().out
    assert "OVER" in out or "2026-04-20" in out


def test_cli_budget_daily_under(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed_multi_days(db, [("2026-04-20", 50.0), ("2026-04-21", 60.0)])
    rc = main(["--db", str(db), "budget", "--since", "", "--daily", "100"])
    assert rc == 0


def test_cli_budget_monthly_projection(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    # 7 jours x $100 = avg $100, projection 30j = $3000 > $2000
    pairs = [(f"2026-04-{15+i:02d}", 100.0) for i in range(7)]
    _seed_multi_days(db, pairs)
    rc = main(["--db", str(db), "budget", "--since", "", "--monthly", "2000"])
    assert rc == 2
    assert "Projete fin mois" in capsys.readouterr().out


def test_cli_budget_empty(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "empty.sqlite"), "budget"])
    assert rc == 0
    assert "Aucune" in capsys.readouterr().out
