import argparse, cv2
from pathlib import Path
from src.common.config import load_configs
from src.common.logging import setup_logging
from src.common.camera import Camera
from src.common.storage import new_run_dir, path_in
from src.common.video import make_writer
from src.detection.motion import MotionDetector
from src.detection.hailo_person import HailoPerson
from src.faces.detect_res10 import detect_faces_bgr
from src.faces.align import landmarks_and_aligned
from src.products.scream_synth import synthesize_scream

def main():
    ap = argparse.ArgumentParser(description="Screamer capture → synth")
    ap.add_argument("--hef", required=True, help="Path to Hailo .hef model (YOLO w/ person class)")
    args = ap.parse_args()
    cfg, repo = load_configs("screamer.json")
    log = setup_logging()

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

            # capture single best frame
            run_dir = new_run_dir(cfg["export"]["out_dir"])
            (repo / "LAST_RUN.txt").write_text(str(run_dir))
            best = frame.copy()

            boxes = detect_faces_bgr(best, models_dir=str(repo / "models"), conf=0.5)
            if not boxes:
                log.info("No face found"); continue
            (x,y,w,h,conf) = sorted(boxes, key=lambda b: b[-1], reverse=True)[0]
            face_bgr = best[y:y+h, x:x+w].copy()
            lm, aligned = landmarks_and_aligned(face_bgr, size=cfg["faces"]["size"])
            out_png = str(path_in(run_dir, "screamer/face_256.png"))
            cv2.imwrite(out_png, aligned)

            frames = synthesize_scream(aligned, fps=cfg["export"]["fps"], duration_sec=cfg["export"]["duration_sec"],
                                       jaw_open_pct=cfg["export"]["jaw_open_pct"], shake_px=cfg["export"]["shake_px"],
                                       flicker=cfg["export"]["flicker"])
            out_mp4 = str(path_in(run_dir, "screamer/screamer.mp4"))
            writer = make_writer(out_mp4, cfg["export"]["fps"], (aligned.shape[1], aligned.shape[0]))
            for f in frames: writer.write(f)
            writer.release()
            log.info(f"Screamer video → {out_mp4}")
            break
    finally:
        cam.release()

if __name__ == "__main__":
    main()
