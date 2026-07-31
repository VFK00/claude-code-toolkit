from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _fixed_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixe `Path.home()` a une valeur neutre pour toute la suite.

    Les fixtures encodent un dirname Claude Code (`-home-alice-...`) et la
    resolution de projet (`project_from_dir`) retombe sur `Path.home()` quand
    aucun `home` explicite n'est fourni. Sans ce fixture, les tests
    dependraient du `$HOME` reel de la machine qui les execute.
    """
    monkeypatch.setattr(Path, "home", lambda: Path("/home/alice"))
