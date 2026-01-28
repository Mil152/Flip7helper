from __future__ import annotations
import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .decision_engine import DecisionEngine
from .recognition_engine import Detection, TemplateRecognizer
from .state import RoundState


def _derive_state(detections: Iterable[Detection]) -> RoundState:
    nums: Set[int] = set()
    has_sc = False
    has_ft = False
    has_x2 = False
    add_pts = 0

    for d in detections:
        lbl = d.label
        if lbl.isdigit():
            try:
                n = int(lbl)
                if 0 <= n <= 12:
                    nums.add(n)
            except ValueError:
                pass
        elif lbl == "secondchance":
            has_sc = True
        elif lbl == "flipthree":
            has_ft = True
        elif lbl == "x2":
            has_x2 = True
        elif lbl.startswith("+"):
            try:
                add_pts += int(lbl[1:])
            except ValueError:
                pass

    return RoundState(
        numbers=frozenset(nums),
        has_second_chance=has_sc,
        flip_three_active=has_ft,
        multiplier_x2=has_x2,
        add_points=add_pts,
    )


def _fmt_pct(x: float) -> str:
    return f"{100.0 * x:5.1f}%"


def _print_report(img: Path, state: RoundState, out) -> None:
    bank = state.current_bank_value()
    print()
    print(f"Screenshot: {img.name}")
    print(f"Detected numbers: {sorted(state.numbers)}")
    print(f"Current bank (if stay now): {bank}  (x2={state.multiplier_x2}, +mods={state.add_points}, SC={state.has_second_chance})")
    print(f"Bust prob next:      {_fmt_pct(out.bust_probability_next)}")
    print(f"EV (take 1 then stay): {out.expected_value_next:,.2f}")
    if state.flip_three_active:
        print(f"Bust prob (Flip 3):  {_fmt_pct(out.bust_probability_flip_three)}")
        print(f"EV (Flip 3 approx):  {out.expected_value_flip_three:,.2f}")
    if out.notes:
        for n in out.notes:
            print(f"Note: {n}")


@dataclass
class App:
    recognizer: TemplateRecognizer
    decision: DecisionEngine

    def handle_image(self, path: Path) -> None:
        # small delay to avoid partial writes
        time.sleep(0.10)
        detections = self.recognizer.recognize(path)
        state = _derive_state(detections)
        out = self.decision.compute(state)
        _print_report(path, state, out)


class NewImageHandler(FileSystemEventHandler):
    def __init__(self, app: App, exts: Set[str]) -> None:
        self.app = app
        self.exts = exts

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() not in self.exts:
            return
        self.app.handle_image(p)

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        p = Path(getattr(event, "dest_path", ""))
        if not p:
            return
        if p.suffix.lower() not in self.exts:
            return
        self.app.handle_image(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch a folder and compute Flip 7 bust probability + EV from screenshots.")
    parser.add_argument("--watch", required=True, help="Folder to watch for new screenshots.")
    parser.add_argument("--assets", default=str(Path(__file__).resolve().parents[1] / "assets"), help="Assets folder containing templates.")
    parser.add_argument("--threshold", type=float, default=0.80, help="Template match threshold (0-1).")
    parser.add_argument("--ext", action="append", default=[".png", ".jpg", ".jpeg", ".bmp"], help="Allowed image extensions (repeatable).")

    args = parser.parse_args()
    watch_dir = Path(args.watch).expanduser()
    assets_dir = Path(args.assets).expanduser()

    recognizer = TemplateRecognizer(assets_dir=assets_dir, match_threshold=args.threshold)
    decision = DecisionEngine()
    app = App(recognizer=recognizer, decision=decision)

    if not watch_dir.exists():
        raise SystemExit(f"Watch dir does not exist: {watch_dir}")

    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext}
    handler = NewImageHandler(app, exts)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)

    print(f"Watching: {watch_dir}")
    print(f"Templates: {assets_dir} ({len(list(recognizer.labels()))} loaded)")
    print("Waiting for new screenshots...")

    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()

