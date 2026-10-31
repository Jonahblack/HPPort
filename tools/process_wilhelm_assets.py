#!/usr/bin/env python3
"""Non-destructive processing pipeline for Wilhelm character assets.

Extracts, crops, and normalizes video transitions and idle clips from
Wilhelm_Generated/ into assets/ without modifying the raw originals.
Generates pre-decoded frame caches for zero-runtime CPU decoding on Raspberry Pi 5.
Supports an extensible asset manifest for future graphics.
"""

import os
import sys
import json
import shutil
from typing import Dict, Any, Optional

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


MANIFEST_PATH = "wilhelm_asset_manifest.json"

DEFAULT_MANIFEST: Dict[str, Any] = {
    "version": "1.0",
    "source_dir": "Wilhelm_Generated",
    "target_assets_dir": "assets",
    "transitions": [
        {
            "id": "look_up",
            "source_file": "look_up_from_book.mp4",
            "target_file": "transitions/look_up_cropped.mp4",
            "frames_dir": "transitions/look_up_frames",
            "start_frame": 78,
            "end_frame": 138,
            "target_fps": 30,
            "description": "Wake transition: Wilhelm raises head from book to greet visitor"
        },
        {
            "id": "return_to_book",
            "source_file": "return_to_book.mp4",
            "target_file": "transitions/return_to_book_cropped.mp4",
            "frames_dir": "transitions/return_to_book_frames",
            "start_frame": 12,
            "end_frame": 78,
            "target_fps": 30,
            "description": "Dismissal transition: Wilhelm lowers head from visitor back to book"
        }
    ],
    "idles": [
        {
            "id": "page_flip",
            "source_file": "page_flip.mp4",
            "target_file": "idles/page_flip.mp4",
            "frames_dir": "idles/page_flip_frames",
            "loop": True,
            "description": "Autonomous reading idle: turns a page"
        },
        {
            "id": "tinker_box_study",
            "source_file": "tinker_box_study.mp4",
            "target_file": "idles/tinker_box_study.mp4",
            "frames_dir": "idles/tinker_study_frames",
            "loop": True,
            "description": "Autonomous tinkering idle: examines enchanted artifact"
        },
        {
            "id": "get_out_book",
            "source_file": "get_out_book.mp4",
            "target_file": "idles/get_out_book.mp4",
            "frames_dir": "idles/get_out_book_frames",
            "loop": False,
            "description": "Activity bridge: sets aside tinker box and gets out book"
        },
        {
            "id": "get_out_tinker_box",
            "source_file": "get_out_tinker_box.mp4",
            "target_file": "idles/get_out_tinker_box.mp4",
            "frames_dir": "idles/get_out_tinker_box_frames",
            "loop": False,
            "description": "Activity bridge: transition from empty desk to tinkering box"
        }
    ],
    "stills": [
        {
            "source_file": "A01_reading.png",
            "target_file": "wilhelm_reading.png",
            "alias_base": True
        },
        {
            "source_file": "end_conversation.png",
            "target_file": "wilhelm_desk_speaking_neutral.png"
        },
        {
            "source_file": "tinker_box.jpeg",
            "target_file": "wilhelm_tinker.jpeg"
        },
        {
            "source_file": "wilhelm_master_front.png",
            "target_file": "wilhelm_master_front.png"
        },
        {
            "source_file": "workshop_master_empty.png",
            "target_file": "workshop_master_empty.png"
        }
    ]
}


def load_manifest(path: str = MANIFEST_PATH) -> Dict[str, Any]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_MANIFEST


