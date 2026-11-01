"""Shared helpers for the analysis scripts."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .. import averaged as av
from .. import constants as C
from .. import ephemeris

RESULTS = Path(os.environ.get("SAIL_RESULTS_DIR", "results"))
EPOCH = ephemeris.jd2000_from_date(2027, 6, 1)  # notional demo launch
LUNAR_DISTANCE_TARGET = 300000e3                 # apogee that counts as "arrived in cislunar space"


def quick() -> bool:
    return os.environ.get("SAIL_QUICK", "0") == "1"


def save_table(df: pd.DataFrame, name: str):
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / f"{name}.csv", index=False)
    return RESULTS / f"{name}.csv"


def save_json(obj, name: str):
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / f"{name}.json", "w") as fh:
        json.dump(obj, fh, indent=2, default=float)


def apogee_done(target=LUNAR_DISTANCE_TARGET):
    def done(s, t):
        a, e, _ = av.classical(*s[:, :5].unbind(-1))
        return a * (1 + e) >= target
    return done


def coast_to_apogee_days(state):
    """Time from perigee to apogee (half period) of the final orbit, days."""
    a, e, _ = av.classical(*state[:, :5].unbind(-1))
    return (math.pi * torch.sqrt(a**3 / C.MU_EARTH) / C.DAY).cpu()


def sun_ra(epoch=EPOCH) -> float:
    u = ephemeris.sun_unit(torch.zeros(1, dtype=torch.float64), epoch)[0]
    return math.atan2(float(u[1]), float(u[0]))


def sso_inclination(alt_m: float) -> float:
    a = C.R_EARTH + alt_m
    n = math.sqrt(C.MU_EARTH / a**3)
    rate = 2 * math.pi / (365.2422 * C.DAY)
    return math.acos(-rate / (1.5 * n * C.J2_EARTH * (C.R_EARTH / a) ** 2))


START_ORBITS = {
    # name: (perigee alt m, apogee alt m, inclination deg)
    "LEO 600 km": (600e3, 600e3, 28.5),
    "LEO 1000 km": (1000e3, 1000e3, 28.5),
    "MEO 8000 km": (8000e3, 8000e3, 28.5),
    "GTO": (250e3, 35786e3, 27.0),
    "GEO": (35786e3, 35786e3, 0.1),
}


def start_elements(name, raan=0.0, argp=0.0, inc_deg=None):
    hp, ha, inc = START_ORBITS[name]
    inc = inc if inc_deg is None else inc_deg
    rp, ra = C.R_EARTH + hp, C.R_EARTH + ha
    a = (rp + ra) / 2
    e = (ra - rp) / (ra + rp)
    return av.mee_from_classical(a, e, math.radians(inc), raan, argp)


def tli_coast_days(perigee_alt=200e3, apogee=384400e3):
    rp = C.R_EARTH + perigee_alt
    a = (rp + apogee) / 2
    return math.pi * math.sqrt(a**3 / C.MU_EARTH) / C.DAY
