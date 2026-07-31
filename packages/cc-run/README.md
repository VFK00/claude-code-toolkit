# cc-run

Run a command across many projects in parallel.

Detects each project's stack from its lockfile/manifest and maps common
presets (test, lint, build, status) to the right command.

## Usage

```bash
cc-run list                                     # detected projects + stack
cc-run run "git status -s"                      # run a free-form command
cc-run --projects app1,app2 run "pytest"        # limit to named projects
cc-run --match node run "pnpm test"             # filter by stack kind
cc-run preset test                              # pytest | pnpm test, per stack
cc-run preset lint
cc-run preset status
cc-run --concurrency 2 --timeout 900 preset build
```

`--projects`, `--match`, `--concurrency` and `--timeout` are options of the
main command, so they go before the subcommand.

`--timeout` bounds real elapsed time: the command runs in its own process
group, and the whole group is signalled (`SIGTERM`, then `SIGKILL`) when the
delay expires — killing the shell alone would leave the actual command running.
A timed-out run reports exit code `124`.

Exit codes: `0` all OK, `1` no project detected, `2` at least one failure.

## Part of

[claude-code-toolkit](https://github.com/VFK00/claude-code-toolkit)
