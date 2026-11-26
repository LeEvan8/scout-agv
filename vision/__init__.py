"""Scout AGV vision: camera source -> YOLO11-pose (ONNX) -> head box -> multi-frame persistence -> overlay."""
from .detector import Detection, PoseDetector
from .head import head_box
from .overlay import draw_hud, draw_tracks
from .source import Frame, FrameSource
from .tracker import PersonTracker, Track

__all__ = ["Detection", "PoseDetector", "head_box", "draw_hud", "draw_tracks", "Frame", "FrameSource",
           "PersonTracker", "Track"]
