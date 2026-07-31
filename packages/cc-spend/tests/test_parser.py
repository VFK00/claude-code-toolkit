import os
from pathlib import Path

import pytest
from cctk_core import SkipReport

from cost_tracker.parser import (
    iter_transcripts,
    parse_line,
    parse_line_checked,
    parse_transcript,
    project_from_dirname,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def make_project(tmp_path: Path, name: str = "alpha") -> Path:
    home_prefix = str(Path.home()).rstrip("/").replace("/", "-")
    proj = tmp_path / f"{home_prefix}-Claude-projets-{name}"
    proj.mkdir(parents=True)
    return proj


def test_project_from_dirname_delegue_au_socle():
    assert (
        project_from_dirname(
            "-home-alice-Claude-projets-alpha", home=Path("/home/alice")
        )
        == "alpha"
    )


def test_parse_line_user_returns_none():
    line = '{"type":"user","message":{"role":"user","content":"x"}}'
    assert parse_line(line, "proj", "/tmp/t.jsonl") is None


def test_parse_line_invalid_json():
    assert parse_line("not json", "proj", "/tmp/t.jsonl") is None


def test_parse_line_assistant_complete():
    line = (
        '{"type":"assistant","message":{"model":"claude-opus-4-7","usage":'
        '{"input_tokens":10,"output_tokens":20,"cache_read_input_tokens":5,'
        '"cache_creation":{"ephemeral_5m_input_tokens":3,"ephemeral_1h_input_tokens":1}}},'
        '"timestamp":"2026-04-20T10:00:00.000Z","sessionId":"s1"}'
    )
    entry = parse_line(line, "alpha", "/tmp/t.jsonl")
    assert entry is not None
    assert entry.model == "claude-opus-4-7"
    assert entry.input_tokens == 10
    assert entry.output_tokens == 20
    assert entry.cache_read == 5
    assert entry.cache_creation_5m == 3
    assert entry.cache_creation_1h == 1
    assert entry.session_id == "s1"
    assert entry.project == "alpha"


def test_parse_transcript_fixture_count():
    entries = list(parse_transcript(FIXTURE, "fixture"))
    # 4 lignes assistant avec usage (opus, sonnet, haiku, unknown)
    assert len(entries) == 4


def test_iter_transcripts(tmp_path):
    proj = make_project(tmp_path)
    t1 = proj / "s1.jsonl"
    t1.write_text('{"type":"user"}\n')
    results = list(iter_transcripts(tmp_path))
    assert len(results) == 1
    assert results[0][1] == "alpha"


# --- Defaut 1 : decouverte recursive des transcripts de sous-agents ---


def test_iter_transcripts_descend_dans_subagents(tmp_path):
    """`<projet>/<session>/subagents/**/*.jsonl` = 53 % des transcripts reels."""
    proj = make_project(tmp_path)
    (proj / "s1.jsonl").write_text('{"type":"user"}\n')
    subagents = proj / "5f2f6548-f8bc-4254-af14-730602a96bac" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-a913d36f1.jsonl").write_text('{"type":"user"}\n')
    deep = subagents / "workflows" / "wf_review-cascade"
    deep.mkdir(parents=True)
    (deep / "agent-deep.jsonl").write_text('{"type":"user"}\n')

    results = list(iter_transcripts(tmp_path))

    assert {p.name for p, _ in results} == {
        "s1.jsonl",
        "agent-a913d36f1.jsonl",
        "agent-deep.jsonl",
    }


def test_iter_transcripts_projet_reel_pas_le_parent_immediat(tmp_path):
    """Le parent d'un transcript de sous-agent est `subagents`, jamais un projet."""
    proj = make_project(tmp_path)
    subagents = proj / "session-uuid" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-x.jsonl").write_text('{"type":"user"}\n')

    results = list(iter_transcripts(tmp_path))

    assert [project for _, project in results] == ["alpha"]


def test_iter_transcripts_repertoire_illisible_signale(tmp_path):
    report = SkipReport()
    (tmp_path / "vide.txt").write_text("x")
    assert list(iter_transcripts(tmp_path / "nope", report)) == []
    assert report.files == 1


# --- Defaut 3 : une ligne fautive ne doit pas couter le fichier ---


HOSTILE_LINES = [
    ("42", "scalaire JSON nu"),
    ('{"type":"assistant","message":"not-a-dict-string","timestamp":"2026-01-01T00:00:00Z"}',
     "message non-objet"),
    ('{"type":"assistant","message":{"usage":[1,2,3]},"timestamp":"2026-01-01T00:00:00Z"}',
     "usage liste"),
    ('{"type":"assistant","message":{"model":"m","usage":{"input_tokens":"abc"}},'
     '"timestamp":"2026-01-01T00:00:00Z","sessionId":"s"}', "input_tokens non numerique"),
    ('{"type":"assistant","message":{"model":123456,"usage":{"input_tokens":1}},'
     '"timestamp":"2026-01-01T00:00:00Z","sessionId":"s"}', "model int"),
    ('{"type":"assistant","message":{"model":"m","usage":{"input_tokens":1}},'
     '"timestamp":"not-a-date","sessionId":"s"}', "timestamp invalide"),
    ('{"type":"assistant","message":{"model":"m","usage":{"input_tokens":1}},'
     '"timestamp":20260101,"sessionId":"s"}', "timestamp int"),
    ("{pas du json", "JSON malforme"),
]


@pytest.mark.parametrize("line,label", HOSTILE_LINES, ids=[lbl for _, lbl in HOSTILE_LINES])
def test_parse_line_ne_leve_jamais(line, label):
    assert parse_line(line, "proj", "/tmp/t.jsonl") is None


@pytest.mark.parametrize("line,label", HOSTILE_LINES, ids=[lbl for _, lbl in HOSTILE_LINES])
def test_parse_line_checked_donne_un_motif(line, label):
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason, f"{label} doit etre signale, pas avale en silence"


def test_parse_line_checked_ligne_hors_sujet_sans_motif():
    entry, reason = parse_line_checked('{"type":"user"}', "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason is None


def test_parse_line_checked_ligne_vide_sans_motif():
    assert parse_line_checked("\n", "proj", "/tmp/t.jsonl") == (None, None)


def test_parse_line_checked_usage_vide_sans_motif():
    line = '{"type":"assistant","message":{"model":"m","usage":{}},"sessionId":"s"}'
    assert parse_line_checked(line, "proj", "/tmp/t.jsonl") == (None, None)


def test_parse_line_checked_sans_timestamp_est_signale():
    """Cette ligne porte un `usage` reel : elle represente un cout.

    Le comportement d'origine la rejetait sans motif, donc sans un mot a
    l'utilisateur. C'est la logique qui avait fait passer sous silence la
    moitie des transcripts : un scan partiel ne doit jamais ressembler a un
    scan complet.
    """
    line = '{"type":"assistant","message":{"model":"m","usage":{"input_tokens":1}}}'
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason == "missing timestamp"


def test_parse_line_checked_session_non_textuelle():
    line = (
        '{"type":"assistant","message":{"model":"m","usage":{"input_tokens":1}},'
        '"timestamp":"2026-01-01T00:00:00Z","sessionId":999}'
    )
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason == "`sessionId` field is not text"


def test_parse_line_cache_creation_non_dict_ne_bloque_pas():
    line = (
        '{"type":"assistant","message":{"model":"m","usage":'
        '{"input_tokens":7,"cache_creation":"nope"}},'
        '"timestamp":"2026-01-01T00:00:00Z","sessionId":"s"}'
    )
    entry = parse_line(line, "proj", "/tmp/t.jsonl")
    assert entry is not None
    assert entry.input_tokens == 7
    assert entry.cache_creation_5m == 0


def test_parse_transcript_survit_a_une_ligne_fautive(tmp_path):
    good = (
        '{"type":"assistant","message":{"model":"claude-opus-4-7","usage":'
        '{"input_tokens":10,"output_tokens":20}},'
        '"timestamp":"2026-04-20T10:00:00.000Z","sessionId":"s1"}'
    )
    f = tmp_path / "mixed.jsonl"
    f.write_text(f"{good}\n42\n{good}\n")
    report = SkipReport()

    entries = list(parse_transcript(f, "alpha", report))

    assert len(entries) == 2
    assert report.entries == 1
    assert report.reasons.total() == 1


def test_parse_transcript_fichier_binaire_ne_plante_pas(tmp_path):
    f = tmp_path / "latin.jsonl"
    f.write_bytes(b'{"type":"user","x":"caf\xe9"}\n\x00\xff\n')
    report = SkipReport()
    assert list(parse_transcript(f, "alpha", report)) == []


def test_parse_transcript_fichier_illisible_signale(tmp_path):
    report = SkipReport()
    assert list(parse_transcript(tmp_path / "absent.jsonl", "alpha", report)) == []
    assert report.files == 1


def test_parse_transcript_lecture_interrompue_signalee(tmp_path, monkeypatch):
    class LectureQuiCasse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            return self

        def __next__(self):
            raise OSError(5, "Input/output error")

    f = tmp_path / "t.jsonl"
    f.write_text("{}\n")
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: LectureQuiCasse())
    report = SkipReport()

    assert list(parse_transcript(f, "alpha", report)) == []
    assert report.files == 1
    assert "read interrupted" in next(iter(report.reasons))


def test_iter_transcripts_ignore_les_fichiers_a_la_racine(tmp_path):
    (tmp_path / "pas-un-projet.txt").write_text("x")
    proj = make_project(tmp_path)
    (proj / "s1.jsonl").write_text('{"type":"user"}\n')
    assert len(list(iter_transcripts(tmp_path))) == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignore les permissions")
def test_iter_transcripts_projet_illisible_signale(tmp_path):
    proj = make_project(tmp_path)
    (proj / "s1.jsonl").write_text('{"type":"user"}\n')
    proj.chmod(0o000)
    report = SkipReport()
    try:
        results = list(iter_transcripts(tmp_path, report))
    finally:
        proj.chmod(0o755)
    assert results == []
    assert report.files == 1


def test_usage_sans_session_id_est_signale() -> None:
    """Une ligne porteuse d'un `usage` devait compter : si elle n'est pas
    rattachable, elle est signalee, jamais avalee en silence."""
    line = (
        '{"type":"assistant","timestamp":"2026-07-31T10:00:00Z",'
        '"message":{"model":"m","usage":{"input_tokens":1,"output_tokens":1}}}'
    )
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason == "missing sessionId"


def test_usage_sans_timestamp_est_signale() -> None:
    line = (
        '{"type":"assistant","sessionId":"s1",'
        '"message":{"model":"m","usage":{"input_tokens":1,"output_tokens":1}}}'
    )
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason == "missing timestamp"


def test_ligne_sans_usage_reste_hors_sujet() -> None:
    """Sans `usage`, la ligne n'avait pas vocation a compter : rien a signaler."""
    line = '{"type":"assistant","message":{"model":"m"}}'
    entry, reason = parse_line_checked(line, "proj", "/tmp/t.jsonl")
    assert entry is None
    assert reason is None
