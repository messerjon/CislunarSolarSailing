"""Pre-process every mission profile and produce all figures + tables.

    python -m cislunar_sail.run_all                 # full run (CPU ~1 h; CUDA much faster)
    python -m cislunar_sail.run_all --quick         # coarse grids for iteration (~8 min)
    python -m cislunar_sail.run_all --only q1 q8    # subset
    python -m cislunar_sail.run_all --device cuda

Outputs: figures/<question>/*.png|svg|html and results/*.csv, plus results/summary.md.
"""
from __future__ import annotations

import argparse
import importlib
import os
import time
import traceback

ANALYSES = {
    "q1": ("q1_earth_to_cislunar", "Transit from LEO/MEO/GTO/GEO/TLI to cislunar space"),
    "q2": ("q2_launch_inclination", "Optimal launch inclination"),
    "q3": ("q3_cislunar_transfers", "Transit between DRO, LLO, EML1/2/4/5"),
    "q4": ("q4_pole_sitter", "Lunar pole-sitter requirements"),
    "q5": ("q5_in_irons", "In-irons / no-travel region, sail vs hybrid"),
    "q6": ("q6_field_of_view", "Sensor field of view, fixed vs gimballed bus"),
    "q7": ("q7_maneuverability", "Hybrid maneuverability and acceleration"),
    "q8": ("q8_lowest_orbit", "Lowest acceptable demonstration orbit"),
    "att": ("attitude_momentum", "Momentum management: electrochromic film vs gimballed CMT"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--device", default=None, help="cpu | cuda | mps (default: cuda if available)")
    ap.add_argument("--only", nargs="*", default=None, choices=list(ANALYSES))
    args = ap.parse_args()
    if args.quick:
        os.environ["SAIL_QUICK"] = "1"
    from . import backend
    dev, dt = backend.configure(args.device)
    print(f"device={dev} dtype={dt} quick={args.quick}")
    timings = {}
    for key in args.only or ANALYSES:
        mod_name, title = ANALYSES[key]
        print(f"\n=== {key}: {title} ===")
        t0 = time.time()
        try:
            mod = importlib.import_module(f".analyses.{mod_name}", __package__)
            mod.run()
            timings[key] = time.time() - t0
            print(f"--- {key} done in {timings[key]:.0f} s")
        except Exception:
            traceback.print_exc()
            timings[key] = float("nan")
    from .analyses import summary
    path = summary.write()
    print(f"\nSummary written to {path}")
    print({k: round(v) if v == v else "FAILED" for k, v in timings.items()})


if __name__ == "__main__":
    main()
