from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict

from .decision_engine import DecisionEngine
from .state import RoundState


class Flip7UI(tk.Tk):
    """
    Manual Flip 7 helper UI.

    Instead of using OCR / template matching, this UI exposes buttons for all
    relevant cards. As you see cards in play, click the corresponding buttons
    and the helper updates bust probability and EV in real time.
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Flip7 Helper (Manual)")

        # Current round state (your active line + held modifiers)
        self.state = RoundState(numbers=frozenset())
        self.decision = DecisionEngine()

        # Deck tracker: how many copies of each card have been seen in the
        # current shoe (including discarded / banked cards and your line).
        # Keys use the same labels as DeckComposition: "0".."12", "freeze",
        # "flipthree", "secondchance", "x2", "+2".."+10".
        self.seen_counts: Dict[str, int] = {}

        # Static totals for each card in the standard 94-card deck.
        self._deck_totals: Dict[str, int] = dict(self.decision.base.counts)
        # StringVars used to display "remaining/total" for each label.
        self._deck_count_vars: Dict[str, tk.StringVar] = {}

        self._build_widgets()
        self._recompute()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)

        header = ttk.Label(self, text="Flip 7 Manual Helper", font=("Segoe UI", 14, "bold"))
        header.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        desc = ttk.Label(
            self,
            text="Track cards seen in DECK, your current line in LINE.",
            font=("Segoe UI", 9),
        )
        desc.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        sep = ttk.Separator(self, orient="horizontal")
        sep.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        # ----------------------------- Deck tracker
        deck_frame = ttk.LabelFrame(self, text="Deck (cards seen in shoe)")
        deck_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=4)

        # Numbers 0–12
        num_deck_frame = ttk.Frame(deck_frame)
        num_deck_frame.grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Label(num_deck_frame, text="Nums:").grid(row=0, column=0, sticky="w")
        for i in range(0, 13):
            col = i + 1
            lbl = str(i)
            minus = ttk.Button(
                num_deck_frame, text="-", width=3, command=lambda k=lbl: self._adjust_seen(k, -1)
            )
            minus.grid(row=0, column=col, padx=(1, 0), pady=1)
            plus = ttk.Button(
                num_deck_frame, text=lbl, width=4, command=lambda k=lbl: self._adjust_seen(k, +1)
            )
            plus.grid(row=1, column=col, padx=(1, 0), pady=1)

            # Remaining / total label for this number
            var = tk.StringVar()
            self._deck_count_vars[lbl] = var
            ttk.Label(num_deck_frame, textvariable=var, font=("Segoe UI", 8)).grid(
                row=2, column=col, padx=(1, 0), pady=0
            )

        # Actions / modifiers in deck
        misc_deck_frame = ttk.Frame(deck_frame)
        misc_deck_frame.grid(row=1, column=0, sticky="w", padx=2, pady=(4, 2))

        def add_deck_row(r: int, label: str, text: str) -> None:
            var = tk.StringVar()
            self._deck_count_vars[label] = var
            ttk.Label(misc_deck_frame, textvariable=var).grid(row=r, column=0, sticky="w")
            ttk.Button(
                misc_deck_frame, text="-", width=2, command=lambda k=label: self._adjust_seen(k, -1)
            ).grid(row=r, column=1, padx=1)
            ttk.Button(
                misc_deck_frame, text="+1", width=3, command=lambda k=label: self._adjust_seen(k, +1)
            ).grid(row=r, column=2, padx=1)

        add_deck_row(0, "freeze", "freeze")
        add_deck_row(1, "flipthree", "flipthree")
        add_deck_row(2, "secondchance", "secondchance")
        add_deck_row(3, "x2", "x2")

        for idx, m in enumerate((2, 4, 6, 8, 10), start=4):
            add_deck_row(idx, f"+{m}", f"+{m}")

        # ----------------------------- Line / held state
        line_frame = ttk.LabelFrame(self, text="Line & held cards")
        line_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=4)

        # Numbers in line: toggles
        nums_line_frame = ttk.Frame(line_frame)
        nums_line_frame.grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Label(nums_line_frame, text="Line numbers:").grid(row=0, column=0, sticky="w")
        self._line_number_vars: Dict[int, tk.IntVar] = {}
        for i in range(0, 13):
            var = tk.IntVar(value=0)
            self._line_number_vars[i] = var
            chk = ttk.Checkbutton(
                nums_line_frame,
                text=str(i),
                variable=var,
                command=self._sync_line_numbers_from_vars,
            )
            r, c = divmod(i, 7)
            chk.grid(row=r + 1, column=c, padx=2, pady=1, sticky="w")

        # Modifiers / actions you currently hold
        mods_frame = ttk.Frame(line_frame)
        mods_frame.grid(row=1, column=0, sticky="w", padx=2, pady=(4, 2))

        sc_btn = ttk.Button(mods_frame, text="Second Chance", command=self._on_second_chance)
        sc_btn.grid(row=0, column=0, sticky="w", padx=2, pady=2)

        ft_btn = ttk.Button(mods_frame, text="Flip Three", command=self._on_flip_three)
        ft_btn.grid(row=0, column=1, sticky="w", padx=2, pady=2)

        x2_btn = ttk.Button(mods_frame, text="x2", command=self._on_x2)
        x2_btn.grid(row=0, column=2, sticky="w", padx=2, pady=2)

        add_frame = ttk.Frame(line_frame)
        add_frame.grid(row=2, column=0, sticky="w", padx=2, pady=(2, 2))
        ttk.Label(add_frame, text="Add points:").grid(row=0, column=0, sticky="w")
        for idx, m in enumerate((2, 4, 6, 8, 10)):
            btn = ttk.Button(add_frame, text=f"+{m}", command=lambda v=m: self._on_add_points(v))
            btn.grid(row=0, column=idx + 1, sticky="w", padx=2, pady=2)

        # Summary / output labels
        self.bust_label = ttk.Label(self, text="Bust next: --", font=("Segoe UI", 12, "bold"))
        self.bust_label.grid(row=5, column=0, sticky="w", padx=10, pady=2)

        self.ev_label = ttk.Label(self, text="EV (take 1 then stay): --", font=("Segoe UI", 11))
        self.ev_label.grid(row=6, column=0, sticky="w", padx=10, pady=2)

        self.threshold_label = ttk.Label(self, text="Bust threshold (P*): --", font=("Segoe UI", 9))
        self.threshold_label.grid(row=7, column=0, sticky="w", padx=10, pady=2)

        self.flip3_label = ttk.Label(self, text="Flip Three (if active): --", font=("Segoe UI", 9))
        self.flip3_label.grid(row=8, column=0, sticky="w", padx=10, pady=2)

        self.numbers_label = ttk.Label(self, text="Numbers: []", font=("Segoe UI", 10))
        self.numbers_label.grid(row=9, column=0, sticky="w", padx=10, pady=2)

        self.bank_label = ttk.Label(self, text="Bank (stay now): 0", font=("Segoe UI", 10))
        self.bank_label.grid(row=10, column=0, sticky="w", padx=10, pady=2)

        self.recommend_label = ttk.Label(self, text="Recommendation: --", font=("Segoe UI", 12, "bold"))
        self.recommend_label.grid(row=11, column=0, sticky="w", padx=10, pady=(6, 4))

        self.notes_text = tk.Text(self, height=4, width=60, wrap="word")
        self.notes_text.grid(row=12, column=0, sticky="nsew", padx=10, pady=(4, 8))
        self.notes_text.configure(state="disabled")
        self.rowconfigure(12, weight=1)

        # Initialize deck count labels now that widgets exist
        self._refresh_deck_counts()

        # Control buttons
        controls = ttk.Frame(self)
        controls.grid(row=13, column=0, sticky="ew", padx=10, pady=(0, 8))
        controls.columnconfigure(0, weight=1)

        reset_btn = ttk.Button(controls, text="New Shoe (reset all)", command=self._on_reset_round)
        reset_btn.grid(row=0, column=0, sticky="w", padx=2)

        clear_line_btn = ttk.Button(controls, text="Clear line", command=self._on_clear_line)
        clear_line_btn.grid(row=0, column=1, sticky="w", padx=8)

    # ----------------------------------------------------------------- logic
    @staticmethod
    def _fmt_pct(x: float) -> str:
        return f"{100.0 * x:.1f}%"

    def _recompute(self) -> None:
        out = self.decision.compute(self.state, self.seen_counts)

        nums_sorted = sorted(self.state.numbers)
        bank = self.state.current_bank_value()
        self.numbers_label.config(text=f"Numbers: {nums_sorted}")
        self.bank_label.config(
            text=f"Bank (stay now): {bank}   x2={self.state.multiplier_x2}  "
            f"+mods={self.state.add_points}  SC={self.state.has_second_chance}"
        )

        self.bust_label.config(text=f"Bust next: {self._fmt_pct(out.bust_probability_next)}")
        self.ev_label.config(text=f"EV (take 1 then stay): {out.expected_value_next:.2f}")
        self.threshold_label.config(
            text=f"Bust threshold (P*): {self._fmt_pct(out.threshold_probability_next)}"
        )

        if self.state.flip_three_active:
            self.flip3_label.config(
                text=f"Flip Three: bust={self._fmt_pct(out.bust_probability_flip_three)}, "
                f"EV≈{out.expected_value_flip_three:.2f}"
            )
        else:
            self.flip3_label.config(text="Flip Three: not active")

        # Marginal stopping rule:
        # Take another card only if bust probability is below the
        # break-even threshold P* = V_next / (S + V_next).
        p_b = out.bust_probability_next
        p_star = out.threshold_probability_next
        margin = p_star - p_b
        if margin > 0.02:
            rec = "Recommendation: TAKE another card"
        elif margin < -0.02:
            rec = "Recommendation: STAY"
        else:
            rec = "Recommendation: NEUTRAL (near break-even)"
        self.recommend_label.config(text=rec)

        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        if out.notes:
            for n in out.notes:
                self.notes_text.insert("end", f"- {n}\n")
        else:
            self.notes_text.insert("end", "Using standard 94-card Flip 7 deck.")
        self.notes_text.configure(state="disabled")

    # ------------------------------ button handlers (mutate state then recompute)
    def _remaining_total_for(self, label: str) -> tuple[int, int]:
        total = int(self._deck_totals.get(label, 0))
        seen = int(self.seen_counts.get(label, 0))
        remaining = max(0, total - seen)
        return remaining, total

    def _refresh_deck_counts(self) -> None:
        for label, var in self._deck_count_vars.items():
            remaining, total = self._remaining_total_for(label)
            var.set(f"{label}: {remaining}/{total}")

    def _adjust_seen(self, label: str, delta: int) -> None:
        """Adjust how many copies of a given card have been seen in the deck."""
        cur = self.seen_counts.get(label, 0)
        cur = max(0, cur + delta)
        if cur == 0:
            self.seen_counts.pop(label, None)
        else:
            self.seen_counts[label] = cur
        self._refresh_deck_counts()
        self._recompute()

    def _sync_line_numbers_from_vars(self) -> None:
        """Update the active line numbers from the checkbuttons and sync deck counts."""
        prev_nums = set(self.state.numbers)
        nums = {n for n, var in self._line_number_vars.items() if var.get()}

        # Any newly-added number to the line also counts as seen in the shoe.
        for n in nums - prev_nums:
            self._adjust_seen(str(n), +1)

        self.state = RoundState(
            numbers=frozenset(nums),
            has_second_chance=self.state.has_second_chance,
            flip_three_active=self.state.flip_three_active,
            multiplier_x2=self.state.multiplier_x2,
            add_points=self.state.add_points,
        )
        self._recompute()

    def _on_second_chance(self) -> None:
        new_flag = not self.state.has_second_chance
        # When Second Chance is gained, also mark one copy as seen in the deck.
        if new_flag and not self.state.has_second_chance:
            self._adjust_seen("secondchance", +1)
        self.state = RoundState(
            numbers=self.state.numbers,
            has_second_chance=new_flag,
            flip_three_active=self.state.flip_three_active,
            multiplier_x2=self.state.multiplier_x2,
            add_points=self.state.add_points,
        )
        self._recompute()

    def _on_flip_three(self) -> None:
        new_flag = not self.state.flip_three_active
        if new_flag and not self.state.flip_three_active:
            self._adjust_seen("flipthree", +1)
        self.state = RoundState(
            numbers=self.state.numbers,
            has_second_chance=self.state.has_second_chance,
            flip_three_active=new_flag,
            multiplier_x2=self.state.multiplier_x2,
            add_points=self.state.add_points,
        )
        self._recompute()

    def _on_x2(self) -> None:
        new_flag = not self.state.multiplier_x2
        if new_flag and not self.state.multiplier_x2:
            self._adjust_seen("x2", +1)
        self.state = RoundState(
            numbers=self.state.numbers,
            has_second_chance=self.state.has_second_chance,
            flip_three_active=self.state.flip_three_active,
            multiplier_x2=new_flag,
            add_points=self.state.add_points,
        )
        self._recompute()

    def _on_add_points(self, amount: int) -> None:
        # Each click represents drawing one +N card from the deck and holding it.
        self._adjust_seen(f"+{amount}", +1)
        self.state = RoundState(
            numbers=self.state.numbers,
            has_second_chance=self.state.has_second_chance,
            flip_three_active=self.state.flip_three_active,
            multiplier_x2=self.state.multiplier_x2,
            add_points=self.state.add_points + amount,
        )
        self._recompute()

    def _on_reset_round(self) -> None:
        # Reset both the line and the deck tracker for a fresh shoe.
        self.state = RoundState(numbers=frozenset())
        self.seen_counts.clear()
        # Clear line checkboxes
        for var in self._line_number_vars.values():
            var.set(0)
        self._refresh_deck_counts()
        self._recompute()

    def _on_clear_line(self) -> None:
        # Clear only the current line (numbers + modifiers), keep deck history.
        self.state = RoundState(numbers=frozenset())
        for var in self._line_number_vars.values():
            var.set(0)
        self._recompute()


def main() -> None:
    """
    Entry point used by the `flip7-ui` console script.

    Simply opens the manual helper window; no command-line arguments required.
    """
    app = Flip7UI()
    app.mainloop()

