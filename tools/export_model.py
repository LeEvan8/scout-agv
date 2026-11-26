"""Recreate models/yolo11n-pose-640.onnx and -416.onnx (the .onnx files are not in git).

Needs PyTorch + ultralytics (~1 GB with the CPU build), so use a SEPARATE throwaway venv, not .venv:

    py -3.12 -m venv %TEMP%\yolo-export
    %TEMP%\yolo-export\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    %TEMP%\yolo-export\Scripts\python.exe -m pip install ultralytics onnx onnxslim
    %TEMP%\yolo-export\Scripts\python.exe tools\export_model.py
    (then delete %TEMP%\yolo-export)

License: YOLO11 weights are AGPL-3.0 (Ultralytics). Check before any commercial use.
"""
import shutil
from pathlib import Path

from ultralytics import YOLO

out = Path(__file__).resolve().parent.parent / "models"
out.mkdir(exist_ok=True)
for size in (640, 416):
    path = YOLO("yolo11n-pose.pt").export(format="onnx", imgsz=size, simplify=True, opset=17)
    shutil.move(path, out / f"yolo11n-pose-{size}.onnx")
    print("wrote", out / f"yolo11n-pose-{size}.onnx")
