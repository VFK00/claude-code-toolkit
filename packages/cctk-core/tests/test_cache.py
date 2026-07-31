from pathlib import Path

from cctk_core.cache import cache_db


def test_chemin_du_cache(tmp_path: Path) -> None:
    assert cache_db("spend", home=tmp_path) == tmp_path / ".cache" / "cctk-spend.db"


def test_cree_le_dossier_parent(tmp_path: Path) -> None:
    db = cache_db("test", home=tmp_path)
    assert db.parent.exists()
    assert db.parent == tmp_path / ".cache"
