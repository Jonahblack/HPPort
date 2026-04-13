#!/usr/bin/env python3
import argparse, cv2
from src.products.scream_synth import synthesize_scream
from src.common.video import make_writer
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="Path to a 256x256 face image")
    ap.add_argument("--out", required=True, help="Output mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--secs", type=int, default=3)
    args = ap.parse_args()
    img = cv2.imread(args.image)
    frames = synthesize_scream(img, fps=args.fps, duration_sec=args.secs)
    w = make_writer(args.out, args.fps, (img.shape[1], img.shape[0]))
    for f in frames: w.write(f)
    w.release()
if __name__ == "__main__":
    main()
