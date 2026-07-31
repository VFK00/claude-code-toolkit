# cc-spend

Aggregate Claude Code costs — by project, session, and model — from local
transcripts.

Reads `~/.claude/projects/**/*.jsonl` directly, no custom hook required.
The walk is recursive, so subagent transcripts
(`<project>/<session>/subagents/**/*.jsonl`) count too — they are charged to
the project they belong to and to their parent session. Results are cached in
SQLite so scans stay incremental, with one commit per file: an unreadable
transcript never costs the work already indexed.

Unparsable lines are skipped, counted, and listed at the end of the scan rather
than aborting it.

## Usage

```bash
cc-spend scan                                 # index new/changed transcripts
cc-spend scan --force                         # full re-scan
cc-spend report --by project                  # cost per project
cc-spend report --by model --since 7d
cc-spend report --by session --project myapp --top 10
cc-spend daily --since 30d                    # daily trend with ASCII bars
cc-spend anomalies --since 30d                # sessions with abnormal cost/cache/output
cc-spend budget --daily 500 --monthly 10000   # threshold alerts (exit 2 if over)
cc-spend export --format csv -o costs.csv
```

`budget` returns exit code `2` on threshold breach, `0` otherwise.

## Part of

[claude-code-toolkit](https://github.com/VFK00/claude-code-toolkit)
