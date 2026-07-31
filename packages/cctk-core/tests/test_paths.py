from pathlib import Path

from cctk_core.paths import project_from_dirname, transcripts_dir, workspace_root

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
