from datetime import UTC, datetime

from cost_tracker.pricing import PRICING, resolve


def test_opus_cost_basic():
    p = PRICING["claude-opus-4-7"]
    # 1M input + 1M output + 0 cache -> 5 + 25
    assert p.cost(1_000_000, 1_000_000) == 30.0


def test_sonnet_cost_with_cache():
    p = PRICING["claude-sonnet-4-6"]
    # 1M input, 0 output, 1M cache_write_5m, 1M cache_read
    cost = p.cost(1_000_000, 0, cache_creation_5m=1_000_000, cache_read=1_000_000)
    assert cost == 3.0 + 3.75 + 0.30


def test_haiku_zero_tokens():
    assert PRICING["claude-haiku-4-5"].cost(0, 0) == 0.0


def test_resolve_exact():
    assert resolve("claude-opus-4-7") is PRICING["claude-opus-4-7"]


def test_resolve_with_suffix():
    assert resolve("claude-haiku-4-5-20251001") is PRICING["claude-haiku-4-5"]


def test_resolve_suffixe_contexte():
    assert resolve("claude-opus-4-7[1m]") is PRICING["claude-opus-4-7"]


def test_resolve_unknown():
    assert resolve("claude-unknown-9-9") is None


def test_opus_5_est_tarife():
    """Le modele courant du poste. Absent, il comptait pour zero."""
    p = resolve("claude-opus-5[1m]")
    assert p is not None
    assert (p.input, p.output, p.cache_read) == (5.00, 25.00, 0.50)


def test_sonnet_5_tarif_introductif_avant_bascule():
    p = resolve("claude-sonnet-5", datetime(2026, 8, 15, tzinfo=UTC))
    assert p is not None
    assert (p.input, p.output) == (2.00, 10.00)


def test_sonnet_5_tarif_plein_apres_bascule():
    p = resolve("claude-sonnet-5", datetime(2026, 9, 1, tzinfo=UTC))
    assert p is not None
    assert (p.input, p.output) == (3.00, 15.00)


def test_sonnet_5_accepte_un_timestamp_naif():
    """Les transcripts ne portent pas tous un fuseau : ne pas lever dessus."""
    p = resolve("claude-sonnet-5", datetime(2026, 8, 15))
    assert p is not None
    assert p.input == 2.00


def test_pas_de_repli_sur_prefixe():
    """`claude-opus-4-9` commence par `claude-opus-4`, dont la grille est celle
    des modeles retires — trois fois le tarif reel. Mieux vaut None."""
    assert resolve("claude-opus-4-9") is None
