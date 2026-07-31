# claude-code-toolkit

[![CI](https://github.com/VFK00/claude-code-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/VFK00/claude-code-toolkit/actions/workflows/ci.yml)

**Keep your coding agents' context honest.**

Every tool in this space measures what agents *consume* — tokens, dollars, sessions.
None measures the quality of what you *give them to read*.

A `CLAUDE.md` that lies degrades every session that loads it, silently. These tools find that.

## Tools

| Command | What it answers |
|---------|-----------------|
| `cc-drift` | Does my `CLAUDE.md` still match the code? |
| `cc-memory` | What is actually in my agent memories? |
| `cc-spend` | What did Claude Code cost, per project and model? |
| `cc-run` | Run one command across many projects, in parallel. |

`cc-drift` and `cc-memory` are the reason this exists. `cc-spend` and `cc-run` are
utilities — if you only want spend tracking, [ccusage](https://ccusage.com) does more.

## Install

```bash
uv tool install git+https://github.com/VFK00/claude-code-toolkit#subdirectory=packages/cc-drift
```

Repeat with `cc-memory`, `cc-spend`, `cc-run` as needed.

## What it looks like

A project whose `CLAUDE.md` claims eight routes and twelve tests, against code
holding three and two:

```console
$ cc-drift check --project demo-app
         demo-app (threshold 25%)
┏━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Signal ┃ Doc ┃ Code ┃ Drift % ┃ Status ┃
┡━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ routes │   8 │    3 │      62 │ DRIFT  │
│ models │   - │    2 │       - │ no doc │
│ tests  │  12 │    2 │      83 │ DRIFT  │
└────────┴─────┴──────┴─────────┴────────┘
  Docs read: CLAUDE.md
  Source files scanned: 3

$ echo $?
2
```

Exit `2` means drift at or above the threshold — enough for a pre-commit hook
or a CI step. `cc-drift install-hook` writes that hook for you.

Cost, per model, from your local transcripts:

```console
$ cc-spend scan
OK transcripts scanned: 2 | entries added: 6
Discarded: 1 entry
  - invalid JSON x1
  e.g. ~/.claude/projects/demo/session.jsonl:3 (invalid JSON)

$ cc-spend report --by model
                  Claude Code cost by model
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ model             ┃  Input ┃ Output ┃ Cache read ┃ Cost USD ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ claude-opus-4-5   │ 48,000 │ 13,600 │    192,000 │    $2.03 │
│ claude-sonnet-4-5 │ 10,000 │  1,800 │          0 │    $0.06 │
├───────────────────┼────────┼────────┼────────────┼──────────┤
│ TOTAL             │        │        │            │    $2.08 │
└───────────────────┴────────┴────────┴────────────┴──────────┘
```

Note the second block of the scan. One line was unreadable, so it is **counted
and shown**, with its reason and where to find it. A tool that quietly drops
part of its input and exits `0` reports a false result — see below.

## Why this exists

Real findings from a single audit session on a 16-project workspace:

- a `CLAUDE.md` claiming **25 scripts** when 24 existed
- a local LLM stack documented as live, **dead for 28 days**
- **6 memory files** describing 8 deleted binaries, still injected on recall
- a drift detector reporting **22 models where 11 existed** — this one was in
  an early version of `cc-drift` itself

Each costs context and produces wrong answers, on every session, until someone
finds it by hand.

That last item is why two rules govern every ingestion path here:

- **Never raise on one bad entry.** A malformed line costs that line, never the
  file, never the run.
- **Never discard in silence.** Whatever is skipped is reported with its reason.

They were not written upfront. They come from a stress test on a real corpus,
where `cc-spend` was found to be skipping **53 % of transcripts** — subagent
runs live deeper in the tree than the scanner looked — while printing `OK` and
exiting `0`.

## Related

[panelize-code](https://github.com/VFK00/panelize-code) — config-driven terminal
dashboards. Same author, separate tool.

## License

MIT
