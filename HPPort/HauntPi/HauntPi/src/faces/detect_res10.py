import cv2, numpy as np
from pathlib import Path

_net = None

def _ensure_net(models_dir: Path):
    global _net
    if _net is None:
        prototxt = str(models_dir / "deploy.prototxt")
        weights = str(models_dir / "res10_300x300_ssd_iter_140000.caffemodel")
        _net = cv2.dnn.readNetFromCaffe(prototxt, weights)
    return _net

def detect_faces_bgr(frame_bgr, models_dir="models", conf=0.5):
    net = _ensure_net(Path(models_dir))
    (h, w) = frame_bgr.shape[:2]
    blob = cv2.dnn.blobFromImage(frame_bgr, 1.0, (300, 300), (104.0, 177.0, 123.0))
    net.setInput(blob)
    dets = net.forward()
    boxes = []
    for i in range(dets.shape[2]):
        confidence = dets[0, 0, i, 2]
        if confidence > conf:
            box = dets[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")
            x1, y1 = max(0, x1-10), max(0, y1-10)
            x2, y2 = min(w, x2+10), min(h, y2+10)
            boxes.append((x1, y1, x2-x1, y2-y1, float(confidence)))
    return boxes
