import numpy as np, cv2, os, json
from pathlib import Path
from src.products.jibjab_export import export_bundle
from src.products.jibjab_compose import compose_video

def test_compose(tmp_path: Path):
    # Create a fake bundle with one face RGBA
    rgba = np.zeros((128,128,4), dtype=np.uint8)
    rgba[...,0:3] = 255; rgba[...,3] = 255
    lmk = np.array([[30,40],[90,40],[60,80],[60,110]])
    bundle = tmp_path / "bundle"
    export_bundle([rgba], [lmk], str(bundle))
    # Minimal template
    templ = tmp_path / "t.json"
    templ.write_text(json.dumps({
        "name": "test",
        "background_video": None,
        "fps": 10,
        "resolution": [320,240],
        "duration_sec": 1,
        "slots": [{"name":"s0","anchor":"mouth_center","size":[64,64],"offset":[0,0],"rotation_from":"eyes"}]
    }))
    out = tmp_path / "out.mp4"
    compose_video(str(templ), [str(bundle)], str(out))
    assert out.exists()
