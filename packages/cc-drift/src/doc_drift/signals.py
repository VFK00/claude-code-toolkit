"""Extraction de signaux code et doc.

Signaux code : nombre de routes, modeles, agents, tests.
Signaux doc : chiffres extraits de CLAUDE.md / docs/ (regex sur lignes `- Label : N`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# --- Regex code ---
# Couvre :
#   - FastAPI/Flask/Express : @router.get, @app.post, router.get(, app.post(
#   - Next.js App Router handlers : export const GET|POST|PUT|DELETE|PATCH
#   - Hono/Koa : app.get(, router.post(
ROUTE_RX = re.compile(
    r"@(?:router|app)\.(?:get|post|put|delete|patch|options|head|route|api_route)\b"
    r"|(?:router|app|t)\.(?:get|post|put|delete|patch)\s*\("
    r"|^export\s+(?:async\s+)?(?:const|function)\s+(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b",
    re.MULTILINE,
)

# tRPC (v10+) : .query(, .mutation(, .subscription( — non ancre a un identifiant
# de routeur precis (`publicProcedure`, `t.procedure`, etc varient trop d'un
# projet a l'autre). Sans discriminant supplementaire, cette alternative
# matche aussi `session.query()` (SQLAlchemy) ou tout `.query(`/`.mutation(`
# metier ecrit en Python. tRPC n'existe qu'en TypeScript/JavaScript : on limite
# donc cette regex aux fichiers de ces extensions (TRPC_EXTENSIONS plus bas),
# jamais aux fichiers Python.
TRPC_ROUTE_RX = re.compile(r"\.(?:query|mutation|subscription)\s*\(")

TRPC_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
MODEL_RX = re.compile(
    r"^model\s+\w+\s*\{|class\s+\w+\s*\(.*(Model|Base|Entity|Schema|Table)|@Entity",
    re.MULTILINE,
)
# `async def test_` est la forme normale sous pytest-asyncio : l'omettre
# sous-compte tout projet a tests asynchrones, et l'ecart remonte a tort en drift.
TEST_RX = re.compile(
    r"^\s*(?:async\s+)?def\s+test_|^\s*it\(|^\s*test\(|^\s*describe\(", re.MULTILINE
)

# `model X {` cote Prisma, tolerant a l'accolade rejetee a la ligne suivante.
PRISMA_MODEL_RX = re.compile(r"^model\s+\w+", re.MULTILINE)

# Dossiers qui contiennent des tests par convention.
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "e2e"}


def is_test_file(path: Path, root: Path) -> bool:
    """Conventions reelles, pas une sous-chaine.

    `"test" in path.stem` matchait `latest`, `contest`, `protest`, `fastest` :
    un `latest.ts` contenant `describe(`/`it(` etait compte comme suite de tests.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:  # pragma: no cover - path hors root
        parts = path.parts
    if any(part in TEST_DIRS for part in parts[:-1]):
        return True
    stem = path.stem
    return (
        stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith(".test")
        or stem.endswith(".spec")
        or stem in {"test", "tests"}
    )


@dataclass
class CodeSignals:
    routes: int = 0
    models: int = 0
    agents: int = 0
    tests: int = 0
    files_scanned: int = 0


@dataclass
class DocSignals:
    routes: int | None = None
    models: int | None = None
    agents: int | None = None
    tests: int | None = None


@dataclass
class DriftResult:
    project: Path
    code: CodeSignals
    doc: DocSignals
    drifts: list[tuple[str, int | None, int, float]] = field(default_factory=list)
    docs_found: list[str] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.drifts)


STACK_EXTENSIONS = {
    ".py": "python",
    ".ts": "node",
    ".tsx": "node",
    ".js": "node",
    ".jsx": "node",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".java": "java",
    ".php": "php",
}

IGNORE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "coverage",
    "archives",
    "target",
}


def iter_source_files(root: Path) -> list[Path]:
    """Parcourt le projet en ignorant dossiers standard."""
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part in IGNORE_DIRS or part.startswith(".") for part in parts):
            continue
        if path.suffix in STACK_EXTENSIONS or path.suffix == ".prisma":
            results.append(path)
    return results


