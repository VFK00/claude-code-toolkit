"""Tarifs Anthropic par modele (USD par million de tokens).

Source : anthropic.com/pricing (avr 2026).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pricing:
    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float

    def cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_5m: int = 0,
        cache_creation_1h: int = 0,
        cache_read: int = 0,
    ) -> float:
        return (
            input_tokens * self.input
            + output_tokens * self.output
            + cache_creation_5m * self.cache_write_5m
            + cache_creation_1h * self.cache_write_1h
            + cache_read * self.cache_read
        ) / 1_000_000


PRICING: dict[str, Pricing] = {
    "claude-opus-4-7": Pricing(15.00, 75.00, 18.75, 30.00, 1.50),
    "claude-opus-4-6": Pricing(15.00, 75.00, 18.75, 30.00, 1.50),
    "claude-opus-4-5": Pricing(15.00, 75.00, 18.75, 30.00, 1.50),
    "claude-sonnet-4-6": Pricing(3.00, 15.00, 3.75, 6.00, 0.30),
    "claude-sonnet-4-5": Pricing(3.00, 15.00, 3.75, 6.00, 0.30),
    "claude-haiku-4-5": Pricing(0.80, 4.00, 1.00, 1.60, 0.08),
    "claude-haiku-4-5-20251001": Pricing(0.80, 4.00, 1.00, 1.60, 0.08),
}


def resolve(model: str) -> Pricing | None:
    """Resolution tolerante aux suffixes de version (ex: `[1m]`, `-20251001`)."""
    if model in PRICING:
        return PRICING[model]
    base = model.split("[")[0].rsplit("-", 1)[0] if "-202" in model else model.split("[")[0]
    if base in PRICING:
        return PRICING[base]
    for key in PRICING:
        if model.startswith(key):
            return PRICING[key]
    return None
