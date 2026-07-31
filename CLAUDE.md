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

## Testing

Tests pass an explicit `home=Path("/home/alice")` rather than relying on the real
home directory, so they behave identically on any machine and in CI.
