"""cc-memory command line interface."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from cctk_core import SkipReport, transcripts_dir
from rich.console import Console
from rich.table import Table

from . import __version__
from .index import DEFAULT_DB, connect, load_all, stale_entries, stats, upsert
from .loader import iter_memory
from .search import Scored, embed_ollama, fulltext_score, grep_entries, semantic_score

DEFAULT_BASE = transcripts_dir()
console = Console()


def print_skips(report: SkipReport) -> None:
    """Restitue ce qui a ete ecarte pendant l'indexation."""
    for line in report.lines():
        console.print(f"[yellow]{line}[/yellow]", highlight=False, soft_wrap=True)


def cmd_index(args: argparse.Namespace) -> int:
    base = Path(args.base)
    if not base.exists():
        console.print(f"[red]Repertoire introuvable : {base}[/red]")
        return 1
    conn = connect(Path(args.db))
    report = SkipReport()
    entries = list(iter_memory(base, report))
    if not entries:
        conn.close()
        console.print("[yellow]Aucun fichier memory trouve.[/yellow]")
        print_skips(report)
        return 0
    embeddings: list[list[float]] | None = None
    if not args.no_embed:
        try:
            texts = [e.searchable_text() for e in entries]
            embeddings = embed_ollama(texts, model=args.embed_model, host=args.ollama_host)
            console.print(f"[green]OK[/green] embeddings : {len(embeddings)} docs")
        except Exception as exc:
            console.print(f"[yellow]Embeddings indispo ({exc}). Fulltext-only.[/yellow]")
            embeddings = None
    indexed = 0
    for i, entry in enumerate(entries):
        emb = embeddings[i] if embeddings else None
        try:
            mtime = os.path.getmtime(entry.path)
            upsert(conn, entry, emb, mtime)
            # Commit par entree : un incident sur le fichier suivant ne doit pas
            # annuler l'indexation deja faite.
            conn.commit()
        except (OSError, sqlite3.Error) as exc:
            conn.rollback()
            report.skip_file(f"indexation impossible ({exc})", entry.path)
            continue
        indexed += 1
    conn.close()
    console.print(f"[green]OK[/green] indexe : {indexed} entrees memory")
    print_skips(report)
    return 0


def _print_results(results: list[Scored], limit: int) -> None:
    table = Table(title="Memory search")
    table.add_column("#", justify="right")
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Project", style="cyan")
    table.add_column("Type")
    table.add_column("Slug")
    table.add_column("Name", overflow="fold")
    for i, r in enumerate(results[:limit], 1):
        table.add_row(
            str(i),
            f"{r.score:.3f}",
            r.entry.project,
            r.entry.type,
            r.entry.slug,
            (r.entry.name or r.entry.description)[:60],
        )
    console.print(table)


def cmd_query(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    loaded = load_all(conn, project=args.project, type_=args.type)
    conn.close()
    if not loaded:
        console.print("[yellow]Index vide. Lance `memory-search index`.[/yellow]")
        return 0
    entries = [e for e, _ in loaded]
    embeddings = [emb for _, emb in loaded]

    fulltext = fulltext_score(entries, args.query)
    sem: list[Scored] = []
    if not args.no_embed and all(e is not None for e in embeddings):
        try:
            q_emb = embed_ollama([args.query], model=args.embed_model, host=args.ollama_host)[0]
            sem = semantic_score(entries, args.query, embeddings, q_emb)  # type: ignore[arg-type]
        except Exception as exc:
            console.print(f"[yellow]Semantic skipped ({exc}).[/yellow]")

    # Fusion : normalise puis somme ponderee
    merged: dict[str, Scored] = {}
    if fulltext:
        max_ft = max(s.score for s in fulltext) or 1.0
        for s in fulltext:
            merged[s.entry.path] = Scored(
                entry=s.entry, score=(s.score / max_ft) * 0.6, reason=s.reason
            )
    if sem:
        for s in sem:
            prev = merged.get(s.entry.path)
            boost = max(0.0, s.score) * 0.4
            if prev:
                merged[s.entry.path] = Scored(
                    entry=prev.entry,
                    score=prev.score + boost,
                    reason=prev.reason + "+semantic",
                )
            else:
                merged[s.entry.path] = Scored(entry=s.entry, score=boost, reason="semantic")
    final = sorted(merged.values(), key=lambda s: s.score, reverse=True)
    _print_results(final, limit=args.limit)
    return 0


def cmd_grep(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    loaded = load_all(conn, project=args.project, type_=args.type)
    conn.close()
    entries = [e for e, _ in loaded]
    try:
        results = grep_entries(entries, args.pattern)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    if not results:
        console.print("[yellow]Aucun match.[/yellow]")
        return 0
    _print_results(results, limit=args.limit)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    s = stats(conn)
    conn.close()
    table = Table(title="Memory stats")
    table.add_column("Cle", style="cyan")
    table.add_column("Valeur", justify="right")
    for k, v in sorted(s.items()):
        table.add_row(k, str(v))
    console.print(table)
    return 0


def cmd_stale(args: argparse.Namespace) -> int:
    conn = connect(Path(args.db))
    entries = stale_entries(
        conn,
        older_than_days=args.older_than,
        project=args.project,
        type_=args.type,
    )
    conn.close()
    if not entries:
        console.print(
            f"[green]Aucune memoire stale (seuil {args.older_than}j).[/green]"
        )
        return 0
    table = Table(title=f"Memoires stale (>= {args.older_than}j)")
    table.add_column("#", justify="right")
    table.add_column("Age", justify="right", style="bold yellow")
    table.add_column("Project", style="cyan")
    table.add_column("Type")
    table.add_column("Slug")
    table.add_column("Path", overflow="fold")
    for i, (entry, _, age) in enumerate(entries[: args.limit], 1):
        table.add_row(
            str(i),
            f"{age}j",
            entry.project,
            entry.type,
            entry.slug,
            entry.path,
        )
    console.print(table)
    if len(entries) > args.limit:
        reste = len(entries) - args.limit
        console.print(f"[dim]... + {reste} autres (utilise --limit pour afficher plus)[/dim]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memory-search", description="Recherche cross-projet memory.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--embed-model", default="nomic-embed-text")
    p.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    p.add_argument("--no-embed", action="store_true", help="Desactive semantic search.")

    sub = p.add_subparsers(dest="cmd", required=True)

    idx = sub.add_parser("index", help="Construit/maj l'index.")
    idx.add_argument("--base", default=str(DEFAULT_BASE))
    idx.set_defaults(func=cmd_index)

    q = sub.add_parser("query", help="Recherche hybride (fulltext + semantic).")
    q.add_argument("query")
    q.add_argument("--project", default=None)
    q.add_argument("--type", default=None)
    q.add_argument("--limit", type=int, default=5)
    q.set_defaults(func=cmd_query)

    g = sub.add_parser("grep", help="Recherche regex stricte.")
    g.add_argument("pattern")
    g.add_argument("--project", default=None)
    g.add_argument("--type", default=None)
    g.add_argument("--limit", type=int, default=20)
    g.set_defaults(func=cmd_grep)

    st = sub.add_parser("stats", help="Statistiques index.")
    st.set_defaults(func=cmd_stats)

    stale = sub.add_parser("stale", help="Detecte memoires non modifiees depuis N jours.")
    stale.add_argument("--older-than", type=int, default=90, help="Seuil en jours (defaut 90).")
    stale.add_argument("--project", default=None)
    stale.add_argument("--type", default=None)
    stale.add_argument("--limit", type=int, default=20)
    stale.set_defaults(func=cmd_stale)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
