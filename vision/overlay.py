"""Drawing: GREEN head box + 'person 87%'. Dashed-looking thinner box when the head is estimated."""
from __future__ import annotations

import cv2
import numpy as np

from .tracker import Track

GREEN = (60, 220, 60)       # BGR
DARK = (20, 20, 20)


GREY = (150, 150, 150)


def draw_tracks(image: np.ndarray, tracks: list[Track], caught_ids: set | None = None,
                target_id: int | None = None) -> None:
    """Green = hiding person, extra-thick = current target, grey = already caught this round."""
    caught_ids = caught_ids or set()
    for t in tracks:
        x1, y1, x2, y2 = (int(v) for v in t.head)
        caught = t.id in caught_ids
        color = GREY if caught else GREEN
        thick = 5 if t.id == target_id else (3 if t.head_from_face else 2)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thick)
        if caught:
            label = "caught"
        else:
            label = f"person {round(t.score * 100)}%" + ("" if t.head_from_face else " (est.)")
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        ty = max(y1 - 6, th + 4)
        lx = int(np.clip(x1, 0, max(0, image.shape[1] - tw - 6)))   # keep the label inside the frame
        cv2.rectangle(image, (lx, ty - th - 4), (lx + tw + 6, ty + 4), color, -1)
        cv2.putText(image, label, (lx + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, DARK, 2, cv2.LINE_AA)


def draw_hud(image: np.ndarray, lines: list[str]) -> None:
    for i, text in enumerate(lines):
        y = 22 + i * 22
        cv2.putText(image, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, DARK, 4, cv2.LINE_AA)
        cv2.putText(image, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
