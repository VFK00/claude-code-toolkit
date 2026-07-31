"""Scoring fulltext BM25-lite + scoring semantique via Ollama."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import httpx

from .loader import MemoryEntry

TOKEN_RE = re.compile(r"[a-zA-ZÀ-ſ0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


@dataclass
class Scored:
    entry: MemoryEntry
    score: float
    reason: str


def fulltext_score(entries: list[MemoryEntry], query: str) -> list[Scored]:
    """BM25-lite : tf-idf pondere par longueur. Suffisant pour quelques centaines de docs."""
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    docs = [tokenize(e.searchable_text()) for e in entries]
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in docs) / n
    k1, b = 1.5, 0.75
    # Document frequency
    df: Counter[str] = Counter()
    for d in docs:
        for term in set(d):
            df[term] += 1

    results: list[Scored] = []
    for entry, doc in zip(entries, docs, strict=True):
        tf = Counter(doc)
        dl = len(doc) or 1
        score = 0.0
        hits = []
        for term in q_tokens:
            if df[term] == 0:
                continue
            idf = math.log((n - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / avgdl)
            if denom:
                score += idf * (freq * (k1 + 1)) / denom
                if freq:
                    hits.append(term)
        if score > 0:
            results.append(Scored(entry=entry, score=score, reason=f"fulltext:{'+'.join(hits)}"))
    results.sort(key=lambda s: s.score, reverse=True)
    return results


def embed_ollama(
    texts: list[str],
    model: str = "nomic-embed-text",
    host: str = "http://localhost:11434",
    timeout: float = 30.0,
) -> list[list[float]]:
    """Calcule les embeddings via Ollama `/api/embeddings`."""
    out: list[list[float]] = []
    with httpx.Client(timeout=timeout) as client:
        for text in texts:
            resp = client.post(
                f"{host}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
            # `embeddings` peut arriver en liste VIDE (modele absent, entree vide) :
            # indexer [0] dessus leve IndexError et court-circuite le garde-fou
            # ci-dessous. On extrait sans indexer a l'aveugle.
            embedding = data.get("embedding")
            if not embedding:
                batch = data.get("embeddings") or []
                embedding = batch[0] if batch else None
            if not embedding:
                raise RuntimeError(f"Reponse Ollama inattendue : {data}")
            out.append(embedding)
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


def semantic_score(
    entries: list[MemoryEntry],
    query: str,
    embeddings: list[list[float]],
    query_embedding: list[float],
) -> list[Scored]:
    """Scoring semantique a partir d'embeddings pre-calcules."""
    if len(embeddings) != len(entries):
        raise ValueError("nb embeddings != nb entries")
    # Changer de modele d'embedding change la dimension (nomic-embed-text 768,
    # bge-m3 1024). Sans ce controle, cosine() sort un `zip() argument 2 is
    # longer than argument 1` qui ne dit rien de la cause reelle.
    for emb in embeddings:
        if len(emb) != len(query_embedding):
            raise ValueError(
                f"dimension d'embedding incompatible : cache={len(emb)}, "
                f"requete={len(query_embedding)}. Le modele d'embedding a change — "
                "reconstruis le cache avec `memory-search index`."
            )
    scored = [
        Scored(entry=e, score=cosine(emb, query_embedding), reason="semantic")
        for e, emb in zip(entries, embeddings, strict=True)
    ]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def grep_entries(entries: list[MemoryEntry], pattern: str) -> list[Scored]:
    """Cherche `pattern` (regex) dans les entries.

    Leve `ValueError` si la regex est invalide — le pattern vient de la ligne de
    commande, une coquille ne doit pas remonter en traceback Python brute.
    """
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"regex invalide : {exc}") from exc
    results: list[Scored] = []
    for e in entries:
        text = e.searchable_text()
        matches = rx.findall(text)
        if matches:
            results.append(
                Scored(entry=e, score=float(len(matches)), reason=f"grep:{len(matches)}")
            )
    results.sort(key=lambda s: s.score, reverse=True)
    return results
