import argparse, cv2
from pathlib import Path
from src.common.config import load_configs
from src.common.logging import setup_logging
from src.common.camera import Camera
from src.common.storage import new_run_dir, path_in
from src.detection.motion import MotionDetector
from src.detection.hailo_person import HailoPerson
from src.faces.detect_res10 import detect_faces_bgr
from src.faces.align import landmarks_and_aligned
from src.faces.cutout import alpha_cutout
from src.products.jibjab_export import export_bundle
from src.products.jibjab_compose import compose_video

def main():
    ap = argparse.ArgumentParser(description="JibJab capture → compose")
    ap.add_argument("--hef", required=True, help="Path to Hailo .hef model (YOLO w/ person class)")
    ap.add_argument("--template", default=None, help="Template JSON (overrides settings/jibjab.json)")
    args = ap.parse_args()
    cfg, repo = load_configs("jibjab.json")
    log = setup_logging()

    # camera
    cam = Camera(index=cfg["camera"]["index"], width=cfg["camera"]["width"], height=cfg["camera"]["height"],
                 fps=cfg["camera"]["fps"], backend=cfg["camera"].get("backend","auto"))
    motion = MotionDetector(**cfg["motion"])
    hailo = HailoPerson(hef_path=args.hef, threshold=cfg["hailo"]["person_conf"])

    try:
        log.info("Waiting for motion + person gate...")
        while True:
            ok, frame = cam.read()
            if not ok: log.error("Camera read failed"); break

            m = motion.poll(frame)
            if not m: continue

            persons = hailo.persons(frame)
            if not persons: 
                log.info("Motion but no person; continue")
                continue

            # capture small burst
            burst = [frame]
            for _ in range(cfg["export"]["burst_frames"] - 1):
                ok2, f2 = cam.read()
                if not ok2: break
                burst.append(f2)

            run_dir = new_run_dir(cfg["export"]["out_dir"])
            best = burst[len(burst)//2]
            (repo / "LAST_RUN.txt").write_text(str(run_dir))

            # detect faces (up to 2)
            boxes = detect_faces_bgr(best, models_dir=str(repo / "models"), conf=0.5)
            if not boxes:
                log.info("No faces found"); continue
            boxes = sorted(boxes, key=lambda b: b[-1], reverse=True)[:cfg["export"]["max_faces"]]

            # make cutouts + landmarks
            faces_rgba, lms = [], []
            for (x,y,w,h,conf) in boxes:
                face_bgr = best[y:y+h, x:x+w].copy()
                lm, _ = landmarks_and_aligned(face_bgr, size=cfg["faces"]["size"])
                rgba = alpha_cutout(face_bgr)
                faces_rgba.append(rgba); lms.append(lm if lm is not None else None)

            out_bundle = export_bundle(faces_rgba, lms, str(path_in(run_dir, "jibjab")))
            log.info(f"Bundle → {out_bundle}")

            # compose video
            templ = args.template or cfg["export"]["template"]
            out_mp4 = str(path_in(run_dir, "jibjab/jibjab.mp4"))
            compose_video(templ, [out_bundle], out_mp4)
            log.info(f"JibJab video → {out_mp4}")
            break  # one run per trigger by default
    finally:
        cam.release()

if __name__ == "__main__":
    main()
