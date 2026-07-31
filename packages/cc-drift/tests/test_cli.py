import os
from pathlib import Path

import pytest

from doc_drift.cli import main


def make_clean(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    (p / "app").mkdir()
    (p / "app" / "api.py").write_text("@router.get('/x')\ndef a(): ...")
    (p / "CLAUDE.md").write_text("**1 routes**")
    return p


def make_drifty(tmp_path: Path) -> Path:
    p = tmp_path / "drifty"
    p.mkdir()
    (p / "app").mkdir()
    (p / "app" / "a.py").write_text("@router.get('/x')\ndef a(): ...")
    (p / "CLAUDE.md").write_text("**50 routes**")
    return p


def test_cli_check_cwd_clean(tmp_path, monkeypatch, capsys):
    p = make_clean(tmp_path)
    monkeypatch.chdir(p)
    rc = main(["check"])
    assert rc == 0


def test_cli_check_cwd_drift(tmp_path, monkeypatch, capsys):
    p = make_drifty(tmp_path)
    monkeypatch.chdir(p)
    rc = main(["check"])
    assert rc == 2
    assert "DRIFT" in capsys.readouterr().out


def test_cli_check_project_flag(tmp_path, capsys):
    make_clean(tmp_path)
    rc = main(["--base", str(tmp_path), "check", "--project", "proj"])
    assert rc == 0


def test_cli_check_project_not_found(tmp_path, capsys):
    rc = main(["--base", str(tmp_path), "check", "--project", "nope"])
    assert rc == 1


def test_cli_check_all(tmp_path, capsys):
    make_clean(tmp_path)
    make_drifty(tmp_path)
    rc = main(["--base", str(tmp_path), "check", "--all"])
    assert rc == 2


def test_cli_check_all_no_projects(tmp_path, capsys):
    rc = main(["--base", str(tmp_path / "empty"), "check", "--all"])
    assert rc == 1


def test_cli_check_threshold_relaxes(tmp_path, capsys):
    make_drifty(tmp_path)
    rc = main(["--base", str(tmp_path), "check", "--project", "drifty", "--threshold", "99"])
    assert rc == 0


def test_cli_check_resolves_subdir(tmp_path, capsys):
    clients = tmp_path / "clients"
    clients.mkdir()
    (clients / "x").mkdir()
    (clients / "x" / "CLAUDE.md").write_text("**2 agents**")
    (clients / "x" / "agents").mkdir()
    (clients / "x" / "agents" / "a.md").touch()
    (clients / "x" / "agents" / "b.md").touch()
    rc = main(["--base", str(tmp_path), "check", "--project", "x"])
    assert rc == 0


def test_cli_install_hook_no_git(tmp_path, capsys):
    p = make_clean(tmp_path)
    rc = main(["install-hook", "--project", str(p)])
    assert rc == 1


def test_cli_install_hook_ok(tmp_path, capsys):
    p = make_clean(tmp_path)
    (p / ".git" / "hooks").mkdir(parents=True)
    rc = main(["install-hook", "--project", str(p)])
    assert rc == 0
    hook = p / ".git" / "hooks" / "pre-commit"
    assert hook.exists()
    assert os.access(hook, os.X_OK)


def test_cli_install_hook_invoque_le_bon_binaire(tmp_path, capsys):
    """Defaut 4 : le hook appelait `doc-drift`, binaire renomme `cc-drift`."""
    p = make_clean(tmp_path)
    (p / ".git" / "hooks").mkdir(parents=True)
    main(["install-hook", "--project", str(p)])
    content = (p / ".git" / "hooks" / "pre-commit").read_text()
    assert "doc-drift" not in content
    assert "cc-drift check" in content


def test_cli_install_hook_executable_reellement(tmp_path):
    """Le hook genere doit tourner : shell valide + binaire resolvable."""
    import subprocess

    p = make_clean(tmp_path)
    (p / ".git" / "hooks").mkdir(parents=True)
    main(["install-hook", "--project", str(p)])
    hook = p / ".git" / "hooks" / "pre-commit"

    proc = subprocess.run(["sh", "-n", str(hook)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    binaries = {
        line.split()[0]
        for line in hook.read_text().splitlines()
        if line and not line.startswith("#") and not line.startswith(" ")
    }
    assert "doc-drift" not in binaries


def test_cli_fix_no_ai_doc(tmp_path, monkeypatch, capsys):
    p = make_clean(tmp_path)
    monkeypatch.chdir(p)
    monkeypatch.setenv("PATH", "")  # vide PATH
    rc = main(["fix", "--dry-run"])
    assert rc == 1


def test_cli_version():
    with pytest.raises(SystemExit):
        main(["--version"])


def test_cli_prog_name_help(capsys):
    """Defaut 4 : --help annoncait encore l'ancien nom de binaire doc-drift."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "usage: cc-drift" in out
    assert "doc-drift" not in out


def test_cli_prog_name_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out
    assert out.startswith("cc-drift")
