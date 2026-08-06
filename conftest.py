"""Garde-fous communs a toute la suite.

Les tests passent deja un `home` explicite pour ne pas dependre du poste. Le
workspace suit la meme regle : il se declare par variable d'environnement, donc
l'environnement de la machine hote doit s'arreter a la porte des tests.
"""

from __future__ import annotations

import pytest
from cctk_core.paths import WORKSPACE_ENV


@pytest.fixture(autouse=True)
def _workspace_neutre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise `$CCTK_WORKSPACE` herite du poste.

    Sans cela, un poste qui exporte cette variable fait passer ou echouer des
    tests qui n'en parlent pas : le defaut des chemins codes en dur, deplace
    dans l'environnement. Un test qui a besoin d'un workspace le declare.
    """
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
