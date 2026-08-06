"""Resolution des chemins utilises par Claude Code.

Claude Code encode le repertoire de travail dans le nom du dossier de session :
`/home/alice/code/app` devient `-home-alice-code-app`. Le prefixe est donc
derive du home reel, jamais code en dur — c'est ce qui rend ces outils
utilisables ailleurs que sur la machine de leur auteur.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE_ENV = "CCTK_WORKSPACE"


def workspace_setting(workspace: str | None = None) -> str:
    """Segment de workspace declare, depuis l'argument ou `$CCTK_WORKSPACE`.

    Rien n'est devine. Un nom de dossier plausible code en dur ne vaut que sur
    la machine de son auteur : `Claude/projets` a survecu a un deplacement du
    workspace et a rendu `cc-run` aveugle a tous les projets, sans une erreur.
    Non declare, le workspace est vide et la racine vaut le home — faux nulle
    part, meme si le scan est plus large.
    """
    raw = workspace if workspace is not None else os.environ.get(WORKSPACE_ENV, "")
    return raw.strip().strip("/")


def _encode(path: Path) -> str:
    """Encode un chemin absolu a la maniere de Claude Code."""
    return str(path).replace("/", "-")


def project_from_dirname(
    dirname: str,
    *,
    home: Path | None = None,
    workspace: str | None = None,
) -> str:
    """Deduit un nom de projet lisible depuis un nom de dossier de session.

    `workspace` (ex. "Projets") retire un segment supplementaire quand
    les projets sont regroupes sous un dossier commun.

    Le fallback ne transforme pas les tirets : dans un nom de dossier, un tiret
    est indiscernable d'un separateur de chemin, le deviner produirait du faux.
    """
    root = home if home is not None else Path.home()
    home_prefix = _encode(root)

    # `strip("/")` est indispensable : un segment absolu reinitialise le join de
    # pathlib — `Path("/home/alice") / "/Claude/projets"` vaut `/Claude/projets`,
    # le prefixe home disparait et plus aucun dirname ne matche, sans erreur.
    ws = workspace_setting(workspace)
    if ws:
        ws_prefix = _encode(root / ws)
        if dirname.startswith(ws_prefix + "-"):
            return dirname[len(ws_prefix) + 1 :]
        if dirname == ws_prefix:
            return Path(ws).name

    if dirname.startswith(home_prefix + "-"):
        return dirname[len(home_prefix) + 1 :]
    if dirname == home_prefix:
        return "home"

    return dirname.lstrip("-")


def transcripts_dir(home: Path | None = None) -> Path:
    """Dossier ou Claude Code ecrit ses transcripts JSONL."""
    root = home if home is not None else Path.home()
    return root / ".claude" / "projects"


def workspace_root(home: Path | None = None, workspace: str | None = None) -> Path:
    """Racine sous laquelle les projets sont regroupes.

    Priorite : argument explicite, puis `$CCTK_WORKSPACE`, puis le home.
    """
    root = home if home is not None else Path.home()
    ws = workspace_setting(workspace)
    return root / ws if ws else root
