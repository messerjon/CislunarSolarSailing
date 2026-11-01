"""Q1: How quickly can each architecture get from LEO / MEO / GTO / GEO / TLI to cislunar space?

"Arrival" = apogee reaches 300,000 km (lunar-distance energy, where three-body
capture into DRO/halo orbits takes over), plus the coast to that apogee.
Each case is run at four RAAN values (Sun geometry) and the median reported.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import torch

from .. import averaged as av
from .. import backend, presets
from .. import constants as C
from .. import plotting as P
from ..spacecraft import Batch
from .common import (EPOCH, LUNAR_DISTANCE_TARGET, START_ORBITS, apogee_done, coast_to_apogee_days, quick,
                     save_table, start_elements, tli_coast_days)


def run():
    acs = [0.1e-3, 0.2e-3, 0.5e-3] if quick() else [0.05e-3, 0.1e-3, 0.2e-3, 0.3e-3, 0.5e-3, 1.0e-3]
    raans = [0.0, math.pi] if quick() else [0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi]
    rows, crafts, states, rpmin = [], [], [], []
    for orbit in START_ORBITS:
        for ac in acs:
            for arch in presets.architectures(ac):
                for raan in raans:
                    oe = start_elements(orbit, raan=raan, argp=0.3)
                    hp = START_ORBITS[orbit][0]
                    rows.append(dict(start=orbit, ac_mm_s2=ac * 1e3, arch=arch.name, raan_deg=math.degrees(raan),
                                     mass_kg=arch.mass, sail_area_m2=arch.sail.area))
                    crafts.append(arch)
                    states.append([*oe, arch.mass])
                    rpmin.append(C.R_EARTH + max(min(hp, 600e3) - 50e3, 250e3))  # guard 50 km below start: no e≈0 singularity
    T = backend.tensor
    model = av.AveragedModel(Batch(crafts), av.EarthEnv(epoch_jd2000=EPOCH), av.objective_energy(T(rpmin)))
    t_max = 10 * C.YEAR
    print(f"Q1: propagating {len(rows)} spiral trajectories (orbit-averaged, batched)")
    res = av.propagate(model, T(states), apogee_done(), t_max, progress=True)
    coast = coast_to_apogee_days(res.state)
    df = pd.DataFrame(rows)
    df["arrived"] = res.done.cpu().numpy()
    df["failed"] = res.failed.cpu().numpy()
    df["transit_days"] = np.where(df.arrived, res.t.cpu().numpy() / C.DAY + coast.numpy(), np.nan)
    df["propellant_used_kg"] = (Batch(crafts).mass0 - res.state[:, 5]).cpu().numpy()
    # TLI: ballistic, no propulsion needed to reach lunar distance
    for ac in acs:
        for arch in presets.architectures(ac):
            df.loc[len(df)] = dict(start="TLI", ac_mm_s2=ac * 1e3, arch=arch.name, raan_deg=0.0, mass_kg=arch.mass,
                                   sail_area_m2=arch.sail.area, arrived=True, failed=False,
                                   transit_days=tli_coast_days(), propellant_used_kg=0.0)
    save_table(df, "q1_earth_to_cislunar_all")
    summ = (df.groupby(["start", "ac_mm_s2", "arch"])
              .agg(median_days=("transit_days", "median"), min_days=("transit_days", "min"),
                   max_days=("transit_days", "max"), success=("arrived", "mean"),
                   propellant_kg=("propellant_used_kg", "median"))
              .reset_index())
    save_table(summ, "q1_earth_to_cislunar")
    plots(summ, res, rows)
    return summ


ORDER = ["LEO 600 km", "LEO 1000 km", "MEO 8000 km", "GTO", "GEO", "TLI"]


def plots(summ, res, rows):
    archs = [a for a in P.ARCH_COLOR if a in set(summ.arch)]
    # (1) grouped bars at 0.2 mm/s^2
    ref = summ[np.isclose(summ.ac_mm_s2, 0.2)]
    f, ax = P.fig()
    w = 0.8 / len(archs)
    for j, a in enumerate(archs):
        d = ref[ref.arch == a].set_index("start").reindex(ORDER)
        y = d.median_days.values / 30.44
        x = np.arange(len(ORDER)) + (j - (len(archs) - 1) / 2) * w
        ax.bar(x, np.nan_to_num(y), w * 0.92, color=P.ARCH_COLOR[a], label=a)
        for xi, yi in zip(x, y):
            if not np.isfinite(yi):
                ax.text(xi, 0.5, "x", ha="center", va="bottom", color=P.INK2, fontsize=13)
    ax.set_xticks(range(len(ORDER)), ORDER)
    ax.set_ylabel("Months to lunar distance")
    ax.set_title("Transit time to cislunar space by launch orbit")
    P.subtitle(ax, "Characteristic acceleration 0.2 mm/s² (sail), 60 kg bus; hybrids carry 10 mN / 1500 s SEP with 8 kg Xe.  x = never arrives (10 yr)")
    ax.legend(ncol=3, loc="upper right")
    ax.grid(axis="x", visible=False)
    P.save(f, "q1_transit_by_orbit", "q1")

    # (2) transit vs characteristic acceleration (log-log) per start orbit, conventional & gimballed hybrid
    f, axes = P.fig(1, 2, sharey=True)
    for ax, a in zip(axes, ["Conventional sail", "Hybrid (gimballed SEP)"]):
        for k, o in enumerate(ORDER[:-1]):
            d = summ[(summ.arch == a) & (summ.start == o)].sort_values("ac_mm_s2")
            ax.plot(d.ac_mm_s2, d.median_days, marker="o", color=P.SERIES[k], label=o)
            ax.fill_between(d.ac_mm_s2, d.min_days, d.max_days, color=P.SERIES[k], alpha=0.12, linewidth=0)
        ax.axhline(tli_coast_days(), color=P.MUTED, linestyle="--", linewidth=1.5)
        ax.text(summ.ac_mm_s2.min(), tli_coast_days() * 1.15, "TLI ballistic coast", color=P.INK2, fontsize=14)
        ax.set_xscale("log"); ax.set_yscale("log")
        P.plain_log(ax)
        ax.set_xlabel("Characteristic acceleration (mm/s²)")
        ax.set_title(a)
    axes[0].set_ylabel("Days to lunar distance")
    axes[1].legend(loc="upper right")
    P.save(f, "q1_transit_vs_ac", "q1")

    # (3) spiral visualisation: GTO, conventional, 0.2 mm/s^2
    idx = [i for i, r in enumerate(rows) if r["start"] == "GTO" and r["arch"] == "Conventional sail"
           and abs(r["ac_mm_s2"] - 0.2) < 1e-9]
    if idx:
        spiral_plot(res, idx[0], "q1_spiral_gto_conventional", "GTO → lunar distance, conventional sail 0.2 mm/s²")
    idx = [i for i, r in enumerate(rows) if r["start"] == "GTO" and r["arch"] == "Hybrid (gimballed SEP)"
           and abs(r["ac_mm_s2"] - 0.2) < 1e-9]
    if idx:
        spiral_plot(res, idx[0], "q1_spiral_gto_hybrid", "GTO → lunar distance, gimballed hybrid 0.2 mm/s²")


def osculating_ellipses(states, n_orbits=60, npts=180):
    st = torch.as_tensor(states)
    sel = np.unique(np.linspace(0, len(st) - 1, n_orbits).astype(int))
    L = torch.linspace(0, 2 * math.pi, npts, dtype=st.dtype)
    out = []
    for i in sel:
        p, f, g, h, k = (st[i, j].expand(npts) for j in range(5))
        r, _ = av.mee_to_rv(p, f, g, h, k, L, C.MU_EARTH)
        out.append(r.numpy() / 1e6)
    return out, sel


def spiral_plot(res, b, name, title):
    hist = res.history
    n_valid = int((hist["t"][:, b].diff(prepend=torch.tensor([-1.0])) > 0).sum())
    states = hist["state"][:n_valid, b]
    t_days = hist["t"][:n_valid, b].numpy() / C.DAY
    ells, sel = osculating_ellipses(states)
    f, ax = P.fig3d()
    cmap = P.CMAP_SEQ
    for e, i in zip(ells, sel):
        c = cmap(0.25 + 0.75 * i / max(sel[-1], 1))
        ax.plot(e[:, 0], e[:, 1], e[:, 2], color=c, linewidth=0.9)
    P.sphere(ax, (0, 0, 0), C.R_EARTH / 1e6 * 3, P.EARTH_C)
    ax.set_xlabel("x (1000 km)", labelpad=14); ax.set_ylabel("y (1000 km)", labelpad=14); ax.set_zlabel("z (1000 km)", labelpad=14)
    ax.set_title(title)
    pts = np.concatenate(ells)
    P.set_equal_3d(ax, pts)
    sm = __import__("matplotlib").cm.ScalarMappable(cmap=cmap, norm=__import__("matplotlib").colors.Normalize(0, t_days[-1]))
    f.colorbar(sm, ax=ax, shrink=0.6, label="Mission elapsed time (days)")
    P.save(f, name + "_3d", "q1")
    # 2D (equatorial-plane projection) for slides
    f, ax = P.fig()
    for e, i in zip(ells, sel):
        ax.plot(e[:, 0], e[:, 1], color=cmap(0.25 + 0.75 * i / max(sel[-1], 1)), linewidth=1.0)
    ax.add_patch(__import__("matplotlib").patches.Circle((0, 0), C.R_EARTH / 1e6, color=P.EARTH_C))
    moon = __import__("matplotlib").patches.Circle((0, 0), C.D_EARTH_MOON / 1e6, fill=False, linestyle="--", color=P.MUTED)
    ax.add_patch(moon)
    ax.set_aspect("equal")
    ax.set_xlabel("x (1000 km, equatorial)"); ax.set_ylabel("y (1000 km)")
    ax.set_title(title)
    P.subtitle(ax, f"Osculating orbits sampled over {t_days[-1]:.0f} days; dashed ring = lunar orbit")
    f.colorbar(sm, ax=ax, label="Mission elapsed time (days)")
    P.save(f, name + "_2d", "q1")
    P.plotly_html([dict(x=e[:, 0], y=e[:, 1], z=e[:, 2], name=f"day {t_days[i]:.0f}",
                        color=f"rgba(42,120,214,{0.25 + 0.75 * i / max(sel[-1], 1):.2f})", width=2)
                   for e, i in zip(ells, sel)], name + "_interactive", title, "q1")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
