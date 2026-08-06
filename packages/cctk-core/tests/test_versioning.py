"""La version se declare a un seul endroit, et le socle est contraint.

Les cinq paquets sont restes en `0.1.0` pendant toute leur histoire. `uv` met en
cache les wheels par version : un `cctk-core` modifie mais toujours `0.1.0` etait
donc reinstalle depuis le wheel precedent, y compris avec `--force`. Le correctif
verifie par `uv run` n'existait pas dans le CLI installe, et rien ne le signalait
— `cc-run --version` repondait `0.1.0` dans les deux cas.

Ces tests gardent les deux moities du correctif : une source de verite unique
pour le numero, et une borne basse sur le socle pour que le bump ait un effet.
"""

from __future__ import annotations

import importlib
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

DISTS = {
    "cctk-core": "cctk_core",
    "cc-spend": "cost_tracker",
    "cc-run": "orchestrator",
    "cc-memory": "memory_search",
    "cc-drift": "doc_drift",
}
TOOLS = [d for d in DISTS if d != "cctk-core"]


def _pyproject(dist: str) -> dict:
    return tomllib.loads((ROOT / "packages" / dist / "pyproject.toml").read_text("utf-8"))


@pytest.mark.parametrize("dist", sorted(DISTS))
def test_version_derivee_du_module(dist: str) -> None:
    """`pyproject.toml` ne repete pas le numero : il le lit dans le module."""
    project = _pyproject(dist)["project"]
    assert "version" not in project, (
        f"{dist} fige sa version dans pyproject.toml : deux sources de verite, "
        "qui divergeront."
    )
    assert "version" in project.get("dynamic", []), f"{dist} ne declare pas sa version dynamique"


@pytest.mark.parametrize("dist,module", sorted(DISTS.items()))
def test_version_installee_egale_celle_du_module(dist: str, module: str) -> None:
    assert version(dist) == importlib.import_module(module).__version__


@pytest.mark.parametrize("dist", sorted(TOOLS))
def test_socle_contraint_par_une_borne_basse(dist: str) -> None:
    """Sans borne, un bump de `cctk-core` n'oblige personne a le reinstaller."""
    deps = _pyproject(dist)["project"]["dependencies"]
    socle = [d for d in deps if d.replace("_", "-").startswith("cctk-core")]
    assert socle, f"{dist} ne depend pas de cctk-core"
    assert ">=" in socle[0], (
        f"{dist} depend de cctk-core sans borne basse ({socle[0]!r}) : "
        "le cache de wheels peut resservir un socle perime."
    )


def test_tous_les_paquets_partagent_la_meme_version() -> None:
    """Monorepo publie d'un bloc : des numeros distincts n'auraient aucun sens."""
    versions = {d: importlib.import_module(m).__version__ for d, m in DISTS.items()}
    assert len(set(versions.values())) == 1, versions
