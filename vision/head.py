"""Head box from pose keypoints. Locates a head only; never identifies who it is.

Fallback ladder (first that applies wins):
  1. >= 2 confident face points (nose, eyes, ears)  -> box around them              (from_face=True)
  2. any weaker face point, at least one >= 0.5      -> centred on them, sized from the shoulders (from_face=True)
  3. shoulders only (back turned, face hidden)       -> above the shoulders          (estimate)
  4. nothing useful                                  -> top of the person box        (estimate)
"""
from __future__ import annotations

import numpy as np

FACE = [0, 1, 2, 3, 4]          # nose, left eye, right eye, left ear, right ear
SHOULDERS = [5, 6]
STRONG = 0.5
WEAK = 0.3


def _square(cx: float, cy: float, size: float) -> np.ndarray:
    return np.array([cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2], dtype=np.float32)


def head_box(person_box: np.ndarray, kpts: np.ndarray) -> tuple[np.ndarray, bool]:
    """Return (x1, y1, x2, y2), from_face. from_face=False means an estimate (drawn as 'est.')."""
    x1, y1, x2, y2 = (float(v) for v in person_box)
    bw, bh = x2 - x1, y2 - y1
    min_size, max_size = 0.06 * max(bw, bh), max(0.9 * bw, 0.3 * bh)

    face, sh = kpts[FACE], kpts[SHOULDERS]
    strong_face = face[face[:, 2] >= STRONG]
    weak_face = face[face[:, 2] >= WEAK]
    sh_vis = sh[sh[:, 2] >= STRONG]
    sh_y = float(sh_vis[:, 1].mean()) if len(sh_vis) else None
    sh_w = abs(float(sh[0, 0] - sh[1, 0])) if len(sh_vis) == 2 else None

    if len(strong_face) >= 2:                                           # 1
        cx, cy = strong_face[:, 0].mean(), strong_face[:, 1].mean()
        size = 1.9 * max(np.ptp(strong_face[:, 0]), np.ptp(strong_face[:, 1]))
        if sh_w is not None:
            size = max(size, 0.6 * sh_w)          # profile view: face points bunch together
        size = float(np.clip(size, min_size, max_size))
        box, from_face = _square(cx, cy - 0.15 * size, size), True
    elif len(strong_face) >= 1:                                         # 2
        w = weak_face[:, 2]
        cx = float((weak_face[:, 0] * w).sum() / w.sum())
        cy = float((weak_face[:, 1] * w).sum() / w.sum())
        if sh_y is not None and sh_y > cy:
            size = 1.3 * (sh_y - cy)              # face-to-shoulder drop ~ 3/4 of a head
        else:
            size = 0.15 * bh
        size = float(np.clip(size, min_size, max_size))
        box, from_face = _square(cx, cy - 0.15 * size, size), True
    elif len(sh_vis) >= 1:                                              # 3
        cx = float(sh_vis[:, 0].mean())
        size = 0.6 * sh_w if sh_w is not None else 0.15 * bh
        size = float(np.clip(size, min_size, max_size))
        box, from_face = _square(cx, sh_y - 0.75 * size, size), False
    else:                                                               # 4
        size = float(np.clip(min(0.6 * bw, 0.25 * bh), 0, max_size))
        cx = (x1 + x2) / 2
        box, from_face = np.array([cx - size / 2, y1, cx + size / 2, y1 + size], dtype=np.float32), False

    box[[0, 2]] = box[[0, 2]].clip(x1, x2)
    box[[1, 3]] = box[[1, 3]].clip(y1, y2)
    return box, from_face
