from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import mss
import numpy as np
import tkinter as tk
from tkinter import ttk

from .decision_engine import DecisionEngine
from .recognition_engine import TemplateRecognizer
from .state import RoundState
from .watch import _derive_state  # reuse state derivation from detections


@dataclass
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int

    @property
    def bbox(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


class Flip7UI(tk.Tk):
    def __init__(
        self,
        recognizer: TemplateRecognizer,
        decision: DecisionEngine,
        region: CaptureRegion,
        interval_ms: int = 700,
    ) -> None:
        super().__init__()
        self.title("Flip7 Helper")
        self.recognizer = recognizer
        self.decision = decision
        self.region = region
        self.interval_ms = interval_ms
        self._running = True
        self._sct = mss.mss()

        self._build_widgets()
        self.after(self.interval_ms, self._tick)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)

        header = ttk.Label(self, text="Flip 7 Real-time Helper", font=("Segoe UI", 14, "bold"))
        header.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self.region_label = ttk.Label(
            self,
            text=f"Region: left={self.region.left}, top={self.region.top}, w={self.region.width}, h={self.region.height}",
            font=("Segoe UI", 9),
        )
        self.region_label.grid(row=1, column=0, sticky="w", padx=10)

        sep = ttk.Separator(self, orient="horizontal")
        sep.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.status_label = ttk.Label(self, text="Capturing...", font=("Segoe UI", 9))
        self.status_label.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 4))

        self.bust_label = ttk.Label(self, text="Bust next: --", font=("Segoe UI", 12, "bold"))
        self.bust_label.grid(row=4, column=0, sticky="w", padx=10, pady=2)

        self.ev_label = ttk.Label(self, text="EV (take 1 then stay): --", font=("Segoe UI", 11))
        self.ev_label.grid(row=5, column=0, sticky="w", padx=10, pady=2)

        self.flip3_label = ttk.Label(self, text="Flip Three (if active): --", font=("Segoe UI", 9))
        self.flip3_label.grid(row=6, column=0, sticky="w", padx=10, pady=2)

        self.numbers_label = ttk.Label(self, text="Numbers: []", font=("Segoe UI", 10))
        self.numbers_label.grid(row=7, column=0, sticky="w", padx=10, pady=2)

        self.bank_label = ttk.Label(self, text="Bank (stay now): 0", font=("Segoe UI", 10))
        self.bank_label.grid(row=8, column=0, sticky="w", padx=10, pady=2)

        self.recommend_label = ttk.Label(self, text="Recommendation: --", font=("Segoe UI", 12, "bold"))
        self.recommend_label.grid(row=9, column=0, sticky="w", padx=10, pady=(6, 4))

        self.notes_text = tk.Text(self, height=4, width=60, wrap="word")
        self.notes_text.grid(row=10, column=0, sticky="nsew", padx=10, pady=(4, 8))
        self.notes_text.configure(state="disabled")

        self.rowconfigure(10, weight=1)

    def _capture_frame(self) -> Optional[np.ndarray]:
        try:
            img = self._sct.grab(self.region.bbox)
        except Exception as exc:  # pragma: no cover - defensive
            self.status_label.config(text=f"Capture error: {exc}")
            return None
        # mss returns BGRA; convert to numpy BGR
        frame = np.array(img)
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]
        return frame

    @staticmethod
    def _fmt_pct(x: float) -> str:
        return f"{100.0 * x:.1f}%"

    def _update_from_state(self, state: RoundState, notes: Tuple[str, ...], bust_next: float, ev_next: float,
                           bust_three: float, ev_three: float) -> None:
        nums_sorted = sorted(state.numbers)
        bank = state.current_bank_value()
        self.numbers_label.config(text=f"Numbers: {nums_sorted}")
        self.bank_label.config(
            text=f"Bank (stay now): {bank}   x2={state.multiplier_x2}  +mods={state.add_points}  SC={state.has_second_chance}"
        )

        self.bust_label.config(text=f"Bust next: {self._fmt_pct(bust_next)}")
        self.ev_label.config(text=f"EV (take 1 then stay): {ev_next:.2f}")

        if state.flip_three_active:
            self.flip3_label.config(
                text=f"Flip Three: bust={self._fmt_pct(bust_three)}, EV≈{ev_three:.2f}"
            )
        else:
            self.flip3_label.config(text="Flip Three: not active")

        # simple recommendation: compare EV to current bank
        if ev_next > bank + 0.01:
            rec = "Recommendation: TAKE another card"
        elif ev_next < bank - 0.01:
            rec = "Recommendation: STAY"
        else:
            rec = "Recommendation: NEUTRAL (EV≈bank)"
        self.recommend_label.config(text=rec)

        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        if notes:
            for n in notes:
                self.notes_text.insert("end", f"- {n}\n")
        else:
            self.notes_text.insert("end", "Using standard 94-card Flip 7 deck.")
        self.notes_text.configure(state="disabled")

    def _tick(self) -> None:
        if not self._running:
            return
        frame = self._capture_frame()
        if frame is None:
            self.after(self.interval_ms, self._tick)
            return

        detections = self.recognizer.recognize_array(frame)
        state = _derive_state(detections)
        out = self.decision.compute(state)
        self.status_label.config(text=f"Updated at {time.strftime('%H:%M:%S')}, {len(detections)} matches")
        self._update_from_state(
            state,
            out.notes,
            out.bust_probability_next,
            out.expected_value_next,
            out.bust_probability_flip_three,
            out.expected_value_flip_three,
        )
        self.after(self.interval_ms, self._tick)

    def on_close(self) -> None:
        self._running = False
        self.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Flip7 helper UI with live screen capture.")
    parser.add_argument("--assets", help="Assets folder containing templates (default: ./assets next to package).")
    parser.add_argument("--left", type=int, required=True, help="Capture region left (screen coordinates).")
    parser.add_argument("--top", type=int, required=True, help="Capture region top (screen coordinates).")
    parser.add_argument("--width", type=int, required=True, help="Capture region width.")
    parser.add_argument("--height", type=int, required=True, help="Capture region height.")
    parser.add_argument("--interval", type=int, default=700, help="Refresh interval in ms (default: 700).")
    parser.add_argument("--threshold", type=float, default=0.80, help="Template match threshold (0-1).")

    args = parser.parse_args()

    import os
    from pathlib import Path

    if args.assets:
        assets_dir = Path(args.assets).expanduser()
    else:
        # default to ../assets relative to this file
        assets_dir = Path(__file__).resolve().parents[1] / "assets"

    recognizer = TemplateRecognizer(assets_dir=assets_dir, match_threshold=args.threshold)
    decision = DecisionEngine()
    region = CaptureRegion(left=args.left, top=args.top, width=args.width, height=args.height)

    app = Flip7UI(recognizer, decision, region, interval_ms=args.interval)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

