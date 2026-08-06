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
    # Deux `it(` plutot que `describe(` + `it(` : ce test porte sur la
    # reconnaissance du NOM de fichier, pas sur le comptage. Le `describe(`
    # n'est plus compte comme un cas (cf. test_describe_est_un_groupe_pas_un_test).
    contenu = (
        "def test_a():\n    pass\ndef test_b():\n    pass\n"
        if nom.endswith(".py")
        else "it('x', () => {})\nit('y', () => {})\n"
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


# --- Comptages ecrits en gras -------------------------------------------------
# La doctrine de redaction VFK impose « **Gras** = metriques cles ». Les regex
# d'origine n'acceptaient que la forme nue (`- Tests : 931`) ou `**5 agents**` :
# elles rataient donc TOUTES les lignes reellement ecrites. Mesure du 2026-08-06
# sur `cc-drift check --all` : 36 signaux « no doc », aucune valeur lue, sur
# l'ensemble du workspace. L'outil ne pouvait structurellement rien signaler.


def test_valeur_en_gras_suivie_de_precisions(tmp_path):
    """`- Tests : **931 tests Vitest / 108 fichiers**` — forme relevee en usage."""
    (tmp_path / "CLAUDE.md").write_text(
        "- Tests : **931 tests Vitest / 108 fichiers** (`pnpm test`, ~3,5 s)\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.tests == 931


def test_label_et_valeur_tous_deux_dans_le_gras(tmp_path):
    """`- **Modeles/Tables : 11** (...)` — le gras englobe label ET valeur."""
    (tmp_path / "CLAUDE.md").write_text(
        "- **Modeles/Tables : 11** (Site, Audit, Score, Finding)\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.models == 11


def test_label_nu_puis_valeur_en_gras(tmp_path):
    """`- Routes API : **45 fichiers ...**` — premier nombre apres le label."""
    (tmp_path / "CLAUDE.md").write_text(
        "- Routes API : **45 fichiers `route.ts` / 53 handlers HTTP**\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.routes == 45


def test_formes_nues_restent_lues(tmp_path):
    """Non-regression : l'assouplissement ne casse pas l'existant."""
    (tmp_path / "CLAUDE.md").write_text(
        "- Routes : 5\n- Modeles : 6\n- Agents : 1\n- Tests : 12\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert (doc.routes, doc.models, doc.agents, doc.tests) == (5, 6, 1, 12)


def test_ligne_sans_nombre_ne_produit_pas_de_valeur(tmp_path):
    """Un renvoi n'est pas un comptage : mieux vaut `no doc` qu'un faux chiffre."""
    (tmp_path / "CLAUDE.md").write_text(
        "- Tests : voir `docs/architecture.md`\n- Modeles : cf. schema Prisma\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.tests is None
    assert doc.models is None


def test_annee_dans_le_label_nest_pas_prise_pour_un_comptage(tmp_path):
    """`- Tests (refonte 2026) : **40 tests**` doit donner 40, pas 2026."""
    (tmp_path / "CLAUDE.md").write_text("- Tests (refonte 2026) : **40 tests**\n")
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.tests == 40


# --- Bruit cote code ----------------------------------------------------------


def test_methodes_de_map_et_set_ne_sont_pas_des_routes(tmp_path):
    """`t.delete(` / `t.get(` sur une Map ne sont pas des routes HTTP.

    Mesure sur une application Next.js : les 10 occurrences captees par `t\\.`
    etaient 10 faux positifs (Map/Set, dont 5 dans du code genere Prisma).
    """
    (tmp_path / "app.ts").write_text(
        "const t = new Map()\nt.delete('a')\nt.get('b')\n"
        "const seen = new Set()\nseen.delete('c')\n"
    )
    assert extract_code_signals(tmp_path).routes == 0


def test_routes_express_et_next_restent_comptees(tmp_path):
    """Non-regression : les vraies routes restent detectees."""
    (tmp_path / "server.ts").write_text("app.get('/a', h)\nrouter.post('/b', h)\n")
    (tmp_path / "route.ts").write_text(
        "export async function GET() {}\nexport const POST = h\n"
    )
    assert extract_code_signals(tmp_path).routes == 4


def test_code_genere_est_ignore(tmp_path):
    """`src/generated/` (client Prisma) n'est pas du code du projet."""
    gen = tmp_path / "src" / "generated" / "prisma"
    gen.mkdir(parents=True)
    (gen / "Audit.ts").write_text("export async function GET() {}\nt.delete('x')\n")
    (tmp_path / "src").joinpath("vrai.ts").write_text("export async function POST() {}")
    sig = extract_code_signals(tmp_path)
    assert sig.routes == 1
    assert sig.files_scanned == 1


# --- Ecart affiche sous le seuil ---------------------------------------------


def test_drift_pct_mesure_l_ecart_relatif():
    """L'ecart se rapporte au plus grand des deux, borne a 1 pour eviter /0."""
    from doc_drift.signals import drift_pct

    assert drift_pct(45, 56) == pytest.approx(19.64, abs=0.01)
    assert drift_pct(11, 11) == 0.0
    assert drift_pct(0, 0) == 0.0
    assert drift_pct(0, 4) == 100.0


def test_describe_est_un_groupe_pas_un_test(tmp_path):
    """`describe(` regroupe des cas, il n'en est pas un.

    Mesure sur une suite Vitest de 108 fichiers : 1162 « tests » comptes contre **931**
    reellement executes par Vitest. L'ecart, 225, est exactement le nombre de
    `describe(` du depot (927 `it/test` + 225 `describe` + 10 e2e = 1162). Un
    faux ecart de 20 % s'installait donc sur tout projet JS structure en suites.
    """
    (tmp_path / "a.test.ts").write_text(
        "describe('groupe', () => {\n"
        "  describe('sous-groupe', () => {\n"
        "    it('cas 1', () => {})\n"
        "    it('cas 2', () => {})\n"
        "  })\n"
        "})\n"
    )
    assert extract_code_signals(tmp_path).tests == 2


def test_modele_llm_nest_pas_un_modele_de_donnees(tmp_path):
    """« modele » est ambigu : donnees (ORM) ou LLM. Sans label, ne pas trancher.

    Regression du 2026-08-06 : l'assouplissement de la forme inline avait fait
    lire `**1 modele resident** = <nom>` (docs d'infrastructure, un modele
    LLM charge en NPU) comme « 1 modele de donnees documente », et sorti un
    DRIFT a 100 % contre 0 modele reel. La forme inline exige donc de nouveau
    une fermeture immediate ; la forme longue reste lue via le label et son `:`.
    """
    (tmp_path / "CLAUDE.md").write_text(
        "| Runtime | **52625** | NPU | **1 modele resident** = `small-lm:4b` |\n"
    )
    doc, _ = extract_doc_signals(tmp_path)
    assert doc.models is None


def test_inline_ferme_reste_lu(tmp_path):
    """Non-regression : `**4 modeles**` garde sa lecture."""
    (tmp_path / "CLAUDE.md").write_text("Stack : **3 routes**, **4 modeles**, **10 tests**\n")
    doc, _ = extract_doc_signals(tmp_path)
    assert (doc.routes, doc.models, doc.tests) == (3, 4, 10)
