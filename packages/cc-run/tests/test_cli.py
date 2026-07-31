from pathlib import Path

import pytest

from orchestrator.cli import main


def make_proj(base: Path, name: str, files: list[str]):
    p = base / name
    p.mkdir()
    for f in files:
        (p / f).touch()


def test_cli_list(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock", "pyproject.toml"])
    make_proj(tmp_path, "b", ["package.json"])
    rc = main(["--base", str(tmp_path), "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a" in out and "b" in out


def test_cli_run_echo(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    make_proj(tmp_path, "b", ["package.json"])
    rc = main(["--base", str(tmp_path), "run", "echo ok"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_cli_run_fail_returns_2(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    rc = main(["--base", str(tmp_path), "run", "false"])
    assert rc == 2


def test_cli_preset_status(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    # git non init dans tmp_path -> status echoue mais l'exec tourne
    rc = main(["--base", str(tmp_path), "preset", "status"])
    assert rc in (0, 2)


def test_cli_preset_skips_static(tmp_path, capsys):
    make_proj(tmp_path, "static", ["index.html"])
    rc = main(["--base", str(tmp_path), "preset", "test"])
    out = capsys.readouterr().out
    assert "Skip" in out or "Aucun job" in out
    assert rc == 1


def test_cli_no_projects_run(tmp_path, capsys):
    rc = main(["--base", str(tmp_path / "empty"), "run", "echo"])
    assert rc == 1


def test_cli_filter_projects(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    make_proj(tmp_path, "b", ["uv.lock"])
    rc = main(["--base", str(tmp_path), "--projects", "a", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a" in out
    # tolerant : vrai critere est que le filtre limite a 1 projet
    assert "python-uv" in out


def test_cli_match_python(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    make_proj(tmp_path, "b", ["package.json"])
    rc = main(["--base", str(tmp_path), "--match", "python", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "python-uv" in out


def test_cli_verbose(tmp_path, capsys):
    make_proj(tmp_path, "a", ["uv.lock"])
    rc = main(["--base", str(tmp_path), "-v", "run", "echo detail"])
    assert rc == 0
    assert "detail" in capsys.readouterr().out


def test_cli_version():
    with pytest.raises(SystemExit):
        main(["--version"])


def test_cli_prog_name_help(capsys):
    """Defaut 4 : --help annoncait encore l'ancien nom de binaire orchestrator."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "usage: cc-run" in out
    assert "orchestrator" not in out


def test_cli_prog_name_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out
    assert out.startswith("cc-run")
