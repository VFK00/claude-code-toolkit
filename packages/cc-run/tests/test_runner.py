import asyncio
import os
import sys
import time

import pytest

from orchestrator.runner import run_many, run_one


async def _wait_dead(pid: int, deadline_s: float = 5.0) -> bool:
    """True des que `pid` n'existe plus (le petit-fils est reparente puis reape)."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_run_one_success(tmp_path):
    r = await run_one("proj", tmp_path, "echo hello")
    assert r.ok is True
    assert "hello" in r.stdout
    assert r.exit_code == 0


@pytest.mark.asyncio
async def test_run_one_failure(tmp_path):
    r = await run_one("proj", tmp_path, "false")
    assert r.ok is False
    assert r.exit_code != 0


@pytest.mark.asyncio
async def test_run_one_timeout(tmp_path):
    cmd = f"{sys.executable} -c 'import time; time.sleep(10)'"
    r = await run_one("proj", tmp_path, cmd, timeout=0.5)
    assert r.exit_code == 124
    assert "TIMEOUT" in r.stderr


@pytest.mark.asyncio
async def test_run_many_concurrency(tmp_path):
    jobs = [("p1", tmp_path, "echo a"), ("p2", tmp_path, "echo b"), ("p3", tmp_path, "false")]
    results = await run_many(jobs, concurrency=2)
    assert len(results) == 3
    assert sum(1 for r in results if r.ok) == 2


# --- Defaut 2 : le timeout doit tuer le groupe de processus, pas seulement le shell ---


@pytest.mark.asyncio
async def test_run_one_timeout_borne_le_temps_reel(tmp_path):
    """`sh -c` fork un descendant : tuer le shell seul laisse tourner la commande."""
    cmd = f"{sys.executable} -c 'import time; time.sleep(30)' & wait"
    start = time.monotonic()

    r = await run_one("proj", tmp_path, cmd, timeout=1.0)

    elapsed = time.monotonic() - start
    assert r.exit_code == 124
    assert elapsed < 15, f"timeout non applique : {elapsed:.1f}s de temps reel"
    assert r.duration_s < 15


@pytest.mark.asyncio
async def test_run_one_timeout_tue_le_petit_fils(tmp_path):
    pidfile = tmp_path / "child.pid"
    script = tmp_path / "child.py"
    script.write_text(
        "import os, sys, time, pathlib\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n"
    )
    cmd = f"{sys.executable} {script} {pidfile} & wait"

    r = await run_one("proj", tmp_path, cmd, timeout=1.5)

    assert r.exit_code == 124
    pid = int(pidfile.read_text())
    assert await _wait_dead(pid), f"petit-fils {pid} toujours vivant apres le timeout"


@pytest.mark.asyncio
async def test_run_one_timeout_escalade_en_sigkill(tmp_path):
    """Un descendant qui ignore SIGTERM doit quand meme etre coupe."""
    pidfile = tmp_path / "tetu.pid"
    script = tmp_path / "tetu.py"
    script.write_text(
        "import os, signal, sys, time, pathlib\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n"
    )
    cmd = f"{sys.executable} {script} {pidfile} & wait"

    r = await run_one("proj", tmp_path, cmd, timeout=1.5)

    assert r.exit_code == 124
    pid = int(pidfile.read_text())
    assert await _wait_dead(pid), f"petit-fils {pid} survit au timeout (SIGTERM ignore)"


@pytest.mark.asyncio
async def test_run_one_cwd(tmp_path):
    (tmp_path / "marker").touch()
    r = await run_one("proj", tmp_path, "ls marker")
    assert r.ok is True
    assert "marker" in r.stdout
