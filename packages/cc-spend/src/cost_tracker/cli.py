"""cc-spend command line interface."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from cctk_core import SkipReport, transcripts_dir
from rich.console import Console
from rich.table import Table

from . import __version__
from .parser import iter_transcripts, parse_transcript
from .store import (
    DEFAULT_DB,
    connect,
    daily_rows,
    detect_anomalies,
    insert_entries,
    mark_transcript,
    purge_transcript,
    report_rows,
    transcript_needs_rescan,
)

DEFAULT_PROJECTS = transcripts_dir()
console = Console()


def print_skips(report: SkipReport) -> None:
    """Restitue ce qui a ete ecarte. Silence = resultat faux non signale."""
    for line in report.lines():
        console.print(f"[yellow]{line}[/yellow]", highlight=False, soft_wrap=True)


def cmd_scan(args: argparse.Namespace) -> int:
    base = Path(args.projects_dir)
    if not base.exists():
        console.print(f"[red]Directory not found: {base}[/red]")
        return 1
    conn = connect(Path(args.db))
    report = SkipReport()
    scanned = 0
    inserted = 0
    try:
        for path, project in iter_transcripts(base, report):
            try:
                if not args.force and not transcript_needs_rescan(conn, path):
                    continue
                if args.force:
                    purge_transcript(conn, path)
                entries = list(parse_transcript(path, project, report))
                inserted += insert_entries(conn, entries)
                mark_transcript(conn, path)
                # Commit par fichier : un incident plus loin dans le run ne doit
                # pas annuler ce qui est deja indexe.
                conn.commit()
            except (OSError, sqlite3.Error) as exc:
                conn.rollback()
                report.skip_file(f"indexing failed ({exc})", str(path))
                continue
            scanned += 1
            if args.verbose:
                console.print(f"  scanned: {path.name} ({project}) -> {len(entries)} entries")
    finally:
        conn.commit()
        conn.close()
    console.print(
        f"[green]OK[/green] transcripts scanned: {scanned} | entries added: {inserted}"
    )
    print_skips(report)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    rows = report_rows(
        conn,
        group_by=args.by,
        since=args.since,
        project=args.project,
        top=args.top,
    )
    conn.close()
    if not rows:
        console.print("[yellow]No data. Run `cc-spend scan` first.[/yellow]")
        return 0
    title = f"Claude Code cost by {args.by}"
    if args.since:
        title += f" (since {args.since})"
    if args.project:
        title += f" | project: {args.project}"
    table = Table(title=title)
    table.add_column(args.by, style="cyan")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cache read", justify="right")
    table.add_column("Cost USD", justify="right", style="bold green")
    total = 0.0
    for key, inp, out, cache, cost in rows:
        table.add_row(
            str(key)[:40],
            f"{inp:,}",
            f"{out:,}",
            f"{cache:,}",
            f"${cost:.2f}",
        )
        total += cost
    table.add_section()
    table.add_row("TOTAL", "", "", "", f"[bold]${total:.2f}[/bold]")
    console.print(table)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    rows = report_rows(conn, group_by=args.by, since=args.since, project=args.project)
    conn.close()
    out = Path(args.output) if args.output else None
    if args.format == "json":
        data = [
            {
                args.by: k,
                "input_tokens": i,
                "output_tokens": o,
                "cache_read_tokens": r,
                "cost_usd": round(c, 4),
            }
            for k, i, o, r, c in rows
        ]
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if out:
            out.write_text(text, encoding="utf-8")
            console.print(f"[green]OK[/green] written: {out}")
        else:
            sys.stdout.write(text + "\n")
        return 0
    if args.format == "csv":
        writer = csv.writer(out.open("w", encoding="utf-8") if out else sys.stdout)
        writer.writerow([args.by, "input_tokens", "output_tokens", "cache_read_tokens", "cost_usd"])
        for k, i, o, r, c in rows:
            writer.writerow([k, i, o, r, f"{c:.4f}"])
        if out:
            console.print(f"[green]OK[/green] written: {out}")
        return 0
    console.print(f"[red]Unknown format: {args.format}[/red]")
    return 1


def cmd_daily(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    rows = daily_rows(conn, since=args.since, project=args.project)
    conn.close()
    if not rows:
        console.print("[yellow]No data. Run `cc-spend scan` first.[/yellow]")
        return 0
    title = f"Daily cost (last {args.since or 'all'})"
    if args.project:
        title += f" | project: {args.project}"
    table = Table(title=title)
    table.add_column("Date", style="cyan")
    table.add_column("Entries", justify="right")
    table.add_column("Cost USD", justify="right", style="bold green")
    table.add_column("Trend", justify="center")
    costs = [c for _, _, c in rows]
    max_cost = max(costs) if costs else 0.0
    for date, n, cost in rows:
        bar_width = int((cost / max_cost) * 30) if max_cost else 0
        bar = "█" * bar_width
        table.add_row(date, f"{n:,}", f"${cost:.2f}", bar)
    total = sum(costs)
    avg = total / len(costs)
    table.add_section()
    table.add_row(
        "TOTAL",
        f"{sum(n for _, n, _ in rows):,}",
        f"[bold]${total:.2f}[/bold]",
        f"avg ${avg:.2f}/day",
    )
    console.print(table)
    return 0


def cmd_budget(args: argparse.Namespace) -> int:

    conn = connect(Path(args.db))
    rows = daily_rows(conn, since=args.since, project=args.project)
    conn.close()
    if not rows:
        console.print("[yellow]No data. Run `cc-spend scan` first.[/yellow]")
        return 0

    daily_limit = args.daily
    weekly_limit = args.weekly
    monthly_limit = args.monthly
    totals = [c for _, _, c in rows]
    total = sum(totals)
    n_days = len(totals)
    avg = total / n_days if n_days else 0.0

    # Daily alerts
    over_daily = [(d, c) for d, _, c in rows if daily_limit and c > daily_limit]

    table = Table(title=f"Claude Code budget (last {args.since})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Status", justify="center")

    def status_cell(value: float, limit: float | None) -> str:
        if limit is None:
            return "-"
        pct = (value / limit) * 100
        if pct >= 100:
            return f"[red]{pct:.0f}% OVER[/red]"
        if pct >= 80:
            return f"[yellow]{pct:.0f}%[/yellow]"
        return f"[green]{pct:.0f}%[/green]"

    table.add_row("Period", args.since or "all", "-", "-")
    table.add_row("Days with data", str(n_days), "-", "-")
    table.add_row("Cumulative total", f"${total:.2f}", "-", "-")
    table.add_row("Average/day", f"${avg:.2f}", f"${daily_limit:.2f}" if daily_limit else "-",
                  status_cell(avg, daily_limit))
    # Month-end projection if period >= 7 days
    if n_days >= 7 and monthly_limit:
        projected = avg * 30
        table.add_row("Projected month-end", f"${projected:.2f}", f"${monthly_limit:.2f}",
                      status_cell(projected, monthly_limit))
    # Week = trailing 7-day aggregation at the end
    if weekly_limit and n_days >= 7:
        last_week = sum(c for _, _, c in rows[-7:])
        table.add_row("Last 7d", f"${last_week:.2f}", f"${weekly_limit:.2f}",
                      status_cell(last_week, weekly_limit))

    console.print(table)

    if over_daily:
        alert = Table(title=f"Days over threshold ${daily_limit:.2f}")
        alert.add_column("Date", style="cyan")
        alert.add_column("Cost", justify="right", style="bold red")
        alert.add_column("Over by", justify="right")
        for d, c in over_daily:
            over = c - (daily_limit or 0)
            alert.add_row(d, f"${c:.2f}", f"+${over:.2f}")
        console.print(alert)

    # Exit code 2 if threshold breached
    if daily_limit and over_daily:
        return 2
    if monthly_limit and n_days >= 7 and avg * 30 > monthly_limit:
        return 2
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    alerts = detect_anomalies(
        conn,
        since=args.since,
        project=args.project,
        cost_factor=args.cost_factor,
        min_cache_ratio=args.min_cache_ratio,
    )
    conn.close()
    if not alerts:
        console.print("[green]No anomaly detected.[/green]")
        return 0
    if args.format == "json":
        sys.stdout.write(json.dumps(alerts, indent=2, ensure_ascii=False) + "\n")
        return 0
    table = Table(title=f"Anomalies detected ({len(alerts)})")
    table.add_column("#", justify="right")
    table.add_column("Session", overflow="fold")
    table.add_column("Project", style="cyan")
    table.add_column("Cost", justify="right", style="bold red")
    table.add_column("Reasons", overflow="fold")
    for i, a in enumerate(alerts[: args.limit], 1):
        table.add_row(
            str(i),
            str(a["session_id"])[:12] + "...",
            str(a["project"]),
            f"${a['cost_usd']:.2f}",
            " | ".join(a["reasons"]),
        )
    console.print(table)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cc-spend", description="Claude Code cross-project costs.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite path (default: {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="Index Claude Code transcripts.")
    scan.add_argument(
        "--projects-dir", default=str(DEFAULT_PROJECTS), help="Default: ~/.claude/projects"
    )
    scan.add_argument("--force", action="store_true", help="Full rescan.")
    scan.add_argument("--verbose", "-v", action="store_true")
    scan.set_defaults(func=cmd_scan)

    report = sub.add_parser("report", help="Show a cost report.")
    report.add_argument("--by", choices=["project", "model", "session"], default="project")
    report.add_argument("--since", default="", help="E.g.: 7d, 30d, 24h.")
    report.add_argument("--project", default=None, help="Filter by project.")
    report.add_argument("--top", type=int, default=None, help="Limit to N results.")
    report.set_defaults(func=cmd_report)

    export = sub.add_parser("export", help="Export CSV/JSON.")
    export.add_argument("--by", choices=["project", "model", "session"], default="project")
    export.add_argument("--since", default="")
    export.add_argument("--project", default=None)
    export.add_argument("--format", choices=["csv", "json"], default="csv")
    export.add_argument("--output", "-o", default=None, help="Output file (stdout if empty).")
    export.set_defaults(func=cmd_export)

    daily = sub.add_parser("daily", help="Cost per day with trend.")
    daily.add_argument("--since", default="30d")
    daily.add_argument("--project", default=None)
    daily.set_defaults(func=cmd_daily)

    anomalies = sub.add_parser("anomalies", help="Sessions outside the norm (cost/cache/output).")
    anomalies.add_argument("--since", default="30d")
    anomalies.add_argument("--project", default=None)
    anomalies.add_argument(
        "--cost-factor", type=float, default=3.0, help="Cost x median (default 3.0)"
    )
    anomalies.add_argument(
        "--min-cache-ratio", type=float, default=3.0, help="Target cache/input ratio"
    )
    anomalies.add_argument("--limit", type=int, default=20)
    anomalies.add_argument("--format", choices=["table", "json"], default="table")
    anomalies.set_defaults(func=cmd_anomalies)

    budget = sub.add_parser("budget", help="Alert on daily/weekly/monthly threshold breach.")
    budget.add_argument("--since", default="30d")
    budget.add_argument("--project", default=None)
    budget.add_argument("--daily", type=float, default=None, help="Threshold USD / day")
    budget.add_argument("--weekly", type=float, default=None, help="Threshold USD / last 7 days")
    budget.add_argument(
        "--monthly", type=float, default=None, help="Threshold USD / 30d projection"
    )
    budget.set_defaults(func=cmd_budget)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
