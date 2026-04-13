import json
from pathlib import Path

def _deep_merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and k in a and isinstance(a[k], dict):
            a[k] = _deep_merge(a[k], v)
        else:
            a[k] = v
    return a

def load_configs(*names):
    repo = Path(__file__).resolve().parents[2]
    # always load shared first
    cfg = json.loads((repo / "settings" / "default.shared.json").read_text())
    for n in names:
        p = repo / "settings" / n
        if p.exists():
            c = json.loads(p.read_text())
            cfg = _deep_merge(cfg, c)
    local = repo / "settings" / "local.json"
    if local.exists():
        cfg = _deep_merge(cfg, json.loads(local.read_text()))
    return cfg, repo
