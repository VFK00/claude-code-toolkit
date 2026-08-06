from orchestrator.detect import detect_project, filter_projects, scan_projects


def make_project(tmp_path, name, files):
    p = tmp_path / name
    p.mkdir()
    for fname in files:
        (p / fname).parent.mkdir(parents=True, exist_ok=True)
        (p / fname).touch()
    return p


def test_detect_python_uv(tmp_path):
    p = make_project(tmp_path, "uvproj", ["uv.lock", "pyproject.toml", "tests/test_x.py"])
    s = detect_project(p)
    assert s.kind == "python-uv"
    assert s.has_tests is True
    assert s.preset_cmd("test") == "uv run pytest"


def test_detect_python_pip(tmp_path):
    p = make_project(tmp_path, "pypip", ["requirements.txt"])
    assert detect_project(p).kind == "python-pip"


def test_detect_pnpm(tmp_path):
    p = make_project(tmp_path, "pnpmproj", ["package.json", "pnpm-lock.yaml"])
    s = detect_project(p)
    assert s.kind == "node-pnpm"
    assert s.preset_cmd("test") == "pnpm test"


def test_detect_npm(tmp_path):
    p = make_project(tmp_path, "npmproj", ["package.json"])
    assert detect_project(p).kind == "node-npm"


def test_detect_static(tmp_path):
    p = make_project(tmp_path, "static", ["index.html"])
    s = detect_project(p)
    assert s.kind == "static"
    assert s.preset_cmd("test") is None
    assert s.preset_cmd("status") is not None


def test_detect_unknown(tmp_path):
    p = make_project(tmp_path, "x", ["README.md"])
    assert detect_project(p).kind == "unknown"


def test_scan_recurse_into(tmp_path):
    make_project(tmp_path, "alpha", ["pyproject.toml"])
    (tmp_path / "clients").mkdir()
    make_project(tmp_path / "clients", "beta", ["package.json"])
    make_project(tmp_path, "archives", ["pyproject.toml"])
    (tmp_path / ".hidden").mkdir()

    projects = scan_projects(tmp_path)
    names = {p.name for p in projects}
    assert "alpha" in names
    assert "beta" in names
    assert "archives" not in names


def test_scan_missing_base(tmp_path):
    assert scan_projects(tmp_path / "nope") == []


# --- Categories detectees, plus enumerees ---


def test_scan_descend_dans_une_categorie_non_listee(tmp_path):
    """`produits/` n'etait dans aucune liste : ses 4 projets etaient invisibles.

    Un dossier sans marqueur de stack dont les enfants en portent est une
    categorie, quel que soit son nom.
    """
    (tmp_path / "produits").mkdir()
    make_project(tmp_path / "produits", "billing-api", ["pyproject.toml"])
    make_project(tmp_path / "produits", "shop-front", ["package.json"])

    names = {p.name for p in scan_projects(tmp_path)}
    assert names == {"billing-api", "shop-front"}
    assert "produits" not in names


def test_scan_garde_un_projet_a_sous_dossier_entier(tmp_path):
    """Un projet dont la stack est dans `app/` reste un projet, pas une categorie.

    Sinon on remonterait `app` et `admin` en perdant le nom du client.
    """
    client = tmp_path / "acme-corp"
    client.mkdir()
    make_project(client, "app", ["package.json"])
    (client / "admin").mkdir()

    projects = scan_projects(tmp_path)
    assert [p.name for p in projects] == ["acme-corp"]
    assert projects[0].subdir == "app"


def test_scan_ignore_les_dossiers_de_service(tmp_path):
    """`_archives` et `_migration` ne sont pas des projets."""
    make_project(tmp_path, "alpha", ["pyproject.toml"])
    make_project(tmp_path, "_archives", ["pyproject.toml"])
    make_project(tmp_path, "_migration", ["pyproject.toml"])

    assert {p.name for p in scan_projects(tmp_path)} == {"alpha"}


def test_scan_categorie_sans_enfant_projet_reste_un_projet(tmp_path):
    """Un dossier de documents ne doit pas se dissoudre en ses sous-dossiers."""
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "factures").mkdir()
    (docs / "contrats").mkdir()

    assert [p.name for p in scan_projects(tmp_path)] == ["documents"]


def test_filter_by_name(tmp_path):
    make_project(tmp_path, "a", ["pyproject.toml", "uv.lock"])
    make_project(tmp_path, "b", ["package.json"])
    all_ = scan_projects(tmp_path)
    filtered = filter_projects(all_, names=["a"])
    assert [p.name for p in filtered] == ["a"]


def test_filter_by_match(tmp_path):
    make_project(tmp_path, "a", ["pyproject.toml", "uv.lock"])
    make_project(tmp_path, "b", ["package.json"])
    all_ = scan_projects(tmp_path)
    py = filter_projects(all_, match="python")
    node = filter_projects(all_, match="node")
    assert [p.name for p in py] == ["a"]
    assert [p.name for p in node] == ["b"]


def test_preset_build_python_uv(tmp_path):
    p = make_project(tmp_path, "x", ["uv.lock"])
    assert detect_project(p).preset_cmd("build") == "uv build"


def test_preset_unknown_kind(tmp_path):
    p = make_project(tmp_path, "x", ["README.md"])
    assert detect_project(p).preset_cmd("test") is None


def test_detect_subdir_backend(tmp_path):
    # Manifest en sous-dossier : pas de manifest racine, backend/ Python + frontend/ Node
    p = make_project(
        tmp_path, "beta", ["README.md", "backend/pyproject.toml", "backend/tests/test_x.py"]
    )
    s = detect_project(p)
    assert s.kind == "python-pip"
    assert s.subdir == "backend"
    assert s.has_tests is True
    assert s.preset_cmd("test") == "cd backend && pytest"
    # Status reste a la racine
    assert s.preset_cmd("status") == "git status --short && git branch --show-current"


def test_detect_subdir_api_uv(tmp_path):
    p = make_project(tmp_path, "x", ["api/uv.lock", "api/pyproject.toml"])
    s = detect_project(p)
    assert s.kind == "python-uv"
    assert s.subdir == "api"
    assert s.preset_cmd("lint") == "cd api && uv run ruff check . && uv run mypy src/"


def test_detect_subdir_priority(tmp_path):
    # backend/ prioritaire sur api/
    p = make_project(tmp_path, "x", ["backend/pyproject.toml", "api/pyproject.toml"])
    assert detect_project(p).subdir == "backend"


def test_detect_no_subdir_when_root_has_manifest(tmp_path):
    p = make_project(tmp_path, "x", ["uv.lock", "backend/pyproject.toml"])
    s = detect_project(p)
    assert s.subdir is None
    assert s.kind == "python-uv"
