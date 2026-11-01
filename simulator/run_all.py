"""Run every Cattle Run study analysis and regenerate results/*.json and figures/*.png.

Usage:  python run_all.py            (NumPy backend)
        CISLUNAR_BACKEND=torch python run_all.py   (PyTorch; uses CUDA GPUs when present)
"""
import importlib
import sys
import time

MODULES = ["q5_in_irons", "q8_lowest_orbit", "q1_transit", "q2_inclination", "q3_cislunar_transfers",
           "q4_pole_sitter", "q6_fov", "q7_hybrid", "design_trades"]

if __name__ == "__main__":
    sel = sys.argv[1:] or MODULES
    t0 = time.time()
    import os
    from cislunar_sail import designs
    designs.export(os.path.join(os.path.dirname(__file__), "..", "results", "designs.json"))
    for name in sel:
        mod = importlib.import_module(f"analyses.{name}")
        mod.run()
    print(f"all analyses complete in {time.time() - t0:.0f} s")
