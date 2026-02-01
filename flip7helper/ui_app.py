from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict

from flip7helper.decision_engine import DecisionEngine
from flip7helper.state import RoundState


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
        # Layout: top (Deck), bottom (Line), then output + controls.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        style = ttk.Style(self)
        # Bigger controls (fills space better)
        # Buttons: slightly smaller to avoid overlap
        style.configure("TButton", padding=(7, 5), font=("Segoe UI", 12))
        style.configure("TCheckbutton", padding=(6, 4))
        # ~1.5x font scale across the app
        style.configure("TLabelframe.Label", font=("Segoe UI", 15, "bold"))
        style.configure("TLabel", font=("Segoe UI", 15))
        # Line checkbox TEXT back to normal; indicator size handled via images.
        style.configure("Big.TCheckbutton", padding=(10, 8), font=("Segoe UI", 18))

        # Custom bigger checkbox indicators (box size ~1.5x).
        self._cb_off, self._cb_on = self._make_checkbox_images(size=24)

        # Keep UI compact: no big header/notes; prioritize buttons.

        # ----------------------------- Deck tracker
        deck_frame = ttk.LabelFrame(self, text="")
        deck_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        deck_frame.columnconfigure(0, weight=1)

        # Numbers 0–12
        num_deck_frame = ttk.Frame(deck_frame)
        num_deck_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        ttk.Label(num_deck_frame, text="Nums:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        for i in range(0, 13):
            # 2-row layout: 0-6 on first row block, 7-12 on second row block
            block = 0 if i <= 6 else 1
            c = i if i <= 6 else (i - 7)
            col = c + 1
            base_row = block * 3
            lbl = str(i)
            minus = ttk.Button(
                num_deck_frame, text="-", width=4, command=lambda k=lbl: self._adjust_seen(k, -1)
            )
            minus.grid(row=base_row + 0, column=col, padx=(1, 0), pady=1)
            plus = ttk.Button(
                num_deck_frame, text=lbl, width=5, command=lambda k=lbl: self._adjust_seen(k, +1)
            )
            plus.grid(row=base_row + 1, column=col, padx=(1, 0), pady=1)

            # Remaining / total label for this number
            var = tk.StringVar()
            self._deck_count_vars[lbl] = var
            ttk.Label(num_deck_frame, textvariable=var, font=("Segoe UI", 14)).grid(
                row=base_row + 2, column=col, padx=(1, 0), pady=(0, 2)
            )

        # Actions / modifiers in deck
        misc_deck_frame = ttk.Frame(deck_frame)
        misc_deck_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(6, 6))

        def add_deck_row(idx: int, label: str, text: str) -> None:
            # 2-column layout for function/modifier cards
            r = idx // 2
            c = idx % 2
            cell = ttk.Frame(misc_deck_frame)
            cell.grid(row=r, column=c, sticky="w", padx=(0, 14), pady=4)

            var = tk.StringVar()
            self._deck_count_vars[label] = var
            ttk.Label(cell, textvariable=var).grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Button(
                cell, text="-", width=3, command=lambda k=label: self._adjust_seen(k, -1)
            ).grid(row=0, column=1, padx=2, pady=2, sticky="w")
            ttk.Button(
                cell, text="+1", width=4, command=lambda k=label: self._adjust_seen(k, +1)
            ).grid(row=0, column=2, padx=2, pady=2, sticky="w")

        add_deck_row(0, "freeze", "freeze")
        add_deck_row(1, "flipthree", "flipthree")
        add_deck_row(2, "secondchance", "secondchance")
        add_deck_row(3, "x2", "x2")

        for j, m in enumerate((2, 4, 6, 8, 10), start=4):
            add_deck_row(j, f"+{m}", f"+{m}")

        # ----------------------------- Line / held state
        line_frame = ttk.LabelFrame(self, text="")
        # Reduce top padding so there's less empty space above the line section.
        line_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        line_frame.columnconfigure(0, weight=1)

        # Numbers in line: toggles
        nums_line_frame = ttk.Frame(line_frame)
        nums_line_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        # Span the label across all checkbox columns so it doesn't widen column 0
        # (which would create a visible gap between 0-1 and 7-8).
        ttk.Label(nums_line_frame, text="Line numbers:").grid(row=0, column=0, columnspan=7, sticky="w")
        self._line_number_vars: Dict[int, tk.IntVar] = {}
        for i in range(0, 13):
            var = tk.IntVar(value=0)
            self._line_number_vars[i] = var
            # ttk.Checkbutton doesn't support selectimage on Windows; use
            # classic tk.Checkbutton for custom indicator images.
            chk = tk.Checkbutton(
                nums_line_frame,
                text=str(i),
                variable=var,
                command=self._sync_line_numbers_from_vars,
                image=self._cb_off,
                selectimage=self._cb_on,
                compound="left",
                indicatoron=False,
                padx=6,
                pady=4,
                font=("Segoe UI", 18),
            )
            r, c = divmod(i, 7)
            chk.grid(row=r + 1, column=c, padx=4, pady=3, sticky="w")

        # Modifiers / actions you currently hold
        mods_frame = ttk.Frame(line_frame)
        mods_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(6, 6))

        sc_btn = ttk.Button(mods_frame, text="Second Chance", command=self._on_second_chance)
        sc_btn.grid(row=0, column=0, sticky="w", padx=4, pady=4)

        ft_btn = ttk.Button(mods_frame, text="Flip Three", command=self._on_flip_three)
        ft_btn.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        x2_btn = ttk.Button(mods_frame, text="x2", command=self._on_x2)
        x2_btn.grid(row=0, column=2, sticky="w", padx=4, pady=4)

        add_frame = ttk.Frame(line_frame)
        add_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))
        ttk.Label(add_frame, text="Add points:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        # Arrange +N buttons in two rows to avoid a long single row.
        plus_values = (2, 4, 6, 8, 10)
        for idx, m in enumerate(plus_values):
            r = 0 if idx < 3 else 1
            c = (idx % 3) + 1
            btn = ttk.Button(add_frame, text=f"+{m}", command=lambda v=m: self._on_add_points(v))
            btn.grid(row=r, column=c, sticky="w", padx=4, pady=4)

        # Summary / output labels
        out_frame = ttk.Frame(self)
        out_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        out_frame.columnconfigure(0, weight=1)

        # Reduce output text size (~0.8x)
        self.bust_label = ttk.Label(out_frame, text="Bust next: --", font=("Segoe UI", 12, "bold"))
        self.bust_label.grid(row=0, column=0, sticky="w", padx=2, pady=2)

        self.recommend_label = ttk.Label(out_frame, text="Recommendation: --", font=("Segoe UI", 12, "bold"))
        self.recommend_label.grid(row=0, column=1, sticky="w", padx=(20, 2), pady=2)

        self.ev_label = ttk.Label(out_frame, text="EV (take 1 then stay): --", font=("Segoe UI", 13))
        self.ev_label.grid(row=1, column=0, sticky="w", padx=2, pady=2)

        self.threshold_label = ttk.Label(out_frame, text="Bust threshold (P*): --", font=("Segoe UI", 13))
        self.threshold_label.grid(row=1, column=1, sticky="w", padx=(20, 2), pady=2)

        self.flip3_label = ttk.Label(out_frame, text="Flip Three: --", font=("Segoe UI", 12))
        self.flip3_label.grid(row=2, column=0, sticky="w", padx=2, pady=2)

        self.bank_label = ttk.Label(out_frame, text="Bank: 0", font=("Segoe UI", 12))
        self.bank_label.grid(row=2, column=1, sticky="w", padx=(20, 2), pady=2)

        self.numbers_label = ttk.Label(out_frame, text="Numbers: []", font=("Segoe UI", 12))
        self.numbers_label.grid(row=3, column=0, sticky="w", padx=2, pady=2)

        # Initialize deck count labels now that widgets exist
        self._refresh_deck_counts()

        # Control buttons
        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        controls.columnconfigure(0, weight=1)

        reset_btn = ttk.Button(controls, text="New Shoe (reset all)", command=self._on_reset_round)
        reset_btn.grid(row=0, column=0, sticky="w", padx=2)

        clear_line_btn = ttk.Button(controls, text="Clear line", command=self._on_clear_line)
        clear_line_btn.grid(row=0, column=1, sticky="w", padx=8)

    @staticmethod
    def _make_checkbox_images(size: int = 24) -> tuple[tk.PhotoImage, tk.PhotoImage]:
        """
        Create simple checkbox indicator images.

        ttk doesn't provide a reliable cross-platform way to scale the indicator
        box independently from the text, so we draw our own larger box (and a
        checkmark for the selected state).
        """
        bg = "#ffffff"
        border = "#333333"
        check = "#1a73e8"

        off = tk.PhotoImage(width=size, height=size)
        on = tk.PhotoImage(width=size, height=size)

        # fill background
        off.put(bg, to=(0, 0, size, size))
        on.put(bg, to=(0, 0, size, size))

        # border thickness
        t = max(2, size // 12)
        # draw border rectangle
        for img in (off, on):
            # top/bottom
            img.put(border, to=(0, 0, size, t))
            img.put(border, to=(0, size - t, size, size))
            # left/right
            img.put(border, to=(0, 0, t, size))
            img.put(border, to=(size - t, 0, size, size))

        # draw checkmark on "on"
        # simple diagonal strokes scaled by size
        def put_pixel(x: int, y: int) -> None:
            if 0 <= x < size and 0 <= y < size:
                on.put(check, (x, y))

        # coordinates as fractions of the box
        x1, y1 = int(size * 0.25), int(size * 0.55)
        x2, y2 = int(size * 0.42), int(size * 0.72)
        x3, y3 = int(size * 0.78), int(size * 0.30)

        # stroke thickness
        sw = max(2, size // 10)

        # line x1,y1 -> x2,y2
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for s in range(steps + 1):
            x = x1 + (x2 - x1) * s // steps
            y = y1 + (y2 - y1) * s // steps
            for dx in range(-sw, sw + 1):
                for dy in range(-sw, sw + 1):
                    put_pixel(x + dx, y + dy)

        # line x2,y2 -> x3,y3
        steps = max(abs(x3 - x2), abs(y3 - y2), 1)
        for s in range(steps + 1):
            x = x2 + (x3 - x2) * s // steps
            y = y2 + (y3 - y2) * s // steps
            for dx in range(-sw, sw + 1):
                for dy in range(-sw, sw + 1):
                    put_pixel(x + dx, y + dy)

        return off, on

    # ----------------------------------------------------------------- logic
    @staticmethod
    def _fmt_pct(x: float) -> str:
        return f"{100.0 * x:.1f}%"

    def _recompute(self) -> None:
        # Reduce CPU: don't simulate Flip Three unless it is active.
        out = self.decision.compute(self.state, self.seen_counts, include_flip_three=self.state.flip_three_active)

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

        # Notes panel removed (kept UI compact).

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
        if not getattr(self, "_suppress_recompute", False):
            self._recompute()

    def _sync_line_numbers_from_vars(self) -> None:
        """Update the active line numbers from the checkbuttons and sync deck counts."""
        prev_nums = set(self.state.numbers)
        nums = {n for n, var in self._line_number_vars.items() if var.get()}

        # Batch deck updates to avoid recomputing repeatedly while toggling.
        self._suppress_recompute = True
        try:
            for n in nums - prev_nums:
                self._adjust_seen(str(n), +1)
        finally:
            self._suppress_recompute = False

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
            self._suppress_recompute = True
            try:
                self._adjust_seen("secondchance", +1)
            finally:
                self._suppress_recompute = False
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
            self._suppress_recompute = True
            try:
                self._adjust_seen("flipthree", +1)
            finally:
                self._suppress_recompute = False
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
            self._suppress_recompute = True
            try:
                self._adjust_seen("x2", +1)
            finally:
                self._suppress_recompute = False
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
        self._suppress_recompute = True
        try:
            self._adjust_seen(f"+{amount}", +1)
        finally:
            self._suppress_recompute = False
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

