from cost_tracker.pricing import PRICING, resolve


def test_opus_cost_basic():
    p = PRICING["claude-opus-4-7"]
    # 1M input + 1M output + 0 cache
    assert p.cost(1_000_000, 1_000_000) == 90.0


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
    assert resolve("claude-haiku-4-5-20251001") is PRICING["claude-haiku-4-5-20251001"]


def test_resolve_prefix_match():
    # Version inconnue mais prefix reconnu
    assert resolve("claude-opus-4-7[1m]") is PRICING["claude-opus-4-7"]


def test_resolve_unknown():
    assert resolve("claude-unknown-9-9") is None
