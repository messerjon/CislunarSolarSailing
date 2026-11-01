import json, os, sys, time
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RES_DIR = os.path.join(ROOT, "results")
sys.path.insert(0, os.path.join(ROOT, "simulator"))


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if not np.isfinite(v) else round(v, 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, float):
        return None if not np.isfinite(o) else round(o, 6)
    return o


def save_results(name, data):
    os.makedirs(RES_DIR, exist_ok=True)
    path = os.path.join(RES_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(_clean(data), f, indent=1)
    return path


class Timer:
    def __init__(self, label):
        self.label = label
    def __enter__(self):
        self.t = time.time(); return self
    def __exit__(self, *a):
        print(f"[{self.label}] {time.time()-self.t:.1f} s", flush=True)
