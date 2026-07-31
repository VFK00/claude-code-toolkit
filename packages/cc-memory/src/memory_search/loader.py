"""Charge les fichiers memory YAML+Markdown depuis ~/.claude/projects/*/memory/."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import yaml
from cctk_core import SkipReport
from cctk_core import project_from_dirname as _project_from_dirname
from pydantic import BaseModel, Field

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class MemoryEntry(BaseModel):
    path: str
    project: str
    slug: str
    name: str = ""
    description: str = ""
    type: str = "unknown"
    body: str = ""
    raw: str = Field(default="", exclude=True)

    def searchable_text(self) -> str:
        return f"{self.name}\n{self.description}\n{self.body}".strip()


def project_from_dir(dirname: str, *, home: Path | None = None) -> str:
    """Deduit le nom du projet depuis un dossier de session Claude Code."""
    return _project_from_dirname(dirname, home=home, workspace="Claude/projets")


def parse_file(
    path: Path, project: str, report: SkipReport | None = None
) -> MemoryEntry | None:
    """Charge un fichier memory. Ne leve jamais : un fichier casse coute ce
    fichier, jamais l'indexation entiere."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        if report is not None:
            reason = exc.strerror or exc.__class__.__name__
            report.skip_file(f"lecture impossible ({reason})", str(path))
        return None
    slug = path.stem
    match = FRONTMATTER_RE.match(text)
    if match:
        front_raw, body = match.group(1), match.group(2)
        try:
            front = yaml.safe_load(front_raw)
        except yaml.YAMLError:
            front = None
        # YAML valide mais non-mapping (liste, scalaire) : le frontmatter est
        # inexploitable, le corps reste indexable.
        if not isinstance(front, dict):
            if front is not None and report is not None:
                report.skip_entry("frontmatter YAML non-mapping", str(path))
            front = {}
        return MemoryEntry(
            path=str(path),
            project=project,
            slug=slug,
            name=str(front.get("name", "")),
            description=str(front.get("description", "")),
            type=str(front.get("type", "unknown")),
            body=body.strip(),
            raw=text,
        )
    return MemoryEntry(
        path=str(path),
        project=project,
        slug=slug,
        body=text.strip(),
        raw=text,
    )


def iter_memory(base: Path, report: SkipReport | None = None) -> Iterator[MemoryEntry]:
    """Parcourt `~/.claude/projects/*/memory/*.md`."""
    if not base.exists():
        return
    try:
        project_dirs = sorted(base.iterdir())
    except OSError as exc:
        if report is not None:
            report.skip_file(f"repertoire illisible ({exc.strerror or exc})", str(base))
        return
    for project_dir in project_dirs:
        memory = project_dir / "memory"
        if not memory.is_dir():
            continue
        project = project_from_dir(project_dir.name)
        for md in sorted(memory.glob("*.md")):
            if md.name == "MEMORY.md":
                continue
            entry = parse_file(md, project, report)
            if entry:
                yield entry
