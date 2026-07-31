# cc-memory

Search across Claude Code agent memories — fulltext, and semantic when an
embeddings backend is available.

Reads `~/.claude/projects/*/memory/*.md`, indexes them in SQLite, and scores
matches with a BM25-lite fulltext ranker, optionally fused with embeddings.

## Usage

```bash
cc-memory index                             # build/update the index
cc-memory --no-embed index                  # fulltext-only, skip embeddings
cc-memory query "auth jwt" --type project --limit 10
cc-memory grep "ADR-\d+" --type reference   # strict regex search
cc-memory stats                             # index counts by project/type
cc-memory stale --older-than 90             # memories untouched in 90+ days
```

`--no-embed` is an option of the main command, so it goes before the
subcommand.

Falls back to fulltext-only automatically when no embeddings backend is
reachable.

A memory file that cannot be read, or whose YAML frontmatter is not a mapping,
is skipped and reported at the end — the rest of the index still gets built and
committed.

## Part of

[claude-code-toolkit](https://github.com/VFK00/claude-code-toolkit)
