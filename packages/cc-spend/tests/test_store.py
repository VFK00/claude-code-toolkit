from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cost_tracker.parser import UsageEntry, parse_transcript
from cost_tracker.store import (
    connect,
    insert_entries,
    mark_transcript,
    purge_transcript,
    report_rows,
    since_to_timestamp,
    transcript_needs_rescan,
    unpriced_models,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"

# Fenetre par defaut interrogee par `daily_rows`/`session_costs` : "30d". Une
# date figee en dur finit hors fenetre au fil du temps (constate 2026-07-28
# sur une fixture datee du 2026-04-20) : ces deux helpers generent une date
# toujours relative a "maintenant" plutot qu'une valeur codee en dur.
def _recent_ts(days_ago: int = 2) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def test_since_to_timestamp_days():
    ts = since_to_timestamp("7d")
    assert "T" in ts


def test_since_to_timestamp_empty():
    assert since_to_timestamp("") == "1970-01-01T00:00:00+00:00"


def test_since_to_timestamp_invalid_value():
    with pytest.raises(ValueError):
        since_to_timestamp("xx")


def test_since_to_timestamp_invalid_unit():
    with pytest.raises(ValueError):
        since_to_timestamp("10y")


def test_insert_and_report(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    entries = list(parse_transcript(FIXTURE, "alpha"))
    inserted = insert_entries(conn, entries)
    assert inserted == 4
    rows = report_rows(conn, group_by="project")
    assert len(rows) == 1
    assert rows[0][0] == "alpha"
    # unknown-model -> cost 0 ; 3 modeles connus contribuent
    assert rows[0][4] > 0


def test_report_group_by_model(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p")))
    rows = report_rows(conn, group_by="model")
    models = {r[0] for r in rows}
    assert "claude-opus-4-7" in models
    assert "claude-sonnet-4-6" in models


def test_report_group_by_session(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p")))
    rows = report_rows(conn, group_by="session")
    assert {r[0] for r in rows} == {"abc-123", "def-456"}


def test_report_project_filter(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p1")))
    insert_entries(conn, list(parse_transcript(FIXTURE, "p2")))
    rows = report_rows(conn, group_by="session", project="p1")
    assert len(rows) == 2  # 2 sessions dans p1 uniquement


def test_report_top_limit(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p")))
    rows = report_rows(conn, group_by="model", top=1)
    assert len(rows) == 1


def test_transcript_needs_rescan(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    f = tmp_path / "t.jsonl"
    f.write_text("line\n")
    assert transcript_needs_rescan(conn, f) is True
    mark_transcript(conn, f)
    assert transcript_needs_rescan(conn, f) is False
    f.write_text("line\nline2\n")
    assert transcript_needs_rescan(conn, f) is True


def test_purge_transcript(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p")))
    purge_transcript(conn, FIXTURE)
    rows = report_rows(conn, group_by="project")
    assert rows == []


def test_invalid_group_by(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError):
        report_rows(conn, group_by="foo")


def test_daily_rows(tmp_path):
    from cost_tracker.store import daily_rows

    conn = connect(tmp_path / "db.sqlite")
    insert_entries(conn, list(parse_transcript(FIXTURE, "p")))
    rows = daily_rows(conn, since="")
    assert len(rows) >= 1
    day, n, cost = rows[0]
    assert len(day) == 10  # YYYY-MM-DD
    assert n > 0


def test_daily_rows_filter(tmp_path):
    from cost_tracker.store import daily_rows

    conn = connect(tmp_path / "db.sqlite")
    # Seed manuel pour garantir 2 projets distincts
    ts = _recent_ts()
    for sid, proj in [("a", "p1"), ("b", "p2")]:
        conn.execute(
            """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
               cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
               VALUES(?, ?, 'claude-opus-4-7', ?, 100, 100, 0, 0, 500, 1.0, ?, ?)""",
            (sid, proj, ts, f"t_{proj}", f"h_{sid}"),
        )
    total_p1 = sum(c for _, _, c in daily_rows(conn, project="p1"))
    total_all = sum(c for _, _, c in daily_rows(conn))
    assert total_p1 == 1.0
    assert total_all == 2.0


def test_session_costs(tmp_path):
    from cost_tracker.store import session_costs

    conn = connect(tmp_path / "db.sqlite")
    # Seed manuel avec une date recente : `session_costs` interroge les 30
    # derniers jours par defaut, une date figee finirait hors fenetre.
    ts = _recent_ts()
    for sid in ("abc-123", "def-456"):
        conn.execute(
            """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
               cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
               VALUES(?, 'p', 'claude-opus-4-7', ?, 100, 100, 0, 0, 500, 1.0, 't1', ?)""",
            (sid, ts, f"h_{sid}"),
        )
    conn.commit()
    rows = session_costs(conn)
    ids = {r[0] for r in rows}
    assert "abc-123" in ids
    assert "def-456" in ids


def test_median_helper():
    from cost_tracker.store import _median

    assert _median([]) == 0.0
    assert _median([5.0]) == 5.0
    assert _median([1.0, 3.0, 2.0]) == 2.0
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_detect_anomalies_empty(tmp_path):
    from cost_tracker.store import detect_anomalies

    conn = connect(tmp_path / "db.sqlite")
    assert detect_anomalies(conn) == []


def test_detect_anomalies_high_cost(tmp_path):
    """Insere manuellement : 5 sessions $1 + 1 session $100 -> la derniere doit etre detectee."""
    from cost_tracker.store import detect_anomalies

    conn = connect(tmp_path / "db.sqlite")
    for i in range(5):
        conn.execute(
            """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
                cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
                VALUES(?, 'p', 'claude-opus-4-7', ?, 100, 100, 0, 0, 500, 1.0, 't1', ?)""",
            (f"s{i}", "2026-04-20T10:00:00+00:00", f"h{i}"),
        )
    conn.execute(
        """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
            cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
            VALUES(?, 'p', 'claude-opus-4-7', ?, 100, 100, 0, 0, 500, 100.0, 't1', 'hbig')""",
        ("big", "2026-04-20T10:00:00+00:00"),
    )
    alerts = detect_anomalies(conn, since="")
    assert any(a["session_id"] == "big" for a in alerts)


def test_detect_anomalies_high_output(tmp_path):
    from cost_tracker.store import detect_anomalies

    conn = connect(tmp_path / "db.sqlite")
    conn.execute(
        """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
            cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
            VALUES(?, 'p', 'claude-opus-4-7', ?, 100, 100000, 0, 0, 500, 10.0, 't1', 'h1')""",
        ("huge", "2026-04-20T10:00:00+00:00"),
    )
    alerts = detect_anomalies(conn, since="")
    assert len(alerts) == 1
    reasons = alerts[0]["reasons"]
    assert any("output tokens eleves" in r for r in reasons)


def test_detect_anomalies_low_cache_ratio(tmp_path):
    from cost_tracker.store import detect_anomalies

    conn = connect(tmp_path / "db.sqlite")
    # input = 1000, cache = 500 -> ratio 0.5 < 3.0
    conn.execute(
        """INSERT INTO usage(session_id, project, model, ts, input_tokens, output_tokens,
            cache_creation_5m, cache_creation_1h, cache_read, cost_usd, transcript, line_hash)
            VALUES(?, 'p', 'claude-opus-4-7', ?, 1000, 100, 0, 0, 500, 5.0, 't1', 'h1')""",
        ("lowcache", "2026-04-20T10:00:00+00:00"),
    )
    alerts = detect_anomalies(conn, since="")
    assert len(alerts) == 1
    reasons = alerts[0]["reasons"]
    assert any("cache ratio" in r for r in reasons)


def test_unpriced_models_signale_ce_qui_echappe_au_tarif(tmp_path: Path) -> None:
    """Un modele absent de la table produit un cout nul.

    Sans signalement, un rapport sous-estime le total sans le dire — un
    resultat faux presente comme valide. Le volume concerne doit remonter.
    """
    conn = connect(tmp_path / "u.db")
    ts = datetime.now(UTC)
    insert_entries(
        conn,
        [
            UsageEntry(
                session_id="s1", project="p", model="claude-opus-4-5",
                timestamp=ts, input_tokens=1000, output_tokens=100,
                cache_creation_5m=0, cache_creation_1h=0, cache_read=0,
                transcript_path="/tmp/a.jsonl",
            ),
            UsageEntry(
                session_id="s2", project="p", model="claude-opus-9-9",
                timestamp=ts, input_tokens=999_999, output_tokens=50_000,
                cache_creation_5m=0, cache_creation_1h=0, cache_read=0,
                transcript_path="/tmp/b.jsonl",
            ),
        ],
    )
    unpriced = unpriced_models(conn)
    assert [m for m, _, _ in unpriced] == ["claude-opus-9-9"]
    model, tokens, entries = unpriced[0]
    assert tokens == 999_999 + 50_000
    assert entries == 1


def test_unpriced_models_vide_quand_tout_est_tarife(tmp_path: Path) -> None:
    conn = connect(tmp_path / "v.db")
    insert_entries(
        conn,
        [
            UsageEntry(
                session_id="s1", project="p", model="claude-sonnet-4-5",
                timestamp=datetime.now(UTC), input_tokens=10, output_tokens=1,
                cache_creation_5m=0, cache_creation_1h=0, cache_read=0,
                transcript_path="/tmp/a.jsonl",
            )
        ],
    )
    assert unpriced_models(conn) == []
