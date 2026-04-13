from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json

@dataclass
class MarkerTracking:
    enabled: bool = False
    expected: int | None = None  # default to number of slots
    hsv_ranges: list | None = None
    min_r_ratio: float = 0.04
    max_r_ratio: float = 0.20
    smooth_alpha: float = 0.8
    dropout_max: int = 8
    max_match_dist_ratio: float = 0.15
    mouth_nudge_ratio: float = 0.12

@dataclass
class Slot:
    name: str
    anchor: str
    size: tuple[int,int]
    offset: tuple[int,int] = (0,0)
    rotation_from: str | None = "eyes"
    position: tuple[int,int] | None = None  # absolute position (x,y) where the anchor should land

@dataclass
class Template:
    name: str
    background_video: str | None
    fps: int = 30
    resolution: tuple[int,int] | None = None
    duration_sec: int = 5
    slots: list[Slot] = None
    marker_tracking: MarkerTracking | None = None

    @staticmethod
    def load(path: str | Path) -> "Template":
        data = json.loads(Path(path).read_text())
        # Support templates that may not include all fields
        slots = []
        for s in data.get("slots", []):
            slots.append(Slot(
                name=s.get("name", "slot"),
                anchor=s.get("anchor", "mouth_center"),
                size=tuple(s.get("size", (200, 240))),
                offset=tuple(s.get("offset", (0, 0))),
                rotation_from=s.get("rotation_from", "eyes"),
                position=(tuple(s.get("position")) if s.get("position") is not None else None)
            ))
        mt = None
        if data.get("marker_tracking"):
            mtd = data["marker_tracking"]
            mt = MarkerTracking(
                enabled=bool(mtd.get("enabled", False)),
                expected=mtd.get("expected"),
                hsv_ranges=mtd.get("hsv_ranges"),
                min_r_ratio=float(mtd.get("min_r_ratio", 0.04)),
                max_r_ratio=float(mtd.get("max_r_ratio", 0.20)),
                smooth_alpha=float(mtd.get("smooth_alpha", 0.8)),
                dropout_max=int(mtd.get("dropout_max", 8)),
                max_match_dist_ratio=float(mtd.get("max_match_dist_ratio", 0.15)),
                mouth_nudge_ratio=float(mtd.get("mouth_nudge_ratio", 0.12)),
            )
        return Template(
            name=data.get("name","template"),
            background_video=data.get("background_video"),
            fps=int(data.get("fps", 30)),
            resolution=tuple(data["resolution"]) if data.get("resolution") else None,
            duration_sec=int(data.get("duration_sec", 5)),
            slots=slots,
            marker_tracking=mt
        )
