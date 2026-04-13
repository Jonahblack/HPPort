from pathlib import Path
from datetime import datetime

def new_run_dir(base: str = "runs") -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = Path(base) / ts
    p.mkdir(parents=True, exist_ok=True)
    return p

def path_in(run_dir: Path, name: str) -> Path:
    p = run_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
