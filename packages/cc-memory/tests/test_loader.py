import os
from pathlib import Path

import pytest
from cctk_core import SkipReport

from memory_search.loader import iter_memory, parse_file, project_from_dir

FIXTURES = Path(__file__).parent / "fixtures" / "sample_projects"


def test_project_from_dir_delegue_au_socle():
    assert (
        project_from_dir("-home-alice-Claude-projets-alpha", home=Path("/home/alice"))
        == "alpha"
    )


def test_parse_file_with_frontmatter(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("---\nname: Test\ndescription: desc\ntype: project\n---\n\nbody here")
    e = parse_file(f, "proj")
    assert e is not None
    assert e.name == "Test"
    assert e.type == "project"
    assert "body here" in e.body


def test_parse_file_malformed_yaml(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("---\nname: [unclosed\n---\n\nbody")
    e = parse_file(f, "proj")
    assert e is not None
    assert e.name == ""


def test_parse_file_no_frontmatter(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("plain content")
    e = parse_file(f, "proj")
    assert e is not None
    assert e.body == "plain content"
    assert e.type == "unknown"


def test_iter_memory_skips_memory_md_index():
    entries = list(iter_memory(FIXTURES))
    slugs = {e.slug for e in entries}
    assert "MEMORY" not in slugs
    assert "project_nf525" in slugs


def test_iter_memory_project_mapping():
    entries = list(iter_memory(FIXTURES))
    projects = {e.project for e in entries}
    assert "alpha" in projects
    assert "gamma" in projects


def test_iter_memory_missing_base(tmp_path):
    assert list(iter_memory(tmp_path / "nope")) == []


def test_iter_memory_ignore_projet_sans_dossier_memory(tmp_path):
    (tmp_path / "un-projet-sans-memoire").mkdir()
    assert list(iter_memory(tmp_path)) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignore les permissions")
def test_iter_memory_base_illisible_signalee(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    base.chmod(0o000)
    report = SkipReport()
    try:
        entries = list(iter_memory(base, report))
    finally:
        base.chmod(0o755)
    assert entries == []
    assert report.files == 1


# --- Defaut 3 : frontmatter YAML valide mais non-mapping ---


@pytest.mark.parametrize(
    "front",
    ["- foo\n- bar", "just a plain scalar string", "42", "true"],
    ids=["liste", "scalaire", "int", "bool"],
)
def test_parse_file_frontmatter_non_mapping(tmp_path, front):
    f = tmp_path / "bad.md"
    f.write_text(f"---\n{front}\n---\nCorps.")
    e = parse_file(f, "proj")
    assert e is not None
    assert e.name == ""
    assert e.type == "unknown"
    assert "Corps." in e.body


def test_parse_file_illisible_signale(tmp_path):
    report = SkipReport()
    assert parse_file(tmp_path / "absent.md", "proj", report) is None
    assert report.files == 1


def test_iter_memory_un_fichier_casse_ne_perd_pas_les_autres(tmp_path):
    home_prefix = str(Path.home()).rstrip("/").replace("/", "-")
    memory = tmp_path / f"{home_prefix}-Claude-projets-alpha" / "memory"
    memory.mkdir(parents=True)
    (memory / "ok1.md").write_text("---\nname: A\n---\nbody")
    (memory / "casse.md").write_text("---\n- foo\n- bar\n---\nCorps.")
    (memory / "ok2.md").write_text("---\nname: B\n---\nbody")

    entries = list(iter_memory(tmp_path))

    assert {e.slug for e in entries} == {"ok1", "casse", "ok2"}


def test_iter_memory_symlink_circulaire_signale(tmp_path):
    home_prefix = str(Path.home()).rstrip("/").replace("/", "-")
    memory = tmp_path / f"{home_prefix}-Claude-projets-alpha" / "memory"
    memory.mkdir(parents=True)
    (memory / "ok.md").write_text("body")
    (memory / "boucle.md").symlink_to("boucle.md")
    report = SkipReport()

    entries = list(iter_memory(tmp_path, report))

    assert {e.slug for e in entries} == {"ok"}
    assert report.files == 1


def test_searchable_text_concat(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("---\nname: A\ndescription: B\n---\nC")
    e = parse_file(f, "p")
    assert "A" in e.searchable_text()
    assert "B" in e.searchable_text()
    assert "C" in e.searchable_text()
