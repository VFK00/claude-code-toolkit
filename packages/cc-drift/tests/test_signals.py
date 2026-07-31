from pathlib import Path

import pytest

from doc_drift.signals import (
    analyze,
    compute_drifts,
    extract_code_signals,
    extract_doc_signals,
    iter_source_files,
)


def make_project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "api.py").write_text(
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/a")
def a(): ...

@router.post("/b")
def b(): ...

router.get("/c")
"""
    )
    (tmp_path / "app" / "models.py").write_text(
        """
class UserModel(Base):
    pass

class OrderBase(Base):
    pass
"""
    )
    (tmp_path / "schema.prisma").write_text(
        """
model Post {
  id Int @id
}

model Comment {
  id Int @id
}
"""
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        """
def test_a(): ...
def test_b(): ...
def test_c(): ...
"""
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "agent-x.md").touch()
    (tmp_path / "agents" / "agent-y.md").touch()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.py").write_text("def test_ignore(): ...")
    return tmp_path


def test_iter_source_files_skips_ignore_dirs(tmp_path):
    make_project(tmp_path)
    files = iter_source_files(tmp_path)
    assert not any("node_modules" in str(f) for f in files)


def test_extract_code_signals(tmp_path):
    make_project(tmp_path)
    sig = extract_code_signals(tmp_path)
    assert sig.routes >= 3
    assert sig.models >= 2 + 2  # 2 Python + 2 Prisma
    assert sig.tests == 3
    assert sig.agents == 2


def test_extract_doc_signals_inline(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# Projet\n\nStack : **3 routes**, **4 modeles**, **2 agents**, **10 tests**\n"
    )
    doc, found = extract_doc_signals(tmp_path)
    assert doc.routes == 3
    assert doc.models == 4
    assert doc.agents == 2
    assert doc.tests == 10
    assert "CLAUDE.md" in found[0]


def test_extract_doc_signals_list(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# P\n\n- Routes API : 5\n- Modeles : 6\n- Agents : 1\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.routes == 5
    assert doc.models == 6
    assert doc.agents == 1


def test_extract_doc_signals_missing(tmp_path):
    doc, found = extract_doc_signals(tmp_path)
    assert doc.routes is None
    assert found == []


def test_extract_doc_signals_multi_source(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("routes: **2 routes**")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("mod : **5 modeles**")
    doc, found = extract_doc_signals(tmp_path)
    assert doc.routes == 2
    assert doc.models == 5
    assert len(found) == 2


def test_compute_drifts_none():
    from doc_drift.signals import CodeSignals, DocSignals

    drifts = compute_drifts(CodeSignals(routes=10, models=5), DocSignals(routes=10, models=5))
    assert drifts == []


def test_compute_drifts_triggers():
    from doc_drift.signals import CodeSignals, DocSignals

    drifts = compute_drifts(
        CodeSignals(routes=20, models=5), DocSignals(routes=10, models=5), threshold=25
    )
    assert any(d[0] == "routes" for d in drifts)


def test_compute_drifts_skips_none_doc():
    from doc_drift.signals import CodeSignals, DocSignals

    drifts = compute_drifts(CodeSignals(routes=100), DocSignals(routes=None))
    assert drifts == []


def test_compute_drifts_both_zero_no_false_positive():
    from doc_drift.signals import CodeSignals, DocSignals

    drifts = compute_drifts(CodeSignals(), DocSignals(routes=0))
    assert drifts == []


def test_analyze_integration(tmp_path):
    make_project(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("**100 routes**, **2 agents**")
    result = analyze(tmp_path, threshold=20.0)
    # 100 vs 3 -> gros drift
    drift_labels = {d[0] for d in result.drifts}
    assert "routes" in drift_labels
    assert "agents" not in drift_labels  # code:2 doc:2 -> pas de drift
    assert result.has_drift is True


def test_analyze_no_doc_no_drift(tmp_path):
    make_project(tmp_path)
    result = analyze(tmp_path)
    assert result.has_drift is False


def test_route_rx_sqlalchemy_no_false_positive(tmp_path):
    """TODO-006 : l'alternative tRPC `.query(`/`.mutation(`/`.subscription(` n'etait
    ancree a rien et matchait aussi `session.query()` SQLAlchemy. Tout projet
    Python utilisant SQLAlchemy recevait un faux drift (routes 0 doc / N code)."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "repository.py").write_text(
        """
from sqlalchemy.orm import Session


def get_active_users(session: Session):
    return session.query(User).filter_by(active=True).all()


def get_orders(session: Session):
    return session.query(Order).all()


def count_orders(session: Session):
    return session.query(Order).count()
"""
    )
    sig = extract_code_signals(tmp_path)
    assert sig.routes == 0


