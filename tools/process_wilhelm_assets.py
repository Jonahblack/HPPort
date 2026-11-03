#!/usr/bin/env python3
"""Validate the entire catalog and atomically publish versioned review artifacts.

Runtime plays original video through a bounded decoder. No old PNG caches or
accelerated cropped MP4s are consumed. This tool never rewrites source media.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renderer.asset_catalog import load_catalog


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_clip(spec, output=None):
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(spec["path"])
    try:
        if not cap.isOpened():
            raise ValueError(f"Cannot open {spec['path']}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if abs(fps - spec["source_fps"]) > 0.05:
            raise ValueError(f"{spec['id']}: FPS mismatch ({fps})")
        start, end = spec.get("start_frame", 0), spec.get("end_frame") or total
        if not 0 <= start < end <= total:
            raise ValueError(f"{spec['id']}: invalid source range")
        wanted = set(np.linspace(start, end - 1, 8, dtype=int).tolist())
        samples = []
        first = last = None
        count = 0
        # Decode sequentially to detect corrupt/truncated media, not only readable endpoints.
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if start <= count < end:
                if first is None:
                    first = frame.copy()
                last = frame
                if count in wanted:
                    thumb = cv2.resize(frame, (320, 180))
                    cv2.putText(thumb, f"{spec['id']} {count / fps:.2f}s", (8, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                    samples.append(thumb)
            count += 1
        if count != total or first is None or last is None:
            raise ValueError(f"{spec['id']}: decoded {count} frames, expected {total}")
        if output is not None:
            folder = output / spec["id"]
            folder.mkdir()
            for name, image in (("first.png", first), ("last.png", last),
                                ("contact_sheet.jpg", np.concatenate(samples, axis=1))):
                if not cv2.imwrite(str(folder / name), image):
                    raise OSError(f"Could not write {folder / name}")
        return {
            "id": spec["id"], "source_file": spec["source_file"],
            "sha256": fingerprint(spec["path"]), "fps": fps, "width": width,
            "height": height, "source_frames": total, "start_frame": start,
            "end_frame": end, "playback_seconds": (end - start) / fps,
            "entry_scene": spec["entry_scene"], "exit_scene": spec["exit_scene"],
            "runtime_enabled": spec["runtime_enabled"], "review_status": spec["review_status"],
            "audio": "muted",
        }
    finally:
        cap.release()


def process(manifest, check_only=False):
    catalog = load_catalog(manifest)
    root = Path(catalog["manifest_path"]).parent
    assets = (root / catalog["target_assets_dir"]).resolve()
    source = (root / catalog["source_dir"]).resolve()
    if not assets.is_relative_to(root) or assets == root or assets.is_relative_to(source):
        raise ValueError("Generated assets must stay in the project and outside source_dir")
    for still in catalog["stills"]:
        file = (source / still["source_file"]).resolve()
        target = (assets / still["target_file"]).resolve()
        if not file.is_relative_to(source) or not target.is_relative_to(assets) or not file.is_file():
            raise ValueError(f"Invalid or missing still: {still['source_file']}")
    if check_only:
        return {"clips": [inspect_clip(c) for c in catalog["clips"]]}
    assets.mkdir(parents=True, exist_ok=True)
    review = assets / "review"
    review.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stage-", dir=review) as temporary:
        stage = Path(temporary)
        clips = [inspect_clip(c, stage) for c in catalog["clips"]]
        manifest_hash = fingerprint(catalog["manifest_path"])
        identity = hashlib.sha256(json.dumps([manifest_hash, clips], sort_keys=True).encode()).hexdigest()[:20]
        report = {
            "manifest_sha256": manifest_hash, "revision": identity, "clips": clips,
            "note": "Technical validation only. Candidate boundaries still require visual review.",
        }
        (stage / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        rows = ["# Wilhelm asset review", "", report["note"], "",
                "| Clip | Source FPS | Playback seconds | Runtime | Review status |",
                "| --- | --- | --- | --- | --- |"]
        for clip in clips:
            rows.append(f"| {clip['id']} | {clip['fps']} | {clip['playback_seconds']:.2f} | {clip['runtime_enabled']} | {clip['review_status']} |")
        rows.extend(["", "Inspect each clip's first.png, last.png, and contact_sheet.jpg alongside its neighbors."])
        (stage / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
        destination = review / identity
        if not destination.exists():
            os.replace(stage, destination)
        # Still copies are individually atomic and are never used to fabricate video endpoints.
        for still in catalog["stills"]:
            target = assets / still["target_file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=target.parent, suffix=target.suffix)
            os.close(fd)
            try:
                shutil.copyfile(source / still["source_file"], name)
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        # Publish the complete report pointer only after every clip and still succeeded.
        fd, name = tempfile.mkstemp(dir=assets, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"revision": identity, "report": f"review/{identity}/report.json",
                           "manifest_sha256": manifest_hash}, stream, indent=2)
            os.replace(name, assets / "scene_catalog.json")
        finally:
            if os.path.exists(name):
                os.unlink(name)
        print(f"Review artifacts: {destination}")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(Path(__file__).resolve().parents[1] / "wilhelm_asset_manifest.json"))
    parser.add_argument("--check", action="store_true", help="Fully validate without writing assets")
    args = parser.parse_args()
    try:
        report = process(args.manifest, args.check)
    except Exception as exc:
        print(f"Asset processing failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {len(report['clips'])} clips at native speed. Embedded audio stays muted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
