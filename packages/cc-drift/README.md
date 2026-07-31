# cc-drift

Detect drift between your `CLAUDE.md` (or `docs/`) and the actual code.

Counts what the code really contains — routes, models, agents, tests — and
compares it against the numbers your documentation claims.

## Usage

```bash
cc-drift check                          # current directory
cc-drift check --project myapp          # a project under your workspace root
cc-drift check --all --threshold 20     # every project, 20% tolerance
cc-drift install-hook --threshold 30    # pre-commit hook
```

Exit codes: `0` no drift, `1` error, `2` drift at or above the threshold.

`install-hook` writes a `pre-commit` hook that calls `cc-drift check`, so the
binary it invokes must be on your `PATH` (`uv tool install ./packages/cc-drift`).

## Part of

[claude-code-toolkit](https://github.com/VFK00/claude-code-toolkit)
