from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    x: int
    y: int
    w: int
    h: int


def _nms(dets: List[Detection], iou_threshold: float) -> List[Detection]:
    if not dets:
        return []
    dets = sorted(dets, key=lambda d: d.score, reverse=True)
    kept: List[Detection] = []

    def iou(a: Detection, b: Detection) -> float:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        union = (a.w * a.h) + (b.w * b.h) - inter
        return inter / union if union > 0 else 0.0

    for d in dets:
        if all(iou(d, k) < iou_threshold for k in kept):
            kept.append(d)
    return kept


class TemplateRecognizer:
    """
    Template-matching recognizer. Expects the assets folder to contain small
    template images named like:
    - numbers: 0.png..12.png
    - actions/modifiers: freeze.png, flipthree.png, secondchance.png, x2.png, +2.png, ...
    """

    def __init__(
        self,
        assets_dir: str | Path,
        match_threshold: float = 0.80,
        max_per_label: int = 20,
        nms_iou: float = 0.25,
    ) -> None:
        self.assets_dir = Path(assets_dir)
        self.match_threshold = float(match_threshold)
        self.max_per_label = int(max_per_label)
        self.nms_iou = float(nms_iou)
        self._templates: Dict[str, np.ndarray] = {}
        self._template_sizes: Dict[str, Tuple[int, int]] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        if not self.assets_dir.exists():
            raise FileNotFoundError(f"assets_dir not found: {self.assets_dir}")
        for p in sorted(self.assets_dir.glob("*.png")):
            label = p.stem.lower()
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            self._templates[label] = img
            h, w = img.shape[:2]
            self._template_sizes[label] = (w, h)
        if not self._templates:
            raise RuntimeError(f"No templates loaded from {self.assets_dir}")

    def labels(self) -> Iterable[str]:
        return self._templates.keys()

    def recognize_array(self, screen: np.ndarray) -> List[Detection]:
        """
        Run template matching on an in-memory grayscale image.
        """
        if screen.ndim == 3:
            screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        if screen.ndim != 2:
            raise ValueError("screen must be a 2D grayscale or 3-channel BGR array")
        detections: List[Detection] = []
        for label, templ in self._templates.items():
            th, tw = templ.shape[:2]
            sh, sw = screen.shape[:2]
            if th > sh or tw > sw:
                continue

            res = cv2.matchTemplate(screen, templ, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res >= self.match_threshold)
            if xs.size == 0:
                continue

            scores = res[ys, xs]
            idxs = np.argsort(scores)[::-1][: self.max_per_label]
            w, h = self._template_sizes[label]
            for i in idxs:
                detections.append(
                    Detection(
                        label=label,
                        score=float(scores[i]),
                        x=int(xs[i]),
                        y=int(ys[i]),
                        w=int(w),
                        h=int(h),
                    )
                )

        # suppress overlaps within same label, then globally
        per_label: Dict[str, List[Detection]] = {}
        for d in detections:
            per_label.setdefault(d.label, []).append(d)

        reduced: List[Detection] = []
        for lbl, ds in per_label.items():
            reduced.extend(_nms(ds, self.nms_iou))

        # global NMS helps reduce double-detections between similar templates (e.g. 1 vs 11)
        reduced = _nms(reduced, 0.15)
        return sorted(reduced, key=lambda d: d.score, reverse=True)

    def recognize(self, screenshot_path: str | Path) -> List[Detection]:
        """
        Backwards-compatible path-based API.
        """
        screen = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
        if screen is None:
            raise FileNotFoundError(f"could not read screenshot: {screenshot_path}")
        return self.recognize_array(screen)

