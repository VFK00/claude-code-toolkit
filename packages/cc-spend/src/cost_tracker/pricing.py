"""Tarifs Anthropic par modele (USD par million de tokens).

Source : platform.claude.com/docs/en/about-claude/pricing (releve le 2026-08-01).

Un tarif absent vaut zero, pas une erreur : `resolve` rend `None` et l'appelant
compte l'entree comme gratuite. C'est pourquoi `cc-spend report` liste en fin de
rapport les modeles non tarifes — un total silencieusement ampute vaut moins
qu'un total annonce incomplet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


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


_OPUS_5 = Pricing(5.00, 25.00, 6.25, 10.00, 0.50)
_SONNET_4X = Pricing(3.00, 15.00, 3.75, 6.00, 0.30)
_OPUS_LEGACY = Pricing(15.00, 75.00, 18.75, 30.00, 1.50)

PRICING: dict[str, Pricing] = {
    # Fable / Mythos 5
    "claude-fable-5": Pricing(10.00, 50.00, 12.50, 20.00, 1.00),
    "claude-mythos-5": Pricing(10.00, 50.00, 12.50, 20.00, 1.00),
    # Opus 5 et toute la famille 4.5+ partagent la meme grille
    "claude-opus-5": _OPUS_5,
    "claude-opus-4-8": _OPUS_5,
    "claude-opus-4-7": _OPUS_5,
    "claude-opus-4-6": _OPUS_5,
    "claude-opus-4-5": _OPUS_5,
    # Opus 4.1 et 4 : retires, grille distincte, conserves pour l'historique
    "claude-opus-4-1": _OPUS_LEGACY,
    "claude-opus-4": _OPUS_LEGACY,
    # Sonnet : la 5 est datee, cf. SCHEDULED
    "claude-sonnet-4-6": _SONNET_4X,
    "claude-sonnet-4-5": _SONNET_4X,
    "claude-sonnet-4": _SONNET_4X,
    "claude-haiku-4-5": Pricing(1.00, 5.00, 1.25, 2.00, 0.10),
    "claude-haiku-3-5": Pricing(0.80, 4.00, 1.00, 1.60, 0.08),
    # Marqueur interne de Claude Code, pas un modele facture. Declare a zero
    # pour qu'il cesse de remonter comme « non tarife » : un avertissement qui
    # se declenche sur du bruit finit par etre ignore quand il a raison.
    "<synthetic>": Pricing(0.0, 0.0, 0.0, 0.0, 0.0),
}

# Un tarif annonce a une date de bascule. On garde les deux grilles et on
# choisit d'apres la date de l'entree : un rapport sur aout ne doit pas etre
# recalcule au tarif de septembre.
SCHEDULED: dict[str, tuple[datetime, Pricing, Pricing]] = {
    "claude-sonnet-5": (
        datetime(2026, 9, 1, tzinfo=UTC),
        Pricing(2.00, 10.00, 2.50, 4.00, 0.20),  # tarif d'introduction
        Pricing(3.00, 15.00, 3.75, 6.00, 0.30),  # a partir de la bascule
    ),
}


def _base_key(model: str) -> str:
    """Retire le suffixe de contexte (`[1m]`) puis la date de version."""
    base = model.split("[")[0]
    return base.rsplit("-", 1)[0] if "-202" in base else base


def resolve(model: str, at: datetime | None = None) -> Pricing | None:
    """Tarif d'un modele a une date donnee, ou `None` si inconnu.

    `at` est la date de l'entree d'usage. Sans elle, on prend l'instant courant :
    les appelants qui veulent seulement savoir si un modele est tarife n'ont pas
    a fabriquer une date.
    """
    when = at or datetime.now(UTC)
    for candidate in (model, _base_key(model)):
        if candidate in SCHEDULED:
            switch, before, after = SCHEDULED[candidate]
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return after if when >= switch else before
        if candidate in PRICING:
            return PRICING[candidate]

    # Pas de repli sur un prefixe : `claude-opus-4-9` commence par
    # `claude-opus-4`, dont la grille est celle des modeles retires — trois fois
    # le tarif reel. Un modele non reconnu remonte dans « Not priced », ou il
    # est visible et corrigeable ; devine, il fausse le total en silence.
    return None
