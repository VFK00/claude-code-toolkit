# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A `uv` workspace holding four CLI tools plus a shared internal package.
Each tool ships its own binary; `cctk-core` holds what would otherwise be duplicated.

```
packages/
  cctk-core/   # paths, cache location, skip reporting — stdlib only, no runtime deps
  cc-drift/    # documentation drift detection
  cc-memory/   # agent memory search
  cc-spend/    # cost aggregation
  cc-run/      # parallel execution
```

## Commands

```bash
uv sync --all-packages --all-extras            # install everything
uv run pytest packages/ -v      # full suite
uv run ruff check .             # lint
uv run mypy packages/*/src      # types (strict)
uv run cc-drift --help          # any tool, without installing
```

## Conventions

- Python **3.12+**, `src/` layout, **hatchling** build backend.
- CLIs use **argparse** from the stdlib — no click, no typer.
- **pydantic v2** for models, **rich** for output.
- Coverage gate: **70 %** per package.
- `ruff` and `mypy --strict` must pass before any commit.
- `cctk-core` stays **dependency-free**. Anything needing a third-party package
  belongs in a tool, not the shared core.

## Path resolution — read before touching `cctk-core`

Claude Code encodes the working directory into session folder names, replacing
`/` with `-`: `/home/alice/code/app` becomes `-home-alice-code-app`.

`project_from_dirname` derives that prefix from `Path.home()`. **Never hardcode it** —
that was the bug that made two of these tools unusable outside their author's machine.

The same rule applies to the **workspace** — the folder projects are grouped under.
It is declared through `$CCTK_WORKSPACE` (or an explicit argument), never guessed:

```bash
export CCTK_WORKSPACE=Projets   # -> ~/Projets is the scan root
```

Undeclared, the workspace is empty and the root is the home directory. That scans
wider than needed, but it is true on every machine. The previous default —
`Claude/projets`, hardcoded — survived a workspace move and left `cc-run list`
reporting **zero projects out of twenty-one, exiting `0`**. A wide scan is visible;
a root that does not exist is not.

`scan_projects` also stops enumerating category names. A directory carrying no stack
marker whose children carry one is a category, and gets descended into. Hardcoding
`{clients, outils}` made `produits/` — four live projects — report as a single row.

The fallback deliberately does not translate dashes back into slashes: in a folder
name, a dash is indistinguishable from a separator, and guessing produces wrong output.

Transcripts live **deeper than one level**: subagent runs are written to
`<project>/<session>/subagents/**/*.jsonl`. Any discovery must recurse, and the
project name always comes from the **top-level** directory — the immediate parent
of a subagent transcript is `subagents`, then a session UUID.

## Ingesting untrusted files

Transcripts and memory files are written by other programs, across schema
versions, and may be truncated. Two rules apply to every ingestion path:

- **Never raise on one bad entry.** A malformed line costs that line, never the
  file, never the run. Commit per file so an incident later in the run cannot
  undo what is already indexed.
- **Never discard in silence.** Whatever is skipped goes into a `SkipReport`
  (`cctk-core`) with its reason, and is printed at the end of the command.
  A tool that quietly drops half its input and exits `0` reports a false result.

## Reinstalling after a `cctk-core` change

`uv` caches built wheels by version. `cctk-core` never changes version, so
`uv tool install --force` happily reinstalls the tools **against the previously
built socle** — the source is right, the binary is stale, and nothing warns you.
Symptom: a fix verified by `uv run` does not appear in the installed CLI.

```bash
uv cache clean cctk-core
uv tool install --force --reinstall ./packages/cc-run   # same for the other three
```

## Pricing data

`cc-spend` prices from a hardcoded table (`pricing.py`). It is a **dated snapshot**,
not a live source — re-check it against
[the official pricing page](https://platform.claude.com/docs/en/about-claude/pricing)
whenever a model ships. Two failure modes, and only the first is visible:

- **Unknown model** → `resolve` returns `None`, the entry costs $0, and the model is
  listed under "Not priced" at the end of `cc-spend report`. Visible.
- **Wrong price for a known model** → a total that looks plausible and is not.
  Silent. The table once priced Opus 4.x at the retired 4.1 rates ($15/$75 instead
  of $5/$25) and Haiku 4.5 at Haiku 3.5's.

`resolve` deliberately does **not** fall back to prefix matching: `claude-opus-4-9`
starts with `claude-opus-4`, whose grid is the retired one. An unrecognized model
must surface in "Not priced", where it is fixable — never be guessed.

Models whose price changes on an announced date live in `SCHEDULED` (currently
Sonnet 5, introductory rate through 2026-08-31). Cost is computed from the entry's
own timestamp, so a report on a past month is not recomputed at today's rate.

## Testing

Tests pass an explicit `home=Path("/home/alice")` rather than relying on the real
home directory, so they behave identically on any machine and in CI.
