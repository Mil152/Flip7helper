from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping


@dataclass(frozen=True)
class DeckComposition:
    """
    Flip 7 Ruleset 3.1 deck composition (94 cards total).

    Number cards:
    - 2..12: value N has N copies
    - 1: 1 copy
    - 0: 1 copy

    Action cards (9):
    - freeze x3
    - flipthree x3
    - secondchance x3

    Modifier cards (6):
    - +2 +4 +6 +8 +10 (1 each)
    - x2 (1)
    """

    counts: Dict[str, int]

    @staticmethod
    def standard() -> "DeckComposition":
        counts: Dict[str, int] = {}
        counts["0"] = 1
        counts["1"] = 1
        for n in range(2, 13):
            counts[str(n)] = n
        counts["freeze"] = 3
        counts["flipthree"] = 3
        counts["secondchance"] = 3
        for m in (2, 4, 6, 8, 10):
            counts[f"+{m}"] = 1
        counts["x2"] = 1
        return DeckComposition(counts=counts)

    def total_cards(self) -> int:
        return sum(self.counts.values())

    def remaining_after_seen(self, seen: Mapping[str, int]) -> "DeckComposition":
        nxt = dict(self.counts)
        for k, v in seen.items():
            if k not in nxt:
                continue
            nxt[k] = max(0, nxt[k] - int(v))
        return DeckComposition(counts=nxt)

    def probability_of(self, keys: Iterable[str]) -> float:
        denom = self.total_cards()
        if denom <= 0:
            return 0.0
        num = 0
        for k in keys:
            num += self.counts.get(k, 0)
        return num / denom

    def as_dict(self) -> Dict[str, int]:
        return dict(self.counts)

