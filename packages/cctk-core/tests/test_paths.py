from pathlib import Path

from cctk_core.paths import (
    WORKSPACE_ENV,
    project_from_dirname,
    transcripts_dir,
    workspace_root,
    workspace_setting,
)

HOME = Path("/home/alice")


def test_projet_sous_workspace() -> None:
    assert (
        project_from_dirname(
            "-home-alice-Claude-projets-alpha", home=HOME, workspace="Claude/projets"
        )
        == "alpha"
    )


def test_sous_dossier_garde_ses_tirets() -> None:
    assert (
        project_from_dirname(
            "-home-alice-Claude-projets-outils-delta", home=HOME, workspace="Claude/projets"
        )
        == "outils-delta"
    )


def test_home_nu() -> None:
    assert project_from_dirname("-home-alice", home=HOME) == "home"


def test_workspace_nu_retourne_projets() -> None:
    assert (
        project_from_dirname("-home-alice-Claude-projets", home=HOME, workspace="Claude/projets")
        == "projets"
    )


def test_fallback_ne_transforme_pas_les_tirets() -> None:
    assert project_from_dirname("weird-name", home=HOME) == "weird-name"


def test_home_different_fonctionne() -> None:
    """Le prefixe est derive de `home`, jamais code en dur."""
    assert (
        project_from_dirname("-Users-bob-code-app", home=Path("/Users/bob"), workspace="code")
        == "app"
    )


def test_sans_workspace_retourne_le_chemin_relatif() -> None:
    assert project_from_dirname("-home-alice-perso-site", home=HOME) == "perso-site"


def test_workspace_avec_slashes_superflus() -> None:
    """Un segment absolu reinitialise le join de pathlib — le prefixe home
    disparaitrait et le matching echouerait en silence."""
    assert (
        project_from_dirname(
            "-home-alice-Claude-projets-alpha", home=HOME, workspace="/Claude/projets/"
        )
        == "alpha"
    )


def test_transcripts_dir() -> None:
    assert transcripts_dir(HOME) == Path("/home/alice/.claude/projects")


def test_workspace_root() -> None:
    assert workspace_root(HOME, "Claude/projets") == Path("/home/alice/Claude/projets")


# --- Workspace declare par l'environnement ---


def test_workspace_root_sans_declaration_vaut_le_home(monkeypatch) -> None:
    """Aucun nom de dossier n'est devine.

    L'ancien defaut `Claude/projets` a survecu au deplacement du workspace :
    `cc-run list` a renvoye zero projet sur une vingtaine, en sortant `0`.
    Un scan trop large se voit ; une racine inexistante ne se voit pas.
    """
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    assert workspace_root(HOME) == HOME


def test_workspace_root_lit_l_environnement(monkeypatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV, "Projets")
    assert workspace_root(HOME) == Path("/home/alice/Projets")


def test_argument_explicite_prime_sur_l_environnement(monkeypatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV, "Projets")
    assert workspace_root(HOME, "autre") == Path("/home/alice/autre")


def test_project_from_dirname_lit_l_environnement(monkeypatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV, "Projets")
    assert project_from_dirname("-home-alice-Projets-outils-delta", home=HOME) == "outils-delta"


def test_workspace_setting_nettoie_les_bords(monkeypatch) -> None:
    monkeypatch.setenv(WORKSPACE_ENV, "  /Projets/  ")
    assert workspace_setting() == "Projets"


def test_workspace_setting_vide_si_non_declare(monkeypatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    assert workspace_setting() == ""
