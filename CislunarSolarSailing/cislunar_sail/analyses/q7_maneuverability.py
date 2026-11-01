"""Q7: Maneuverability and acceleration of the hybrid approach.

(a) Direction-resolved agility from the acceleration envelopes (Q5): mean and
    worst-direction acceleration, delta-v per day.
(b) Representative below-GEO / GEO-class maneuvers flown with the averaged
    model and Lyapunov element targeting:
      * GEO inclination change 0 -> 5 deg
      * GEO-belt relocation: raise by 1000 km and circularise
      * Demo-orbit plane change at 1000 km LEO: 5 deg inclination change
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd

from .. import averaged as av
from .. import backend, presets
from .. import constants as C
from .. import envelope as E
from .. import plotting as P
from ..spacecraft import Batch, fibonacci_sphere
from .common import EPOCH, quick, save_table, sun_ra


def archs(ac=0.2e-3):
    return [presets.conventional(ac), presets.hybrid(ac, gimbal_deg=0.0), presets.hybrid(ac, gimbal_deg=30.0),
            dataclasses.replace(presets.hybrid(ac, gimbal_deg=30.0, retractable=True), name="Retractable hybrid")]


MANEUVERS = {
    "GEO inclination 0→5°": dict(a0=42164e3, i0=0.05, a1=42164e3, i1=5.0, alt_guard=35000e3),
    "GEO relocation +1000 km": dict(a0=42164e3, i0=0.05, a1=43164e3, i1=0.05, alt_guard=35000e3),
    "LEO 1000 km plane change 5°": dict(a0=C.R_EARTH + 1000e3, i0=28.5, a1=C.R_EARTH + 1000e3, i1=33.5, alt_guard=900e3),
}


def run():
    rows = []
    sph = fibonacci_sphere(3000)
    for sc in archs():
        sup = E.support(sc, sph).cpu().numpy()
        th, rho = E.envelope(sc)
        w = np.sin(np.radians(th))
        rows.append(dict(arch=sc.name, metric="mean envelope accel (mm/s²)", value=float((w * rho).sum() / w.sum() * 1e3)))
        rows.append(dict(arch=sc.name, metric="worst-direction accel (mm/s²)", value=float(rho.min() * 1e3)))
        rows.append(dict(arch=sc.name, metric="mean Δv/day, best attitude (m/s)", value=float(np.clip(sup, 0, None).mean() * C.DAY)))
    agility = pd.DataFrame(rows)
    save_table(agility, "q7_agility")

    # maneuvers
    T = backend.tensor
    sra = sun_ra()
    mrows, crafts, states, a_t, i_t, guard = [], [], [], [], [], []
    for mname, m in MANEUVERS.items():
        for sc in archs():
            for raan_off in ([0, 90] if quick() else [0, 90, 180, 270]):
                mrows.append(dict(maneuver=mname, arch=sc.name, raan_off=raan_off))
                crafts.append(sc)
                states.append([*av.mee_from_classical(m["a0"], 1e-4, math.radians(m["i0"]), sra + math.radians(raan_off), 0.0), sc.mass])
                a_t.append(m["a1"]); i_t.append(math.radians(m["i1"])); guard.append(C.R_EARTH + m["alt_guard"])
    a_t, i_t, guard = T(a_t), T(i_t), T(guard)
    # tolerance-normalised Lyapunov weights; e tolerance is demonstration-grade because sail SRP
    # pumps GEO eccentricity to a few 1e-2 (holding a GEO station-keeping box is a separate problem)
    tol_a, tol_e, tol_i = 50e3, 0.02, math.radians(0.2)
    obj = av.objective_target(a_t, 0.0, i_t, w_a=(a_t / tol_a) ** 2, w_e=1 / tol_e**2, w_i=1 / tol_i**2, rp_min=guard)

    def done(s, t):
        a, e, inc = av.classical(*s[:, :5].unbind(-1))
        # a and i are the demonstration targets; residual eccentricity is reported, not required
        return ((a - a_t).abs() < tol_a) & ((inc - i_t).abs() < tol_i)
    model = av.AveragedModel(Batch(crafts), av.EarthEnv(epoch_jd2000=EPOCH), obj)
    print(f"Q7: {len(mrows)} maneuvers")
    res = av.propagate(model, T(states), done, 3 * C.YEAR, dt_max=0.5 * C.DAY, progress=True)
    df = pd.DataFrame(mrows)
    df["done"] = res.done.cpu().numpy()
    df["days"] = np.where(df.done, res.t.cpu().numpy() / C.DAY, np.nan)
    df["prop_kg"] = (Batch(crafts).mass0 - res.state[:, 5]).cpu().numpy()
    df["e_final"] = av.classical(*res.state[:, :5].unbind(-1))[1].cpu().numpy()
    save_table(df, "q7_maneuvers_all")
    summ = df.groupby(["maneuver", "arch"]).agg(median_days=("days", "median"), min_days=("days", "min"),
                                                max_days=("days", "max"), success=("done", "mean"),
                                                prop_kg=("prop_kg", "median"), e_final=("e_final", "median")).reset_index()
    save_table(summ, "q7_maneuvers")
    plots(agility, summ)
    return summ


def plots(agility, summ):
    names = [a.name for a in archs()]
    f, ax = P.fig()
    w = 0.8 / len(names)
    mans = list(MANEUVERS)
    for j, n in enumerate(names):
        d = summ[summ.arch == n].set_index("maneuver").reindex(mans)
        x = np.arange(len(mans)) + (j - (len(names) - 1) / 2) * w
        ax.bar(x, d.median_days.values, w * 0.92, color=P.ARCH_COLOR.get(n, P.SERIES[4]), label=n)
        for xi, (v, pk) in zip(x, zip(d.median_days.values, d.prop_kg.values)):
            if np.isfinite(v):
                ax.text(xi, v, f"{v:.0f} d" + (f"\n{pk:.1f} kg" if pk > 0.05 else ""), ha="center", va="bottom", fontsize=12, color=P.INK2)
    ax.set_xticks(range(len(mans)), mans)
    ax.set_ylabel("Days to complete (median over Sun geometry)")
    ax.set_title("Maneuver time: sail vs hybrid")
    P.subtitle(ax, "a_c = 0.2 mm/s²; SEP 10 mN / 1500 s; labels show Xe used. Done = |Δa| < 50 km, |Δi| < 0.2°; residual e in table")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    P.save(f, "q7_maneuver_times", "q7")

    f, ax = P.fig()
    piv = agility.pivot(index="arch", columns="metric", values="value").reindex(names)
    mets = list(piv.columns)
    for j, n in enumerate(names):
        x = np.arange(len(mets)) + (j - (len(names) - 1) / 2) * w
        ax.bar(x, piv.loc[n].values, w * 0.92, color=P.ARCH_COLOR.get(n, P.SERIES[4]), label=n)
    ax.set_xticks(range(len(mets)), mets)
    ax.set_title("Direction-resolved agility")
    ax.legend()
    ax.grid(axis="x", visible=False)
    P.save(f, "q7_agility", "q7")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
