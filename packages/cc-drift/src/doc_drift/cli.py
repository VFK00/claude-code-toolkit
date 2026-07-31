"""cc-drift command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cctk_core import workspace_root
from rich.console import Console
from rich.table import Table

from . import __version__
from .signals import DriftResult, analyze

DEFAULT_BASE = workspace_root()
console = Console()


def iter_candidate_projects(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    results: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name == "archives":
            continue
        if entry.name in {"clients", "outils"}:
            for sub in sorted(entry.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    results.append(sub)
            continue
        results.append(entry)
    return results


def resolve_targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return iter_candidate_projects(Path(args.base))
    if args.project:
        base = Path(args.base)
        p = base / args.project
        if not p.is_dir():
            for sub in ("clients", "outils"):
                alt = base / sub / args.project
                if alt.is_dir():
                    return [alt]
            console.print(f"[red]Project not found: {args.project}[/red]")
            return []
        return [p]
    return [Path.cwd()]


def print_result(result: DriftResult, threshold: float) -> None:
    header = f"{result.project.name} (threshold {threshold:.0f}%)"
    table = Table(title=header)
    table.add_column("Signal", style="cyan")
    table.add_column("Doc", justify="right")
    table.add_column("Code", justify="right")
    table.add_column("Drift %", justify="right")
    table.add_column("Status", justify="center")
    signals = [
        ("routes", result.doc.routes, result.code.routes),
        ("models", result.doc.models, result.code.models),
        ("agents", result.doc.agents, result.code.agents),
        ("tests", result.doc.tests, result.code.tests),
    ]
    drift_map = {d[0]: d for d in result.drifts}
    for label, doc_v, code_v in signals:
        if doc_v is None and code_v == 0:
            continue
        if label in drift_map:
            _, _, _, pct = drift_map[label]
            status = "[red]DRIFT[/red]"
            pct_s = f"{pct:.0f}"
        elif doc_v is None:
            status = "[yellow]no doc[/yellow]"
            pct_s = "-"
        else:
            status = "[green]OK[/green]"
            pct_s = "0"
        table.add_row(label, "-" if doc_v is None else str(doc_v), str(code_v), pct_s, status)
    console.print(table)
    if result.docs_found:
        console.print(f"  Docs read: {', '.join(result.docs_found)}")
    console.print(f"  Source files scanned: {result.code.files_scanned}")


def cmd_check(args: argparse.Namespace) -> int:
    targets = resolve_targets(args)
    if not targets:
        return 1
    any_drift = False
    for root in targets:
        result = analyze(root, threshold=args.threshold)
        print_result(result, threshold=args.threshold)
        if result.has_drift:
            any_drift = True
    return 2 if any_drift else 0


HOOK_TEMPLATE = """#!/bin/sh
# cc-drift pre-commit hook
cc-drift check --threshold {threshold} || {{
    echo "cc-drift: doc/code drift detected. Update the docs, or rerun" >&2
    echo "with a different threshold: cc-drift install-hook --threshold N." >&2
    exit 1
}}
"""


def cmd_install_hook(args: argparse.Namespace) -> int:
    root = Path(args.project) if args.project else Path.cwd()
    hook_path = root / ".git" / "hooks" / "pre-commit"
    if not hook_path.parent.is_dir():
        console.print(f"[red]Not a git repo: {root}[/red]")
        return 1
    hook_path.write_text(HOOK_TEMPLATE.format(threshold=args.threshold), encoding="utf-8")
    hook_path.chmod(0o755)
    console.print(f"[green]OK[/green] hook installed: {hook_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cc-drift", description="Documentation/code drift detector.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--base", default=str(DEFAULT_BASE), help=f"Projects root (default: {DEFAULT_BASE})."
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Analyze drift.")
    group = check.add_mutually_exclusive_group()
    group.add_argument("--project", default=None, help="Project name to scan.")
    group.add_argument("--all", action="store_true", help="Scan all projects under --base.")
    check.add_argument(
        "--threshold", type=float, default=25.0, help="Tolerated percentage (default 25)."
    )
    check.set_defaults(func=cmd_check)

    hook = sub.add_parser("install-hook", help="Install a pre-commit hook.")
    hook.add_argument("--project", default=None, help="Project path (default: cwd).")
    hook.add_argument("--threshold", type=float, default=25.0)
    hook.set_defaults(func=cmd_install_hook)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
