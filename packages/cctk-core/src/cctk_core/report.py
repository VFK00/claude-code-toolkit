"""Inventaire de ce qu'une ingestion a ecarte.

Une entree illisible ne doit ni faire tomber le run, ni disparaitre sans
laisser de trace : elle est comptee ici, avec son motif, et restituee en fin
de commande. Le silence est ce qui produit les resultats faux.

Stdlib uniquement : le rendu reste du texte brut, la mise en forme (rich,
couleurs) appartient aux CLI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class SkipReport:
    """Compte les entrees et fichiers ecartes, par motif.

    `entries` = lignes / documents individuels rejetes.
    `files`   = fichiers entierement perdus (illisibles, boucle de symlink...).
    """

    entries: int = 0
    files: int = 0
    reasons: Counter[str] = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)
    max_samples: int = 3

    def skip_entry(self, reason: str, location: str = "") -> None:
        self.entries += 1
        self._record(reason, location)

    def skip_file(self, reason: str, location: str = "") -> None:
        self.files += 1
        self._record(reason, location)

    def _record(self, reason: str, location: str) -> None:
        self.reasons[reason] += 1
        if location and len(self.samples) < self.max_samples:
            self.samples.append(f"{location} ({reason})")

    @property
    def total(self) -> int:
        return self.entries + self.files

    def __bool__(self) -> bool:
        return self.total > 0

    def lines(self) -> list[str]:
        """Rendu multi-lignes : combien, pourquoi, ou. Vide si rien d'ecarte."""
        if not self:
            return []
        counts = []
        if self.entries:
            counts.append(f"{self.entries} entr{'ies' if self.entries > 1 else 'y'}")
        if self.files:
            counts.append(f"{self.files} file{'s' if self.files > 1 else ''}")
        out = [f"Discarded: {' and '.join(counts)}"]
        out += [
            f"  - {reason} x{n}" for reason, n in self.reasons.most_common()
        ]
        out += [f"  e.g. {sample}" for sample in self.samples]
        return out
