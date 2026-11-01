"""Q2: What is the optimal launch inclination for reaching cislunar space?

Sweeps inclination and RAAN (relative to the Sun's right ascension at launch,
i.e. launch local time) from LEO 1000 km and GTO. Two metrics:
  * transit time to lunar distance;
  * plane mismatch between the arrival orbit and the Moon's orbit plane
    (drives the cost of lunar capture / DRO-halo insertion).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import torch

from .. import averaged as av
from .. import backend, ephemeris, presets
from .. import constants as C
from .. import plotting as P
from ..spacecraft import Batch
from .common import (EPOCH, START_ORBITS, apogee_done, coast_to_apogee_days, quick, save_table, start_elements,
                     sso_inclination, sun_ra)


def moon_plane_normal(t_sec):
    t = torch.stack((t_sec, t_sec + 3600.0), -1)
    r = ephemeris.moon_position(t, EPOCH)
    h = torch.linalg.cross(r[..., 0, :], r[..., 1, :])
    return h / h.norm(dim=-1, keepdim=True)


def orbit_normal(state):
    p, f, g, h, k = state[:, :5].unbind(-1)
    n = torch.stack((2 * k, -2 * h, 1 - h * h - k * k), -1)
    return n / n.norm(dim=-1, keepdim=True)


def run():
    incs = [0, 28.5, 51.6, 90] if quick() else [0, 10, 18.3, 28.5, 40, 51.6, 63.4, 75, 90, 98]
    raan_offsets = np.arange(0, 360, 90 if quick() else 45)
    sra = sun_ra()
    archs = [presets.conventional(0.2e-3), presets.hybrid(0.2e-3, gimbal_deg=30.0)]
    rows, crafts, states, rpmin = [], [], [], []
    for start in ["LEO 1000 km", "GTO"]:
        for inc in incs:
            for dr in raan_offsets:
                for sc in archs:
                    raan = sra + math.radians(dr)
                    rows.append(dict(start=start, inc_deg=inc, raan_minus_sun_deg=dr, arch=sc.name))
                    crafts.append(sc)
                    states.append([*start_elements(start, raan=raan, argp=0.0, inc_deg=inc), sc.mass])
                    rpmin.append(C.R_EARTH + (550e3 if start.startswith("LEO") else 250e3))
    T = backend.tensor
    model = av.AveragedModel(Batch(crafts), av.EarthEnv(epoch_jd2000=EPOCH), av.objective_energy(T(rpmin)))
    print(f"Q2: {len(rows)} launch geometries")
    res = av.propagate(model, T(states), apogee_done(), 8 * C.YEAR, progress=True)
    df = pd.DataFrame(rows)
    df["arrived"] = res.done.cpu().numpy()
    df["transit_days"] = np.where(df.arrived, (res.t.cpu() / C.DAY + coast_to_apogee_days(res.state)).numpy(), np.nan)
    ang = torch.rad2deg(torch.acos((orbit_normal(res.state) * moon_plane_normal(res.t)).sum(-1).clamp(-1, 1)))
    df["plane_offset_to_moon_deg"] = ang.cpu().numpy()
    df["mean_eclipse_frac"] = torch.nanmean(res.history["eclipse_frac"], 0).numpy()
    save_table(df, "q2_launch_inclination_all")
    summ = (df.groupby(["start", "arch", "inc_deg"])
              .agg(median_days=("transit_days", "median"), best_days=("transit_days", "min"),
                   worst_days=("transit_days", "max"), median_plane_offset=("plane_offset_to_moon_deg", "median"),
                   best_plane_offset=("plane_offset_to_moon_deg", "min"),
                   eclipse=("mean_eclipse_frac", "mean"))
              .reset_index())
    save_table(summ, "q2_launch_inclination")
    plots(df, summ)
    return summ


def plots(df, summ):
    moon_inc = ephemeris.moon_inclination_to_equator(EPOCH)
    f, axes = P.fig(1, 2)
    for ax, start in zip(axes, ["LEO 1000 km", "GTO"]):
        for k, arch in enumerate(["Conventional sail", "Hybrid (gimballed SEP)"]):
            d = summ[(summ.start == start) & (summ.arch == arch)].sort_values("inc_deg")
            c = P.ARCH_COLOR[arch]
            ax.plot(d.inc_deg, d.median_days, marker="o", color=c, label=arch)
            ax.fill_between(d.inc_deg, d.best_days, d.worst_days, color=c, alpha=0.15, linewidth=0)
        ax.axvline(moon_inc, color=P.MUTED, linestyle="--", linewidth=1.3)
        ax.text(moon_inc + 1, ax.get_ylim()[1] * 0.98, f"lunar plane\n{moon_inc:.1f}°", color=P.INK2, fontsize=13, va="top")
        ax.set_title(f"From {start}")
        ax.set_xlabel("Launch inclination (deg)")
    axes[0].set_ylabel("Days to lunar distance\n(line: median over launch time; band: best–worst)")
    axes[1].legend(loc="upper right")
    P.save(f, "q2_transit_vs_inclination", "q2")

    for start in ["LEO 1000 km", "GTO"]:
        f, axes = P.fig(1, 2)
        for ax, metric, lab, cmap in ((axes[0], "transit_days", "Days to lunar distance", P.CMAP_SEQ),
                                      (axes[1], "plane_offset_to_moon_deg", "Arrival plane offset from lunar orbit (deg)", P.CMAP_SEQ)):
            d = df[(df.start == start) & (df.arch == "Conventional sail")]
            piv = d.pivot(index="inc_deg", columns="raan_minus_sun_deg", values=metric)
            im = ax.imshow(piv.values, cmap=cmap, aspect="auto", origin="lower")
            ax.set_xticks(range(piv.shape[1]), [f"{int(c)}" for c in piv.columns])
            ax.set_yticks(range(piv.shape[0]), [f"{r:g}" for r in piv.index])
            ax.set_xlabel("RAAN − Sun RA at launch (deg)")
            ax.set_ylabel("Inclination (deg)")
            ax.grid(False)
            f.colorbar(im, ax=ax, label=lab, shrink=0.85)
        axes[0].set_title(f"Conventional sail from {start}")
        P.save(f, f"q2_heatmap_{start.split()[0].lower()}", "q2")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
