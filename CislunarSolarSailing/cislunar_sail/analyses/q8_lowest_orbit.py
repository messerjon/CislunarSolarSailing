"""Q8: What is the lowest orbit that still meets the Cattle Run demonstration objective?

Demonstration objective (DARPA-SN-27-03): below GEO, show renewable propulsion
achieves sufficient acceleration, accurate control and autonomous GNC. The
binding physical requirement is that the sail can *raise* its orbit against
drag. We fly 30 days from circular orbits across altitude x characteristic
acceleration x solar activity x orbit plane, with drag-aware locally-optimal
steering (the controller feathers or stows the sail when drag dominates).

Note: sail drag and sail SRP both scale with A/m, so for the film alone the
drag/SRP ratio is independent of sail size; only the density matters.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd

from .. import averaged as av
from .. import backend, presets
from .. import constants as C
from .. import plotting as P
from ..spacecraft import Batch
from .common import EPOCH, quick, save_table, sso_inclination, sun_ra

DEMO_RAISE_KM = 10.0  # "clearly demonstrated" net raise per 30 days


def run():
    alts = np.arange(400, 1301, 100 if quick() else 50) * 1e3
    acs = [0.1e-3, 0.2e-3, 0.5e-3] if quick() else [0.05e-3, 0.1e-3, 0.2e-3, 0.3e-3, 0.5e-3]
    atms = ["min", "moderate", "max"]
    planes = {"28.5° (Cape)": None, "51.6° (ISS-like)": None, "SSO dawn-dusk": None}
    sra = sun_ra()
    rows, crafts, states, envs = [], [], [], []
    for atm in atms:
        for ac in acs:
            variants = [presets.conventional(ac),
                        dataclasses.replace(presets.conventional(ac, double_sided=True), name="Double-sided sail"),
                        dataclasses.replace(presets.conventional(ac, retractable=True), name="Retractable sail"),
                        presets.hybrid(ac, gimbal_deg=30.0)]
            for sc in variants:
                for plane in planes:
                    for h in alts:
                        if plane.startswith("28.5"):
                            inc, raan = math.radians(28.5), sra
                        elif plane.startswith("51.6"):
                            inc, raan = math.radians(51.6), sra
                        else:
                            inc, raan = sso_inclination(h), sra + math.pi / 2  # LTAN 18:00
                        oe = av.mee_from_classical(C.R_EARTH + h, 1e-4, inc, raan, 0.0)
                        rows.append(dict(atmosphere=atm, ac_mm_s2=ac * 1e3, arch=sc.name, plane=plane, alt_km=h / 1e3))
                        crafts.append(sc)
                        states.append([*oe, sc.mass])
                        envs.append(atm)
    T = backend.tensor
    df_parts = []
    for atm in atms:  # one batch per atmosphere level (env is shared within a batch)
        idx = [i for i, e in enumerate(envs) if e == atm]
        rp_guard = T([C.R_EARTH + rows[i]["alt_km"] * 1e3 - 50e3 for i in idx])  # stops eccentricity dives into the atmosphere
        model = av.AveragedModel(Batch([crafts[i] for i in idx]), av.EarthEnv(epoch_jd2000=EPOCH, atmosphere=atm),
                                 av.objective_energy(rp_guard))
        print(f"Q8: {len(idx)} cases, atmosphere={atm}")
        res = av.propagate(model, T([states[i] for i in idx]), lambda s, t: s[:, 0] < 0, 30 * C.DAY,
                           dt_max=0.25 * C.DAY, progress=True)
        a, e, _ = av.classical(*res.state[:, :5].unbind(-1))
        part = pd.DataFrame([rows[i] for i in idx])
        a0 = C.R_EARTH + part.alt_km.values * 1e3
        part["delta_a_km_30d"] = np.where(res.failed.cpu().numpy(), -part.alt_km.values, (a.cpu().numpy() - a0) / 1e3)
        part["reentered"] = res.failed.cpu().numpy()
        part["eclipse_frac"] = res.history["eclipse_frac"][0].numpy()
        part["stowed_frac"] = res.history["stowed_frac"][:, :].mean(0).numpy()
        df_parts.append(part)
    df = pd.concat(df_parts, ignore_index=True)
    save_table(df, "q8_lowest_orbit_all")
    # crossover altitudes
    out = []
    for key, g in df.groupby(["atmosphere", "ac_mm_s2", "arch", "plane"]):
        g = g.sort_values("alt_km")
        pos = g[g.delta_a_km_30d > 0]
        demo = g[g.delta_a_km_30d >= DEMO_RAISE_KM]
        out.append(dict(zip(["atmosphere", "ac_mm_s2", "arch", "plane"], key),
                        lowest_net_raise_km=pos.alt_km.min() if len(pos) else np.nan,
                        lowest_demo_km=demo.alt_km.min() if len(demo) else np.nan))
    summ = pd.DataFrame(out)
    save_table(summ, "q8_lowest_orbit")
    plots(df, summ)
    return summ


def plots(df, summ):
    # (1) delta-a vs altitude at 0.2 mm/s^2, conventional, three atmospheres, Cape plane
    for arch in ["Conventional sail", "Retractable sail"]:
        f, ax = P.fig()
        sel = df[(df.arch == arch) & np.isclose(df.ac_mm_s2, 0.2) & (df.plane == "28.5° (Cape)")]
        for k, atm in enumerate(["min", "moderate", "max"]):
            d = sel[sel.atmosphere == atm].sort_values("alt_km")
            ax.plot(d.alt_km, d.delta_a_km_30d, marker="o", color=P.SERIES[[0, 3, 7][k]], label=f"Solar {atm}")
        ax.axhline(0, color=P.INK2, linewidth=1.2)
        ax.axhline(DEMO_RAISE_KM, color=P.MUTED, linestyle="--", linewidth=1.3)
        ax.text(sel.alt_km.max(), DEMO_RAISE_KM - 4, f"demonstration threshold: +{DEMO_RAISE_KM:.0f} km / 30 d", color=P.INK2,
                fontsize=14, ha="right", va="top")
        ax.set_ylim(-60, max(80, sel.delta_a_km_30d.max() * 1.1))
        ax.set_xlabel("Initial circular altitude (km)")
        ax.set_ylabel("Net change in semi-major axis\nover 30 days (km)")
        ax.set_title(f"Can a {arch.lower()} out-climb drag?")
        P.subtitle(ax, "a_c = 0.2 mm/s², 28.5° inclination, drag-aware locally-optimal steering; below −60 km clipped (re-entry)")
        ax.legend(loc="center right")
        P.save(f, f"q8_delta_a_vs_alt_{arch.split()[0].lower()}", "q8")

    # (2) lowest demo altitude vs a_c, one panel per solar-activity level (Cape plane; planes differ < 50 km)
    f, axes = P.fig(1, 3, sharey=True)
    archs = [("Conventional sail", P.ARCH_COLOR["Conventional sail"]), ("Double-sided sail", P.ARCH_COLOR["Double-sided sail"]),
             ("Retractable sail", P.SERIES[4]), ("Hybrid (gimballed SEP)", P.ARCH_COLOR["Hybrid (gimballed SEP)"])]
    for ax, atm in zip(axes, ["min", "moderate", "max"]):
        for arch, col in archs:
            d = summ[(summ.arch == arch) & (summ.plane == "28.5° (Cape)") & (summ.atmosphere == atm)].sort_values("ac_mm_s2")
            ax.plot(d.ac_mm_s2, d.lowest_demo_km, marker="o", color=col, label=arch)
        ax.set_xscale("log"); P.plain_log(ax, "x")
        ax.set_title(f"Solar {atm}")
        ax.set_xlabel("a_c (mm/s²)")
    axes[0].set_ylabel("Lowest altitude for +10 km / 30 d (km)")
    axes[0].legend(loc="upper left", fontsize=13)
    f.suptitle("Lowest demonstration orbit by architecture and solar activity (28.5°; 51.6° and dawn-dusk SSO within 50 km)",
               x=0.02, ha="left", fontsize=19, fontweight="bold")
    P.save(f, "q8_crossover_altitude", "q8")

    # (3) heatmap: lowest demo altitude, conventional, (ac x atmosphere), Cape
    f, axes = P.fig(1, 2)
    for ax, arch in zip(axes, ["Conventional sail", "Retractable sail"]):
        d = summ[(summ.arch == arch) & (summ.plane == "28.5° (Cape)")]
        piv = d.pivot(index="atmosphere", columns="ac_mm_s2", values="lowest_demo_km").reindex(["min", "moderate", "max"])
        im = ax.imshow(piv.values, cmap=P.CMAP_SEQ_R, aspect="auto", vmin=400, vmax=1300)
        for (i, j), v in np.ndenumerate(piv.values):
            ax.text(j, i, "—" if not np.isfinite(v) else f"{v:.0f}", ha="center", va="center", fontsize=16,
                    color="white" if np.isfinite(v) and v < 850 else P.INK)
        ax.set_xticks(range(piv.shape[1]), [f"{c:g}" for c in piv.columns])
        ax.set_yticks(range(3), ["Solar min", "Moderate", "Solar max"])
        ax.set_xlabel("a_c (mm/s²)")
        ax.set_title(arch)
        ax.grid(False)
    f.colorbar(im, ax=axes, label="Lowest altitude for +10 km / 30 d (km)", shrink=0.8)
    P.save(f, "q8_demo_altitude_heatmap", "q8")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
