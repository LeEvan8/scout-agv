"""Scout AGV Phase 2a — vision only (no robot). Live camera -> green head box + confidence.

    .venv\\Scripts\\python.exe vision_demo.py                      (laptop webcam 0)
    .venv\\Scripts\\python.exe vision_demo.py --source 1           (another webcam)
    .venv\\Scripts\\python.exe vision_demo.py --source http://<camera-ip>/stream   (ESP32 MJPEG later)
    .venv\\Scripts\\python.exe vision_demo.py --model models/yolo11n-pose-416.onnx (faster, shorter range)

Q or ESC quits. Nothing is recorded or saved; video stays on this laptop.
"""
import argparse
import sys
import time

import cv2

from vision import FrameSource, PersonTracker, PoseDetector, draw_hud, draw_tracks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="webcam number or MJPEG URL")
    ap.add_argument("--model", default="models/yolo11n-pose-640.onnx")
    ap.add_argument("--conf", type=float, default=0.40, help="minimum model confidence (0..1)")
    args = ap.parse_args()

    detector = PoseDetector(args.model, score_threshold=args.conf)
    tracker = PersonTracker()
    source = FrameSource(args.source).start()
    window = "Scout AGV vision (Q to quit)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    last_index, fps, t_prev = -1, 0.0, time.perf_counter()
    try:
        while True:
            frame = source.latest()
            if frame is None or frame.index == last_index:   # no new image yet
                if cv2.waitKey(5) & 0xFF in (ord("q"), 27):
                    break
                continue
            last_index = frame.index

            t0 = time.perf_counter()
            tracks = tracker.update(detector.detect(frame.image))
            infer_ms = (time.perf_counter() - t0) * 1000
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 * (1 / max(now - t_prev, 1e-3))
            t_prev = now

            view = frame.image.copy()
            draw_tracks(view, tracks)
            draw_hud(view, [
                f"{len(tracks)} person(s)   {fps:4.1f} fps   detect {infer_ms:3.0f} ms   frame age {frame.age * 1000:3.0f} ms",
                f"source {args.source}: {source.status}",
            ])
            cv2.imshow(window, view)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        source.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
