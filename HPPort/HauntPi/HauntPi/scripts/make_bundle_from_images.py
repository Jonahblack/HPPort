#!/usr/bin/env python3
import argparse
from pathlib import Path
import cv2
import numpy as np
from src.products.jibjab_export import export_bundle


def ensure_bgra(img):
    if img is None:
        raise RuntimeError("Failed to load image")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        h, w = img.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=img.dtype)
        img = np.concatenate([img, alpha], axis=2)
    elif img.shape[2] == 4:
        pass
    else:
        raise RuntimeError(f"Unsupported image shape: {img.shape}")
    return img


def main():
    ap = argparse.ArgumentParser(description="Create a JibJab bundle from image files")
    ap.add_argument("--images", nargs="+", required=True, help="Input image files (PNG/JPG). If no alpha, will be made opaque.")
    ap.add_argument("--out", required=True, help="Output bundle directory")
    args = ap.parse_args()

    faces = []
    lms = []
    for path in args.images:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        img = ensure_bgra(img)
        faces.append(img)
        lms.append(None)  # landmarks optional; compose centers without them

    bundle_dir = export_bundle(faces, lms, args.out)
    print(bundle_dir)


if __name__ == "__main__":
    main()

