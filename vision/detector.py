"""YOLO11-pose person detector on ONNX Runtime (CPU). No PyTorch needed at run time.

Model output (1, 56, N): per candidate cx, cy, w, h, person score, then 17 keypoints x, y, score
(COCO order: 0 nose, 1-2 eyes, 3-4 ears, 5-6 shoulders, ...). Coordinates are in the letterboxed
model input; we map them back to the camera image.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


@dataclass
class Detection:
    box: np.ndarray         # x1, y1, x2, y2 in image pixels (whole person)
    score: float            # model confidence 0..1 (NOT a calibrated probability)
    keypoints: np.ndarray   # (17, 3): x, y, score


class PoseDetector:
    def __init__(self, model_path: str | Path, score_threshold: float = 0.40, iou_threshold: float = 0.7):
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size = int(inp.shape[2])               # 640 or 416, fixed at export
        self.score_threshold = score_threshold
        self.iou_threshold = iou_threshold

    def _letterbox(self, image: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        h, w = image.shape[:2]
        scale = min(self.size / h, self.size / w)
        nh, nw = round(h * scale), round(w * scale)
        pad_x, pad_y = (self.size - nw) / 2, (self.size - nh) / 2
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        top, left = round(pad_y - 0.1), round(pad_x - 0.1)
        canvas[top:top + nh, left:left + nw] = resized
        return canvas, scale, left, top

    def detect(self, image: np.ndarray) -> list[Detection]:
        canvas, scale, pad_x, pad_y = self._letterbox(image)
        blob = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.session.run(None, {self.input_name: blob})[0][0].T       # (N, 56)

        scores = out[:, 4]
        keep = scores >= self.score_threshold
        if not np.any(keep):
            return []
        out, scores = out[keep], scores[keep]

        cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
        xywh = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], axis=1)
        idx = cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), self.score_threshold, self.iou_threshold)
        if len(idx) == 0:
            return []

        h, w = image.shape[:2]
        dets = []
        for i in np.array(idx).flatten():
            x, y, ww, hh = xywh[i]
            box = np.array([x, y, x + ww, y + hh], dtype=np.float32)
            box[[0, 2]] = (box[[0, 2]] - pad_x) / scale
            box[[1, 3]] = (box[[1, 3]] - pad_y) / scale
            box[[0, 2]] = box[[0, 2]].clip(0, w)
            box[[1, 3]] = box[[1, 3]].clip(0, h)
            kpts = out[i, 5:].reshape(17, 3).copy()
            kpts[:, 0] = (kpts[:, 0] - pad_x) / scale
            kpts[:, 1] = (kpts[:, 1] - pad_y) / scale
            dets.append(Detection(box, float(scores[i]), kpts))
        dets.sort(key=lambda d: d.score, reverse=True)
        return dets