def test_route_rx_trpc_public_procedure_detectee(tmp_path):
    """Le vrai cas tRPC (fichier .ts) doit continuer a etre detecte."""
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "router.ts").write_text(
        """
export const appRouter = router({
  list: publicProcedure.query(({ ctx }) => ctx.db.user.findMany()),
});
"""
    )
    sig = extract_code_signals(tmp_path)
    assert sig.routes == 1


def test_route_rx_trpc(tmp_path):
    (tmp_path / "routers").mkdir()
    (tmp_path / "routers" / "user.ts").write_text(
        """
export const userRouter = t.router({
  list: publicProcedure.query(({ ctx }) => ctx.db.user.findMany()),
  create: publicProcedure.input(z.object({})).mutation(({ input }) => {}),
  watch: publicProcedure.subscription(() => {}),
});
"""
    )
    sig = extract_code_signals(tmp_path)
    assert sig.routes == 3


def test_route_rx_nextjs_app_router(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "route.ts").write_text(
        """
export async function GET(request: Request) { return new Response(); }
export const POST = async () => new Response();
export function DELETE() { return new Response(); }
"""
    )
    sig = extract_code_signals(tmp_path)
    assert sig.routes == 3


# --- Regressions comptage (2026-07-28) ---


def test_prisma_models_comptes_une_seule_fois(tmp_path):
    """MODEL_RX matche deja `model X {` : l'ajouter au comptage .prisma doublait."""
    (tmp_path / "schema.prisma").write_text(
        "model User {\n  id Int @id\n}\n\nmodel Post {\n  id Int @id\n}\n"
    )
    assert extract_code_signals(tmp_path).models == 2


@pytest.mark.parametrize("nom", ["latest.ts", "contest.js", "protest.jsx", "fastest.ts"])
def test_fichier_non_test_malgre_sous_chaine_test(tmp_path, nom):
    """`"test" in stem` comptait latest/contest/protest comme suites de tests."""
    (tmp_path / nom).write_text("describe('x', () => {})\nit('y', () => {})\n")
    assert extract_code_signals(tmp_path).tests == 0


@pytest.mark.parametrize("nom", ["foo.test.ts", "foo.spec.ts", "bar_test.py", "test_bar.py"])
def test_conventions_de_nommage_reconnues(tmp_path, nom):
    contenu = (
        "def test_a():\n    pass\ndef test_b():\n    pass\n"
        if nom.endswith(".py")
        else "describe('x', () => {})\nit('y', () => {})\n"
    )
    (tmp_path / nom).write_text(contenu)
    assert extract_code_signals(tmp_path).tests == 2


def test_dossier_tests_compte_quel_que_soit_le_nom_de_fichier(tmp_path):
    d = tmp_path / "tests"
    d.mkdir()
    (d / "helpers.py").write_text("def test_a():\n    pass\ndef test_b():\n    pass\n")
    assert extract_code_signals(tmp_path).tests == 2


def test_tests_async_sont_comptes(tmp_path):
    """`async def test_` est la forme normale avec pytest-asyncio.

    La regex n'acceptait que `def test_` : tout projet a tests asynchrones
    etait sous-compte, et l'ecart signale a tort comme un drift de doc.
    """
    (tmp_path / "test_async.py").write_text(
        "async def test_a() -> None:\n    pass\n"
        "async def test_b() -> None:\n    pass\n"
        "def test_c() -> None:\n    pass\n"
    )
    assert extract_code_signals(tmp_path).tests == 3
