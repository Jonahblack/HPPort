#!/usr/bin/env python3
import argparse
from src.products.jibjab_compose import compose_video
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--bundles", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    compose_video(args.template, args.bundles, args.out)
if __name__ == "__main__":
    main()
