from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class RoundState:
    """
    What we can infer from the screenshot (current round only).

    - numbers: unique number cards currently in your line (busting set)
    - has_second_chance: whether you hold Second Chance right now
    - flip_three_active: whether you are forced to take next 3 cards
    - multiplier_x2: whether x2 is currently held (affects EV/risk)
    - add_points: sum of +2/+4/+6/+8/+10 currently held
    """

    numbers: FrozenSet[int]
    has_second_chance: bool = False
    flip_three_active: bool = False
    multiplier_x2: bool = False
    add_points: int = 0

    @property
    def unique_count(self) -> int:
        return len(self.numbers)

    @property
    def number_sum(self) -> int:
        return sum(self.numbers)

    def current_bank_value(self) -> int:
        base = self.number_sum
        if self.multiplier_x2:
            base *= 2
        return base + self.add_points

