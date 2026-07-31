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

## Why drift matters

Real findings from a single audit session on a 16-project workspace:

- a `CLAUDE.md` claiming **25 scripts** when 24 existed
- a local LLM stack documented as live, **dead for 28 days**
- **6 memory files** describing 8 deleted binaries, still injected on recall
- a drift detector reporting **22 Prisma models where 11 existed**

Each of these costs context and produces wrong answers, on every session, until
someone finds them by hand.

## Related

[panelize-code](https://github.com/VFK00/panelize-code) — config-driven terminal
dashboards. Same author, separate tool.

## License

MIT
