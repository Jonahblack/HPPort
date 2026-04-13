import json, cv2
from pathlib import Path

def export_bundle(faces_rgba, landmarks_list, out_dir: str) -> str:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    manifest = {"faces": []}
    for i, (rgba, lmk) in enumerate(zip(faces_rgba, landmarks_list)):
        png_path = out / f"face_{i:02d}.png"
        cv2.imwrite(str(png_path), rgba)  # BGRA
        entry = {"file": png_path.name, "landmarks": (lmk.tolist() if lmk is not None else None)}
        manifest["faces"].append(entry)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return str(out)
