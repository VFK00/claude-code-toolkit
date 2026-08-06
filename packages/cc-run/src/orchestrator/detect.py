"""Detection de stack par projet + presets de commandes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXCLUDE_DIRS = {"archives", "node_modules", ".git", "__pycache__", ".venv", "venv"}


@dataclass(frozen=True)
class ProjectStack:
    path: Path
    name: str
    kind: str  # "python-uv" | "python-pip" | "node-pnpm" | "node-npm" | "static" | "unknown"
    has_tests: bool
    has_lint: bool
    subdir: str | None = None  # "backend", "frontend", etc. si stack dans sous-dossier

    def preset_cmd(self, preset: str) -> str | None:
        table: dict[str, dict[str, str]] = {
            "python-uv": {
                "test": "uv run pytest",
                "lint": "uv run ruff check . && uv run mypy src/",
                "build": "uv build",
            },
            "python-pip": {
                "test": "pytest",
                "lint": "ruff check . && mypy .",
                "build": "python -m build",
            },
            "node-pnpm": {
                "test": "pnpm test",
                "lint": "pnpm lint",
                "build": "pnpm build",
            },
            "node-npm": {
                "test": "npm test",
                "lint": "npm run lint",
                "build": "npm run build",
            },
            "static": {},
        }
        status_cmd = "git status --short && git branch --show-current"
        if preset == "status":
            return status_cmd
        cmd = table.get(self.kind, {}).get(preset)
        if cmd is None:
            return None
        if self.subdir:
            return f"cd {self.subdir} && {cmd}"
        return cmd


SUBDIR_CANDIDATES = ("backend", "api", "server", "app")


def _detect_at(path: Path) -> tuple[str, bool]:
    """Retourne (kind, has_tests) en inspectant UNIQUEMENT `path`."""
    uv_lock = path / "uv.lock"
    pyproject = path / "pyproject.toml"
    requirements = path / "requirements.txt"
    package_json = path / "package.json"
    pnpm_lock = path / "pnpm-lock.yaml"
    has_tests = (path / "tests").is_dir() or (path / "test").is_dir() or (path / "e2e").is_dir()
    if uv_lock.exists():
        return "python-uv", has_tests
    if pyproject.exists() or requirements.exists():
        return "python-pip", has_tests
    if package_json.exists():
        return "node-pnpm" if pnpm_lock.exists() else "node-npm", has_tests
    if (path / "index.html").exists():
        return "static", has_tests
    return "unknown", has_tests


def detect_project(path: Path) -> ProjectStack:
    name = path.name
    kind, has_tests = _detect_at(path)
    subdir: str | None = None
    if kind == "unknown":
        for candidate in SUBDIR_CANDIDATES:
            sub = path / candidate
            if sub.is_dir():
                sub_kind, sub_tests = _detect_at(sub)
                if sub_kind != "unknown":
                    kind = sub_kind
                    has_tests = has_tests or sub_tests
                    subdir = candidate
                    break
    if subdir:
        has_lint = True
    else:
        has_lint = (path / "pyproject.toml").exists() or (path / "package.json").exists()
    return ProjectStack(
        path=path, name=name, kind=kind, has_tests=has_tests, has_lint=has_lint, subdir=subdir
    )


def _usable(path: Path) -> bool:
    """Ecarte le bruit : caches, dossiers caches, dossiers de service `_*`."""
    return (
        path.is_dir()
        and path.name not in EXCLUDE_DIRS
        and not path.name.startswith((".", "_"))
    )


def _children(path: Path) -> list[Path]:
    """Sous-dossiers exploitables. Un dossier illisible vaut zero enfant."""
    try:
        return sorted(c for c in path.iterdir() if _usable(c))
    except OSError:
        return []


def _looks_like_project(path: Path) -> bool:
    """Marqueur de stack a la racine ou dans un sous-dossier standard, ou depot git."""
    return (path / ".git").exists() or detect_project(path).kind != "unknown"


def scan_projects(base: Path, recurse_into: set[str] | None = None) -> list[ProjectStack]:
    """Scanne `base` pour trouver les projets.

    Un dossier qui ne porte aucun marqueur de projet, mais dont les enfants en
    portent, est une **categorie** : on descend d'un niveau plutot que de le
    compter pour un projet. Cette liste etait figee a `{clients, outils}`, ce
    qui laissait invisible tout regroupement portant un autre nom — `produits/`
    remontait comme une ligne unique et ses projets n'existaient pas pour
    `cc-run run`.

    `recurse_into` force la descente pour des noms donnes.
    """
    results: list[ProjectStack] = []
    if not base.is_dir():
        return results

    for entry in sorted(base.iterdir()):
        if not _usable(entry):
            continue
        children = _children(entry)
        forced = recurse_into is not None and entry.name in recurse_into
        is_category = not _looks_like_project(entry) and any(
            _looks_like_project(c) for c in children
        )
        if forced or is_category:
            results.extend(detect_project(c) for c in children)
            continue
        results.append(detect_project(entry))
    return results


def filter_projects(
    projects: list[ProjectStack],
    names: list[str] | None = None,
    match: str | None = None,
) -> list[ProjectStack]:
    out = projects
    if names:
        wanted = set(names)
        out = [p for p in out if p.name in wanted]
    if match == "python":
        out = [p for p in out if p.kind.startswith("python")]
    elif match == "node":
        out = [p for p in out if p.kind.startswith("node")]
    elif match:
        out = [p for p in out if match in p.kind]
    return out