def extract_code_signals(root: Path) -> CodeSignals:
    sig = CodeSignals()
    files = iter_source_files(root)
    sig.files_scanned = len(files)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sig.routes += len(ROUTE_RX.findall(text))
        if path.suffix in TRPC_EXTENSIONS:
            sig.routes += len(TRPC_ROUTE_RX.findall(text))
        # MODEL_RX contient deja `^model \w+ {` : l'appliquer AUSSI a un .prisma
        # comptait chaque modele deux fois et fabriquait du drift sur tout projet
        # Prisma. Un schema = une seule regex, la plus permissive des deux.
        if path.suffix == ".prisma":
            sig.models += len(PRISMA_MODEL_RX.findall(text))
        else:
            sig.models += len(MODEL_RX.findall(text))
        if is_test_file(path, root):
            sig.tests += len(TEST_RX.findall(text))
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        sig.agents = len(list(agents_dir.glob("*.md")))
    return sig


DOC_LINE_RX = {
    "routes": re.compile(r"(?im)^\s*[-*]\s*(routes?(?:\s*api)?|endpoints?)\s*[:\-]?\s*(\d+)"),
    "models": re.compile(r"(?im)^\s*[-*]\s*(mod[ée]l(?:e|es|s)?|mod[ée]les?)\s*[:\-]?\s*(\d+)"),
    "agents": re.compile(r"(?im)^\s*[-*]\s*(agents?)\s*[:\-]?\s*(\d+)"),
    "tests": re.compile(r"(?im)^\s*[-*]\s*(tests?)\s*[:\-]?\s*(\d+)"),
}

# Formulations telegraphiques compactes : `**30 agents**` (tout en gras) ou `**30** agents`.
def _inline(word: str) -> re.Pattern[str]:
    return re.compile(
        rf"\*\*(\d+)\s+{word}\*\*|\*\*(\d+)\*\*\s*{word}",
        re.IGNORECASE,
    )


DOC_INLINE_RX = {
    "routes": _inline(r"(?:routes?|endpoints?)"),
    "models": _inline(r"mod[ée]les?"),
    "agents": _inline(r"agents?"),
    "tests": _inline(r"tests?"),
}


def extract_doc_signals(root: Path) -> tuple[DocSignals, list[str]]:
    doc = DocSignals()
    found: list[str] = []
    candidates = [
        root / "CLAUDE.md",
        root / "README.md",
        root / "docs" / "architecture.md",
        root / "docs" / "changelog.md",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        found.append(str(candidate.relative_to(root)))
        text = candidate.read_text(encoding="utf-8", errors="replace")
        for key, rx in DOC_LINE_RX.items():
            current = getattr(doc, key)
            if current is None:
                m = rx.search(text)
                if m:
                    setattr(doc, key, int(m.group(2)))
        for key, rx in DOC_INLINE_RX.items():
            current = getattr(doc, key)
            if current is None:
                m = rx.search(text)
                if m:
                    value = m.group(1) or m.group(2)
                    setattr(doc, key, int(value))
    return doc, found


def compute_drifts(
    code: CodeSignals, doc: DocSignals, threshold: float = 25.0
) -> list[tuple[str, int | None, int, float]]:
    """Retourne (label, doc_value, code_value, pct_drift) pour chaque signal en drift."""
    drifts: list[tuple[str, int | None, int, float]] = []
    for label, code_v in [
        ("routes", code.routes),
        ("models", code.models),
        ("agents", code.agents),
        ("tests", code.tests),
    ]:
        doc_v = getattr(doc, label)
        if doc_v is None:
            continue
        if doc_v == 0 and code_v == 0:
            continue
        base = max(doc_v, code_v, 1)
        pct = abs(code_v - doc_v) / base * 100
        if pct >= threshold:
            drifts.append((label, doc_v, code_v, pct))
    return drifts


def analyze(root: Path, threshold: float = 25.0) -> DriftResult:
    code = extract_code_signals(root)
    doc, found = extract_doc_signals(root)
    drifts = compute_drifts(code, doc, threshold=threshold)
    return DriftResult(project=root, code=code, doc=doc, drifts=drifts, docs_found=found)
