"""cc-run command line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from cctk_core import workspace_root
from rich.console import Console
from rich.table import Table

from . import __version__
from .detect import ProjectStack, filter_projects, scan_projects
from .runner import RunResult, run_many

DEFAULT_BASE = workspace_root()
console = Console()


def resolve_projects(args: argparse.Namespace) -> list[ProjectStack]:
    base = Path(args.base)
    names = [n.strip() for n in args.projects.split(",") if n.strip()] if args.projects else None
    all_projects = scan_projects(base)
    return filter_projects(all_projects, names=names, match=args.match)


def print_results(results: list[RunResult], verbose: bool) -> None:
    table = Table(title="Orchestrator")
    table.add_column("Project", style="cyan")
    table.add_column("Cmd", overflow="fold")
    table.add_column("Code", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Status", justify="center")
    for r in results:
        status = "[green]OK[/green]" if r.ok else "[red]FAIL[/red]"
        table.add_row(
            r.name,
            r.command[:60],
            str(r.exit_code),
            f"{r.duration_s:.1f}s",
            status,
        )
    console.print(table)
    if verbose:
        for r in results:
            console.rule(f"{r.name} :: {r.command}")
            if r.stdout:
                console.print(r.stdout.rstrip())
            if r.stderr:
                console.print(f"[red]{r.stderr.rstrip()}[/red]")


def cmd_list(args: argparse.Namespace) -> int:
    projects = resolve_projects(args)
    table = Table(title="Detected projects")
    table.add_column("Name", style="cyan")
    table.add_column("Kind")
    table.add_column("Subdir")
    table.add_column("Tests", justify="center")
    table.add_column("Path", overflow="fold")
    for p in projects:
        table.add_row(
            p.name,
            p.kind,
            p.subdir or "-",
            "O" if p.has_tests else "-",
            str(p.path),
        )
    console.print(table)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    projects = resolve_projects(args)
    if not projects:
        console.print("[yellow]No project detected.[/yellow]")
        return 1
    jobs = [(p.name, p.path, args.command) for p in projects]
    results = asyncio.run(run_many(jobs, concurrency=args.concurrency, timeout=args.timeout))
    print_results(results, verbose=args.verbose)
    return 0 if all(r.ok for r in results) else 2


def cmd_preset(args: argparse.Namespace) -> int:
    projects = resolve_projects(args)
    jobs: list[tuple[str, Path, str]] = []
    skipped: list[str] = []
    for p in projects:
        cmd = p.preset_cmd(args.preset)
        if cmd is None:
            skipped.append(f"{p.name} ({p.kind})")
            continue
        jobs.append((p.name, p.path, cmd))
    if skipped:
        console.print(
            f"[yellow]Skip (preset {args.preset} unavailable): {', '.join(skipped)}[/yellow]"
        )
    if not jobs:
        console.print("[yellow]No job to run.[/yellow]")
        return 1
    results = asyncio.run(run_many(jobs, concurrency=args.concurrency, timeout=args.timeout))
    print_results(results, verbose=args.verbose)
    return 0 if all(r.ok for r in results) else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cc-run", description="Parallel exec across N projects.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--base", default=str(DEFAULT_BASE), help=f"Projects root (default: {DEFAULT_BASE})"
    )
    p.add_argument("--projects", default=None, help="Comma-separated names.")
    p.add_argument("--match", default=None, help="Filter kind: python | node | static")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--verbose", "-v", action="store_true")

    sub = p.add_subparsers(dest="cmd", required=True)

    lst = sub.add_parser("list", help="List detected projects.")
    lst.set_defaults(func=cmd_list)

    run = sub.add_parser("run", help="Run a free-form command across all filtered projects.")
    run.add_argument("command", help="Shell command.")
    run.set_defaults(func=cmd_run)

    preset = sub.add_parser("preset", help="Run preset (test/lint/build/status).")
    preset.add_argument("preset", choices=["test", "lint", "build", "status"])
    preset.set_defaults(func=cmd_preset)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
