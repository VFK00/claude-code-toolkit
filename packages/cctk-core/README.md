# cctk-core

Shared internal package for `claude-code-toolkit`. It has no CLI and no
user-facing entry point — just the plumbing the other four packages need.

## What's here

- **Path resolution** (`paths.py`) — `project_from_dirname`, `transcripts_dir`,
  `workspace_root`. Claude Code encodes a working directory into a session
  folder name by replacing `/` with `-`; deriving that prefix from
  `Path.home()` (never hardcoding it) is what makes these tools work on a
  machine other than their author's.
- **Cache location** (`cache.py`) — `cache_db(name)` resolves
  `~/.cache/cctk-<name>.db`, creating the parent directory if needed.
- **`SkipReport`** (`report.py`) — counts and classifies whatever an ingestion
  path discards (a malformed line, an unreadable file...), and renders it for
  display at the end of a run.

## Why it exists

`cc-drift`, `cc-run`, `cc-spend` and `cc-memory` all need to resolve the same
paths and must never discard input in silence. Before this package, that
logic was duplicated across four tools: a fix in one place didn't reach the
others, and the "never hardcode the home prefix" bug that broke portability
had to be found and fixed four times. `cctk-core` holds it once.

It also carries the two ingestion rules documented in the repo's `CLAUDE.md`:
never raise on a single bad entry, and never discard anything without
recording it in a `SkipReport` that the caller prints — the mechanism behind
every tool's "never silently drop data" promise.

## Not installable on its own

This package ships no binary and stays dependency-free by design. It's a
dependency of the four tools above, not a tool itself — installing it alone
gets you a library with nothing to call it.

## Part of

[claude-code-toolkit](https://github.com/VFK00/claude-code-toolkit)
