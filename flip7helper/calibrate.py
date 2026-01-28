from __future__ import annotations

import argparse
from pathlib import Path

import mss
import numpy as np
import cv2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture a single screen region with mss and save it as a PNG to help calibrate Flip7 UI coordinates."
    )
    parser.add_argument("--left", type=int, required=True, help="Capture region left (screen coordinates).")
    parser.add_argument("--top", type=int, required=True, help="Capture region top (screen coordinates).")
    parser.add_argument("--width", type=int, required=True, help="Capture region width.")
    parser.add_argument("--height", type=int, required=True, help="Capture region height.")
    parser.add_argument(
        "--out",
        type=str,
        default="flip7_calibration.png",
        help="Output image path (default: flip7_calibration.png in current directory).",
    )

    args = parser.parse_args()

    monitor = {"left": args.left, "top": args.top, "width": args.width, "height": args.height}
    out_path = Path(args.out).expanduser()

    with mss.mss() as sct:
        img = sct.grab(monitor)
        frame = np.array(img)
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]  # BGRA -> BGR

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    print(f"Saved calibration capture to: {out_path}")
    print(f"Region used: left={args.left}, top={args.top}, width={args.width}, height={args.height}")

