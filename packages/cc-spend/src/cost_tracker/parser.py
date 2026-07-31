"""Parser transcripts JSONL Claude Code.

Structure d'une ligne assistant pertinente :
    {"type":"assistant","message":{"model":"...","usage":{...}},"timestamp":"...","sessionId":"..."}

Deux invariants tiennent tout le fichier :

- **Rien ne leve.** Un transcript reel melange des schemas de plusieurs versions,
  des reponses partielles et des fichiers tronques. Une ligne fautive coute cette
  ligne, jamais le fichier ni le run.
- **Rien n'est avale.** Ce qui est rejete alimente un `SkipReport` que la CLI
  affiche en fin de scan.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from cctk_core import SkipReport
from cctk_core import project_from_dirname as _project_from_dirname
from pydantic import BaseModel, ValidationError


class UsageEntry(BaseModel):
    session_id: str
    project: str
    model: str
    timestamp: datetime
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_5m: int = 0
    cache_creation_1h: int = 0
    cache_read: int = 0
    transcript_path: str


def project_from_dirname(dirname: str, *, home: Path | None = None) -> str:
    """Deduit le nom du projet depuis un dossier de session Claude Code."""
    return _project_from_dirname(dirname, home=home, workspace="Claude/projets")


def parse_line(line: str, project: str, transcript_path: str) -> UsageEntry | None:
    """Retourne l'entree d'usage d'une ligne, ou None. Ne leve jamais."""
    entry, _ = parse_line_checked(line, project, transcript_path)
    return entry


def parse_line_checked(
    line: str, project: str, transcript_path: str
) -> tuple[UsageEntry | None, str | None]:
    """Retourne `(entree, motif de rejet)`.

    Motif `None` = ligne simplement hors sujet (ligne vide, message utilisateur,
    assistant sans usage) : rien a signaler. Motif renseigne = la ligne aurait
    du compter mais son contenu est inexploitable — c'est ce qui remonte a
    l'utilisateur en fin de scan.
    """
    if not line.strip():
        return None, None
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return None, "JSON invalide"
    if not isinstance(rec, dict):
        return None, "ligne JSON qui n'est pas un objet"
    if rec.get("type") != "assistant":
        return None, None

    msg = rec.get("message") or {}
    if not isinstance(msg, dict):
        return None, "champ `message` non-objet"
    usage = msg.get("usage") or {}
    if not isinstance(usage, dict):
        return None, "champ `usage` non-objet"
    if not usage:
        return None, None

    model = msg.get("model") or "unknown"
    if not isinstance(model, str):
        return None, "champ `model` non textuel"

    ts = rec.get("timestamp")
    session_id = rec.get("sessionId") or ""
    if not ts or not session_id:
        return None, None
    if not isinstance(ts, str):
        return None, "champ `timestamp` non textuel"
    if not isinstance(session_id, str):
        return None, "champ `sessionId` non textuel"
    try:
        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None, "timestamp illisible"

    cache_creation = usage.get("cache_creation") or {}
    if not isinstance(cache_creation, dict):
        cache_creation = {}

    try:
        entry = UsageEntry(
            session_id=session_id,
            project=project,
            model=model,
            timestamp=timestamp,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_5m=cache_creation.get("ephemeral_5m_input_tokens", 0),
            cache_creation_1h=cache_creation.get("ephemeral_1h_input_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0),
            transcript_path=transcript_path,
        )
    except ValidationError:
        return None, "compteurs de tokens non numeriques"
    return entry, None


def iter_transcripts(
    base: Path, report: SkipReport | None = None
) -> Iterator[tuple[Path, str]]:
    """Enumere les transcripts JSONL sous `~/.claude/projects/<projet>/`.

    Le parcours est **recursif** : Claude Code ecrit les transcripts de
    sous-agents sous `<projet>/<session>/subagents/**/*.jsonl`, parfois trois
    niveaux plus bas (`subagents/workflows/wf_.../agent-*.jsonl`). Un glob a un
    seul niveau laissait la moitie des transcripts — les plus chers — hors du
    total, sans le dire.

    Le nom de projet vient toujours du dossier de **premier niveau** : le parent
    immediat d'un transcript de sous-agent est `subagents`, puis un UUID de
    session, jamais un projet.
    """
    try:
        project_dirs = sorted(base.iterdir())
    except OSError as exc:
        if report is not None:
            report.skip_file(f"repertoire illisible ({_reason(exc)})", str(base))
        return
    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue
        project = project_from_dirname(project_dir.name)
        yield from _walk_jsonl(project_dir, project, report)


def _walk_jsonl(
    root: Path, project: str, report: SkipReport | None
) -> Iterator[tuple[Path, str]]:
    """Descend l'arborescence d'un projet.

    `os.walk` plutot que `Path.rglob` : rglob avale les erreurs de parcours
    (repertoire sans permission) sans laisser de trace, ce qui rend un scan
    incomplet indetectable. `onerror` les remonte.
    """

    def on_error(exc: OSError) -> None:
        if report is not None:
            where = exc.filename or str(root)
            report.skip_file(f"repertoire illisible ({_reason(exc)})", str(where))

    # followlinks reste a False : une boucle de symlinks ne doit pas tourner.
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".jsonl"):
                yield Path(dirpath) / name, project


def parse_transcript(
    path: Path, project: str, report: SkipReport | None = None
) -> Iterator[UsageEntry]:
    """Parcourt un transcript ligne a ligne, en signalant ce qui est ecarte."""
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        if report is not None:
            report.skip_file(f"lecture impossible ({_reason(exc)})", str(path))
        return
    with handle:
        line_no = 0
        try:
            for line in handle:
                line_no += 1
                entry, reason = parse_line_checked(line, project, str(path))
                if entry is not None:
                    yield entry
                elif reason is not None and report is not None:
                    report.skip_entry(reason, f"{path}:{line_no}")
        except OSError as exc:  # lecture interrompue en cours de fichier
            if report is not None:
                report.skip_file(f"lecture interrompue ({_reason(exc)})", str(path))


def _reason(exc: OSError) -> str:
    return exc.strerror or exc.__class__.__name__
