from pathlib import Path

import httpx
import pytest

from memory_search.loader import MemoryEntry, iter_memory
from memory_search.search import (
    cosine,
    embed_ollama,
    fulltext_score,
    grep_entries,
    semantic_score,
    tokenize,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample_projects"


def test_tokenize_strips_short_tokens():
    # min 2 chars : "a" est strip, mais "le" et "vu" sont gardes
    assert tokenize("A chat x vu chien") == ["chat", "vu", "chien"]


def test_tokenize_accents():
    tokens = tokenize("facturation electronique")
    assert "facturation" in tokens
    assert "electronique" in tokens


def test_fulltext_empty_query():
    entries = list(iter_memory(FIXTURES))
    assert fulltext_score(entries, "") == []


def test_fulltext_nf525_wins():
    entries = list(iter_memory(FIXTURES))
    results = fulltext_score(entries, "nf525")
    assert len(results) >= 1
    assert results[0].entry.slug == "project_nf525"


def test_fulltext_no_match():
    entries = list(iter_memory(FIXTURES))
    results = fulltext_score(entries, "zzzinexistant")
    assert results == []


def test_fulltext_empty_docs():
    assert fulltext_score([], "query") == []


def test_cosine_identical():
    assert cosine([1.0, 0.0], [1.0, 0.0]) > 0.99


def test_cosine_orthogonal():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_semantic_score_length_mismatch():
    import pytest

    with pytest.raises(ValueError):
        semantic_score([], "q", [[1.0]], [1.0])


def test_semantic_score_ordering():
    entries = list(iter_memory(FIXTURES))[:2]
    # premiere entree embedding proche de la query
    embs = [[1.0, 0.0], [0.0, 1.0]]
    q = [1.0, 0.0]
    results = semantic_score(entries, "q", embs, q)
    assert results[0].entry is entries[0]


def test_grep_case_insensitive():
    entries = list(iter_memory(FIXTURES))
    results = grep_entries(entries, "NF525")
    assert any(r.entry.slug == "project_nf525" for r in results)


def test_grep_regex():
    entries = list(iter_memory(FIXTURES))
    results = grep_entries(entries, r"agent[s]?")
    assert len(results) >= 1


# --- Regressions : entrees malformees / cache incoherent (2026-07-28) ---


def _entry(**kw):
    return MemoryEntry(path="p", project="x", slug="s", **kw)


def test_grep_regex_invalide_leve_valueerror():
    """Un pattern CLI errone doit donner un message, pas une traceback re.error."""
    with pytest.raises(ValueError, match="regex invalide"):
        grep_entries([_entry(body="abc")], "ADR-[")


def test_semantic_score_dimension_incompatible():
    """Cache en dim 768 (nomic) interroge en dim 1024 (bge-m3) : cause explicite."""
    entries = [_entry(body="a")]
    with pytest.raises(ValueError, match="dimension d'embedding incompatible"):
        semantic_score(entries, "q", [[0.1] * 768], [0.2] * 1024)


def test_embed_ollama_liste_embeddings_vide(monkeypatch):
    """`{"embeddings": []}` doit lever RuntimeError, pas IndexError."""

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"embeddings": []}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda **kw: _Client())
    with pytest.raises(RuntimeError, match="Reponse Ollama inattendue"):
        embed_ollama(["texte"])