def save_manifest(manifest: Dict[str, Any], path: str = MANIFEST_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[Manifest] Saved asset manifest to {path}")


def process_stills(manifest: Dict[str, Any]) -> None:
    source_dir = manifest.get("source_dir", "Wilhelm_Generated")
    target_dir = manifest.get("target_assets_dir", "assets")
    os.makedirs(target_dir, exist_ok=True)

    for item in manifest.get("stills", []):
        src = os.path.join(source_dir, item["source_file"])
        dest = os.path.join(target_dir, item["target_file"])
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            print(f"[Stills] Copied: {src} -> {dest}")
            if item.get("alias_base"):
                base_dest = os.path.join(target_dir, "base.png")
                shutil.copy2(src, base_dest)
                print(f"[Stills] Aliased to default sprite: {dest} -> {base_dest}")
        else:
            print(f"[Stills] Warning: Source still '{src}' not found. Skipping.")


def crop_video_frames(
    src_path: str,
    dest_video_path: str,
    dest_frames_dir: str,
    start_frame: int,
    end_frame: int,
    target_fps: int = 30
) -> int:
    if not HAS_CV2:
        print(f"[Video] OpenCV not installed. Cannot crop '{src_path}'.")
        return 0

    if not os.path.exists(src_path):
        print(f"[Video] Source video '{src_path}' not found.")
        return 0

    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        print(f"[Video] Failed to open '{src_path}'.")
        return 0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start = max(0, min(start_frame, total_frames - 1))
    end = max(start + 1, min(end_frame, total_frames))
    expected_frames = end - start

    os.makedirs(os.path.dirname(dest_video_path), exist_ok=True)
    os.makedirs(dest_frames_dir, exist_ok=True)

    # Initialize video writer for cropped copy
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(dest_video_path, fourcc, target_fps, (width, height))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    saved_count = 0

    for f_idx in range(start, end):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
        frame_name = f"frame_{saved_count:03d}.png"
        frame_path = os.path.join(dest_frames_dir, frame_name)
        cv2.imwrite(frame_path, frame)
        saved_count += 1

    writer.release()
    cap.release()

    print(
        f"[Video] Cropped '{os.path.basename(src_path)}' ({start}..{end}) -> "
        f"{saved_count} frames saved to '{dest_frames_dir}' & '{dest_video_path}' @ {target_fps}fps"
    )
    return saved_count


def copy_or_cache_idles(manifest: Dict[str, Any]) -> None:
    source_dir = manifest.get("source_dir", "Wilhelm_Generated")
    target_dir = manifest.get("target_assets_dir", "assets")

    for idle in manifest.get("idles", []):
        src = os.path.join(source_dir, idle["source_file"])
        dest = os.path.join(target_dir, idle["target_file"])
        frames_dir = os.path.join(target_dir, idle["frames_dir"])

        if not os.path.exists(src):
            print(f"[Idle] Source '{src}' not found. Skipping.")
            continue

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        print(f"[Idle] Copied idle clip: {src} -> {dest}")

        if HAS_CV2 and idle.get("extract_frames"):
            os.makedirs(frames_dir, exist_ok=True)
            cap = cv2.VideoCapture(src)
            f_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_path = os.path.join(frames_dir, f"frame_{f_count:03d}.png")
                cv2.imwrite(frame_path, frame)
                f_count += 1
            cap.release()
            print(f"[Idle] Extracted {f_count} frames for '{idle['id']}' to '{frames_dir}'")


def process_transitions(manifest: Dict[str, Any]) -> None:
    source_dir = manifest.get("source_dir", "Wilhelm_Generated")
    target_dir = manifest.get("target_assets_dir", "assets")

    for trans in manifest.get("transitions", []):
        src = os.path.join(source_dir, trans["source_file"])
        dest_video = os.path.join(target_dir, trans["target_file"])
        dest_frames = os.path.join(target_dir, trans["frames_dir"])

        crop_video_frames(
            src_path=src,
            dest_video_path=dest_video,
            dest_frames_dir=dest_frames,
            start_frame=trans["start_frame"],
            end_frame=trans["end_frame"],
            target_fps=trans.get("target_fps", 30)
        )


def main():
    print("=" * 60)
    print("Wilhelm Asset Processing & Non-Destructive Ingestion Engine")
    print("=" * 60)
    manifest = load_manifest()
    save_manifest(manifest)

    print("\n1. Copying and registering master stills...")
    process_stills(manifest)

    print("\n2. Processing non-destructive transition crops and frame caches...")
    process_transitions(manifest)

    print("\n3. Ingesting autonomous idle video loops...")
    copy_or_cache_idles(manifest)

    print("\n[Complete] Asset ingestion finished successfully.")


if __name__ == "__main__":
    main()
