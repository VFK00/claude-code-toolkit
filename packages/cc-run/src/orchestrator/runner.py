"""Exec parallele asyncio + collecte resultats."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

# Delai laisse au groupe pour sortir sur SIGTERM avant le SIGKILL.
GRACE_S = 0.5


@dataclass
class RunResult:
    name: str
    path: Path
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    """Signale tout le groupe. Absent ou deja mort : rien a faire."""
    with contextlib.suppress(OSError):
        os.killpg(pgid, sig)


async def _kill_group(proc: asyncio.subprocess.Process) -> None:
    """Termine le groupe de processus, pas seulement le shell.

    `proc` est `/bin/sh -c "<cmd>"` : tuer ce seul PID laisse le petit-fils
    (la vraie commande) tourner et tenir les pipes ouverts — `communicate()`
    reste alors bloque jusqu'a la fin naturelle du petit-fils. Avec
    `start_new_session=True`, le shell est leader d'un groupe dedie dont le
    pgid vaut son pid : on signale le groupe entier.
    """
    pgid = proc.pid
    _signal_group(pgid, signal.SIGTERM)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=GRACE_S)
    # SIGKILL inconditionnel : le shell peut avoir rendu la main alors qu'un
    # descendant ignore SIGTERM et tient toujours les pipes. Attendre la sortie
    # du seul shell laisserait cet orphelin tourner — le defaut qu'on corrige.
    _signal_group(pgid, signal.SIGKILL)
    await proc.wait()


async def run_one(name: str, path: Path, command: str, timeout: float = 600.0) -> RunResult:
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Groupe de processus dedie : condition necessaire pour que le
            # timeout coupe reellement les descendants.
            start_new_session=True,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode or 0
        except TimeoutError:
            await _kill_group(proc)
            return RunResult(
                name=name,
                path=path,
                command=command,
                exit_code=124,
                stdout="",
                stderr=f"TIMEOUT apres {timeout}s",
                duration_s=time.monotonic() - start,
            )
        return RunResult(
            name=name,
            path=path,
            command=command,
            exit_code=exit_code,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
            duration_s=time.monotonic() - start,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return RunResult(
            name=name,
            path=path,
            command=command,
            exit_code=1,
            stdout="",
            stderr=f"Erreur exec : {exc}",
            duration_s=time.monotonic() - start,
        )


async def run_many(
    jobs: list[tuple[str, Path, str]],
    concurrency: int = 4,
    timeout: float = 600.0,
) -> list[RunResult]:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(name: str, path: Path, cmd: str) -> RunResult:
        async with sem:
            return await run_one(name, path, cmd, timeout=timeout)

    return await asyncio.gather(*(guarded(n, p, c) for n, p, c in jobs))
