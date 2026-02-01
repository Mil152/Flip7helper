from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Tuple

from flip7helper.deck_engine import DeckComposition
from flip7helper.state import RoundState

NUMBER_LABELS = tuple(str(i) for i in range(0, 13))


def _is_number_label(lbl: str) -> bool:
    return lbl.isdigit() and 0 <= int(lbl) <= 12


@dataclass(frozen=True)
class DecisionOutput:
    bust_probability_next: float
    bust_probability_flip_three: float
    expected_value_next: float
    expected_value_flip_three: float
    threshold_probability_next: float
    average_gain_next_if_success: float
    notes: Tuple[str, ...] = ()


class DecisionEngine:
    """
    Deterministic probability model over the full 94-card deck.

    Outputs:
      - bust_probability_next: probability you bust on the next draw (duplicate number)
      - expected_value_next: expected bank after taking exactly one more card, then staying

    Also provides rough approximations for Flip Three.

    Notes:
      - Action/modifier cards do not bust.
      - Second Chance: next-draw bust is effectively 0 (duplicate is canceled once).
    """

    def __init__(self, composition: DeckComposition | None = None) -> None:
        self.base = composition or DeckComposition.standard()

    def compute(
        self,
        state: RoundState,
        seen_counts: Mapping[str, int] | None = None,
        skip_flip_three: bool = False,
        include_flip_three: bool = True,
    ) -> DecisionOutput:
        seen_counts = dict(seen_counts or {})
        deck = self.base.remaining_after_seen(seen_counts)
        denom = deck.total_cards()
        if denom <= 0:
            bank = state.current_bank_value()
            return DecisionOutput(0.0, 0.0, float(bank), float(bank), ("Empty deck",))

        dup_labels = [str(n) for n in state.numbers]
        p_dup_number = deck.probability_of(dup_labels)
        bust_next = 0.0 if state.has_second_chance else p_dup_number

        ev_next = self._ev_one_step_stay_after(state, deck, skip_flip_three=skip_flip_three)

        # Marginal stopping model: derive a dynamic average next-card value
        # V_next from the full EV calculation and the current deck instead of
        # using a fixed constant. Treat:
        #   EV_next = (1 - P_b) * (S + V_next) + P_b * B
        # where S is current bank and B is the payoff on bust.
        # Solve for V_next:
        #   V_next = (EV_next - P_b * B) / (1 - P_b) - S
        # This implicitly assigns values to special cards via _ev_one_step_stay_after.
        current_bank = self._apply_flip7_bonus_if_applicable(state, state.current_bank_value())
        p_b = bust_next
        # Bust payoff: 0 if you actually bust, or current bank if Second Chance
        # saves you and you can still bank.
        bust_payoff = float(current_bank) if state.has_second_chance else 0.0

        if p_b < 1.0 - 1e-9:
            v_next = (ev_next - (p_b * bust_payoff)) / (1.0 - p_b) - current_bank
        else:
            v_next = 0.0
        if current_bank + v_next > 0.0:
            p_threshold = v_next / (current_bank + v_next)
        else:
            p_threshold = 1.0

        # Flip Three is the most expensive part of the model. Allow callers to
        # skip it (e.g. UI when Flip Three is not active).
        #
        # When estimating Flip Three EV internally, avoid infinite recursion by
        # optionally skipping the flip-three sub-calculation on recursive calls.
        if (not include_flip_three) or skip_flip_three:
            bust_three, ev_three = 0.0, float(ev_next)
        else:
            bust_three, ev_three = self._approx_flip_three(state, deck)

        notes = []
        if state.unique_count >= 7:
            notes.append("Flip 7 achieved: +15 bonus (round ends)")
        if state.has_second_chance:
            notes.append("Second Chance held: next-draw bust prevented once")
        if state.multiplier_x2:
            notes.append("x2 held: points at risk doubled")

        return DecisionOutput(
            bust_probability_next=bust_next,
            bust_probability_flip_three=bust_three,
            expected_value_next=ev_next,
            expected_value_flip_three=ev_three,
            threshold_probability_next=p_threshold,
            average_gain_next_if_success=v_next,
            notes=tuple(notes),
        )

    def _apply_flip7_bonus_if_applicable(self, state: RoundState, bank_value: int) -> int:
        if state.unique_count >= 7:
            return bank_value + 15
        return bank_value

    def _ev_one_step_stay_after(
        self,
        state: RoundState,
        deck: DeckComposition,
        skip_flip_three: bool = False,
    ) -> float:
        denom = deck.total_cards()
        if denom <= 0:
            return float(state.current_bank_value())

        current_bank = self._apply_flip7_bonus_if_applicable(state, state.current_bank_value())

        dup_labels = [str(n) for n in state.numbers]
        p_dup_number = deck.probability_of(dup_labels)
        ev_dup = float(current_bank) if state.has_second_chance else 0.0

        # New number events
        ev_new_numbers = 0.0
        for n in range(0, 13):
            lbl = str(n)
            cnt = deck.counts.get(lbl, 0)
            if cnt <= 0 or n in state.numbers:
                continue
            p = cnt / denom
            nxt_numbers = set(state.numbers)
            nxt_numbers.add(n)
            nxt_state = RoundState(
                numbers=frozenset(nxt_numbers),
                has_second_chance=state.has_second_chance,
                flip_three_active=state.flip_three_active,
                multiplier_x2=state.multiplier_x2,
                add_points=state.add_points,
            )
            bank = self._apply_flip7_bonus_if_applicable(nxt_state, nxt_state.current_bank_value())
            ev_new_numbers += p * bank

        # Action/modifier events
        ev_other = 0.0

        cnt = deck.counts.get("freeze", 0)
        if cnt:
            ev_other += (cnt / denom) * current_bank

        cnt = deck.counts.get("flipthree", 0)
        if cnt:
            p = cnt / denom
            if skip_flip_three:
                # When called from within a Flip Three approximation, avoid
                # recursing again into another Flip Three simulation. Treat
                # drawing Flip Three as roughly keeping current bank value.
                ev3 = float(current_bank)
            else:
                _, ev3 = self._approx_flip_three(state, deck)
            ev_other += p * ev3

        cnt = deck.counts.get("secondchance", 0)
        if cnt:
            p = cnt / denom
            nxt_state = RoundState(
                numbers=state.numbers,
                has_second_chance=True,
                flip_three_active=state.flip_three_active,
                multiplier_x2=state.multiplier_x2,
                add_points=state.add_points,
            )
            bank = self._apply_flip7_bonus_if_applicable(nxt_state, nxt_state.current_bank_value())
            ev_other += p * bank

        cnt = deck.counts.get("x2", 0)
        if cnt:
            p = cnt / denom
            nxt_state = RoundState(
                numbers=state.numbers,
                has_second_chance=state.has_second_chance,
                flip_three_active=state.flip_three_active,
                multiplier_x2=True,
                add_points=state.add_points,
            )
            bank = self._apply_flip7_bonus_if_applicable(nxt_state, nxt_state.current_bank_value())
            ev_other += p * bank

        for m in (2, 4, 6, 8, 10):
            lbl = f"+{m}"
            cnt = deck.counts.get(lbl, 0)
            if not cnt:
                continue
            p = cnt / denom
            nxt_state = RoundState(
                numbers=state.numbers,
                has_second_chance=state.has_second_chance,
                flip_three_active=state.flip_three_active,
                multiplier_x2=state.multiplier_x2,
                add_points=state.add_points + m,
            )
            bank = self._apply_flip7_bonus_if_applicable(nxt_state, nxt_state.current_bank_value())
            ev_other += p * bank

        return float((p_dup_number * ev_dup) + ev_new_numbers + ev_other)

    def _approx_flip_three(self, state: RoundState, deck: DeckComposition) -> Tuple[float, float]:
        p_bust_total = 0.0
        ev = float(state.current_bank_value())

        surv = 1.0
        tmp_state = state
        tmp_deck = deck
        seen_local: Dict[str, int] = {}

        for _ in range(3):
            # Use a recursion-safe compute that skips its own Flip Three approximation.
            out = self.compute(tmp_state, seen_local, skip_flip_three=True)
            p_bust_step = out.bust_probability_next
            p_bust_total = 1.0 - (surv * (1.0 - p_bust_step))
            surv *= (1.0 - p_bust_step)
            ev = out.expected_value_next

            # heuristic: remove one likely non-bust card to adjust denominators across steps
            denom = tmp_deck.total_cards()
            if denom <= 0:
                break
            candidates: Iterable[str] = []
            if tmp_state.numbers:
                candidates = [str(n) for n in range(0, 13) if n not in tmp_state.numbers]
            best = None
            best_cnt = 0
            for c in candidates:
                cnt = tmp_deck.counts.get(c, 0)
                if cnt > best_cnt:
                    best, best_cnt = c, cnt
            if best is None or best_cnt == 0:
                for k, v in tmp_deck.counts.items():
                    if v <= 0:
                        continue
                    if _is_number_label(k) and int(k) in tmp_state.numbers:
                        continue
                    best = k
                    break
            if best is None:
                break
            seen_local[best] = seen_local.get(best, 0) + 1
            tmp_deck = tmp_deck.remaining_after_seen({best: 1})

        return float(min(max(p_bust_total, 0.0), 1.0)), float(ev)

