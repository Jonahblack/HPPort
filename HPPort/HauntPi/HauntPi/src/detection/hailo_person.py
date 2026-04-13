# Hailo wrapper expecting hailo_platform to be installed on the Pi.
try:
    from hailo_platform import HailoYOLO
except Exception:
    HailoYOLO = None

class HailoPerson:
    def __init__(self, hef_path: str, threshold: float = 0.6):
        if HailoYOLO is None:
            raise RuntimeError("hailo_platform not available. Install Hailo SDK.")
        self._yolo = HailoYOLO(model_path=hef_path, threshold=threshold)

    def persons(self, frame_bgr):
        detections = self._yolo.infer(frame_bgr)
        out = []
        for d in detections:
            try:
                if getattr(d, "label", "") == "person" and float(getattr(d, "confidence", 0)) >= self._yolo.threshold:
                    x, y, w, h = d.bbox
                    out.append((int(x), int(y), int(w), int(h), float(d.confidence)))
            except Exception:
                continue
        return out
