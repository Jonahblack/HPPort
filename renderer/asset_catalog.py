"""Validated, path-resolved scene descriptions shared by playback and asset tools."""

import json
import math
from pathlib import Path


def load_catalog(manifest_path):
    path = Path(manifest_path).resolve()
    with path.open(encoding="utf-8") as stream:
        catalog = json.load(stream)
    if catalog.get("version") != "2.0":
        raise ValueError("Scene playback requires a version 2.0 asset manifest")
    scenes = catalog.get("scenes", {})
    if not scenes or catalog.get("initial_scene") not in scenes:
        raise ValueError("Manifest needs scenes and a valid initial_scene")
    for name, scene in scenes.items():
        if not isinstance(scene, dict) or not isinstance(scene.get("activity"), str):
            raise ValueError(f"Scene {name} needs an activity")
    canvas = catalog.get("canvas_size", [1280, 720])
    if not isinstance(canvas, list) or len(canvas) != 2 or any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in canvas):
        raise ValueError("canvas_size must contain two positive integers")
    source = (path.parent / catalog["source_dir"]).resolve()
    seen = set()
    for item in catalog.get("clips", []):
        name = item["id"]
        if name in seen:
            raise ValueError(f"Duplicate clip ID: {name}")
        seen.add(name)
        if item["entry_scene"] not in scenes or item["exit_scene"] not in scenes:
            raise ValueError(f"Unknown scene in {name}")
        fps = item.get("source_fps", 24)
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"Invalid source_fps in {name}")
        item["source_fps"] = fps
        item.setdefault("runtime_enabled", False)
        item.setdefault("review_status", "preview")
        if not isinstance(item["runtime_enabled"], bool):
            raise ValueError(f"runtime_enabled must be boolean in {name}")
        start, end = item.get("start_frame", 0), item.get("end_frame")
        if isinstance(start, bool) or not isinstance(start, int) or start < 0 or (end is not None and (isinstance(end, bool) or not isinstance(end, int) or end <= start)):
            raise ValueError(f"Invalid source range in {name}")
        fade = item.get("crossfade_ms", 0)
        if isinstance(fade, bool) or not isinstance(fade, (int, float)) or not math.isfinite(fade) or fade < 0:
            raise ValueError(f"Invalid crossfade_ms in {name}")
        if item.get("audio", "muted") != "muted":
            raise ValueError(f"Embedded audio is not supported: {name}")
        if item.get("checkpoints", ["source_end"]) != ["source_end"]:
            raise ValueError(f"{name}: this player supports source_end checkpoints only")
        if item.get("runtime_enabled") and item.get("review_status") not in ("candidate", "approved"):
            raise ValueError(f"Runtime clip {name} must be a reviewed candidate or approved")
        file = (source / item["source_file"]).resolve()
        if not file.is_relative_to(source):
            raise ValueError(f"Source escapes source_dir: {name}")
        item["path"] = str(file)
    catalog["manifest_path"] = str(path)
    return catalog
