"""Q3: Transit times to and between DRO, low lunar orbit (LRO-class) and EML1/2/4/5.

Orbit-to-orbit transfers among L1 halo, L2 halo, DRO, L4 and L5 are solved as
minimum-time problems with batched Levenberg-Marquardt multiple shooting and
thrust homotopy (cislunar_sail.shooting). A batch spans a time-of-flight grid x
Sun phase x multi-start; the shortest TOF that converges *and* re-validates with
4x finer integration is the transit time. Reported per Sun phase so the
dependence on launch epoch is visible ("best" = best epoch, "median" = typical).

Low lunar orbit (100 km polar, LRO-class) lies deep in the Moon's well where
multiple shooting needs very fine steps; it is computed as an orbit-averaged
Moon-centred spiral from a 15,000 km circular capture orbit, and combined with
the transfer to the DRO as an approximate end-to-end estimate.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import torch

from .. import averaged as av
from .. import backend, cr3bp, presets
from .. import constants as C
from .. import plotting as P
from .. import shooting as sh
from ..spacecraft import Batch
from .common import quick, save_table


def orbit_set():
    return [cr3bp.find_halo("L1", 10000), cr3bp.find_halo("L2", 15000), cr3bp.find_dro(70000),
            cr3bp.equilibrium_target("L4"), cr3bp.equilibrium_target("L5")]


SHORT = ["L1 halo", "L2 halo", "DRO", "L4", "L5"]


def craft_set():
    return [presets.conventional(0.2e-3), presets.hybrid(0.2e-3, gimbal_deg=30.0)]


def build_batch(pairs, n_craft, tofs, suns, starts):
    rows = list(itertools.product(pairs, range(n_craft), tofs, suns, starts))
    T = backend.tensor
    batch = sh.TransferBatch(
        src_idx=torch.tensor([r[0][0] for r in rows]), dst_idx=torch.tensor([r[0][1] for r in rows]),
        craft_idx=torch.tensor([r[1] for r in rows]), tof=T([r[2] * C.DAY / C.TU for r in rows]),
        sun0=T([r[3] for r in rows]), phiA0=T([r[4][0] for r in rows]), phiB0=T([r[4][1] for r in rows]))
    return rows, batch


def run_shooting():
    orbits = orbit_set()
    models = [sh.FourierOrbit(o) for o in orbits]
    crafts = craft_set()
    if quick():
        pairs = [(0, 1), (1, 0), (2, 1), (1, 2), (2, 3), (1, 4)]
        tofs, suns, starts = [10, 20, 40, 80, 120], [0.0, math.pi], [(0.0, 0.0), (0.5, 0.25)]
    else:
        pairs = [(a, b) for a in range(5) for b in range(5) if a != b and not (a >= 3 and b >= 3)]
        tofs = [7, 10, 14, 20, 28, 40, 56, 80, 112, 160]
        suns = [0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi]
        starts = [(0.0, 0.0), (0.5, 0.25), (0.25, 0.75)]
    rows, batch = build_batch(pairs, len(crafts), tofs, suns, starts)
    cfg = sh.ShootingConfig(S=2, steps_per_arc=8)
    print(f"Q3: {len(rows)} multiple-shooting problems ({len(pairs)} orbit pairs x {len(crafts)} craft x "
          f"{len(tofs)} TOF x {len(suns)} Sun phases x {len(starts)} starts)")
    sols = []
    chunk = 512
    for c0 in range(0, len(rows), chunk):
        idx = torch.arange(c0, min(len(rows), c0 + chunk))
        sub = sh.TransferBatch(*(getattr(batch, f)[idx] for f in batch.__dataclass_fields__))
        s = sh.solve_homotopy(models, crafts, sub, cfg)
        # re-validate with 4x finer integration
        fine = sh.ShootingConfig(S=2, steps_per_arc=32)
        chk = sh.solve_lm(models, crafts, sub, fine, iters=0, init={k: v.to(backend.device()) for k, v in s.items() if torch.is_tensor(v)})
        s["ok_fine"] = (chk["ok"].cpu() & s["ok"]).cpu()
        s["fine_dr_km"] = chk["max_dr_km"].cpu()
        sols.append(s)
        print(f"  chunk {c0 // chunk + 1}/{math.ceil(len(rows) / chunk)}: converged {int(s['ok'].sum())}, "
              f"validated {int(s['ok_fine'].sum())}")
    sol = {k: torch.cat([s[k] for s in sols]) for k in sols[0] if torch.is_tensor(sols[0][k])}
    df = pd.DataFrame([dict(src=SHORT[r[0][0]], dst=SHORT[r[0][1]], arch=crafts[r[1]].name, tof_days=r[2],
                            sun_deg=round(math.degrees(r[3])), start=str(r[4])) for r in rows])
    df["converged"] = sol["ok"].numpy()
    df["validated"] = sol["ok_fine"].numpy()
    df["max_defect_km"] = sol["max_dr_km"].numpy()
    df["prop_kg"] = sol["prop_kg"].numpy()
    save_table(df, "q3_shooting_all")
    return df, sol, rows, batch, models, crafts, orbits


def spiral_to_llo():
    """Orbit-averaged spiral from a 15,000 km circular lunar capture orbit to 100 km polar (LRO-class)."""
    crafts = craft_set()
    T = backend.tensor
    states, sun_ph = [], []
    for sc in crafts:
        for ph in ([0.0, math.pi] if quick() else np.linspace(0, 2 * math.pi, 6, endpoint=False)):
            states.append([*av.mee_from_classical(15000e3, 1e-3, math.radians(10), 0.0, 0.0), sc.mass])
            sun_ph.append((sc.name, ph))
    a_t = C.R_MOON + 100e3
    batch_crafts = [crafts[0] if n == crafts[0].name else crafts[1] for n, _ in sun_ph]
    out = []
    for (name, ph), st, sc in zip(sun_ph, states, batch_crafts):
        out.append((name, ph, st, sc))
    rows = []
    # different Sun phases need separate environments
    for name, ph, st, sc in out:
        obj = av.objective_target(T([a_t]), 0.0, T([math.radians(90)]), w_a=100.0, w_e=1 / 0.01**2,
                                  w_i=1 / math.radians(1) ** 2, rp_min=T([C.R_MOON + 60e3]), a_metric="l1")
        model = av.AveragedModel(Batch([sc]), av.MoonEnv(sun_phase0=ph), obj)

        def done(s, t):
            a, e, inc = av.classical(*s[:, :5].unbind(-1))
            return ((a - a_t).abs() < 20e3) & (e < 0.01) & ((inc - math.radians(90)).abs() < math.radians(1))
        res = av.propagate(model, T([st]), done, 5 * C.YEAR, dt_max=0.25 * C.DAY)
        rows.append(dict(arch=name, sun_deg=round(math.degrees(ph)), done=bool(res.done[0]),
                         days=float(res.t[0]) / C.DAY if bool(res.done[0]) else np.nan,
                         prop_kg=float(sc.mass - res.state[0, 5]),
                         final_alt_km=float(av.classical(*res.state[:, :5].unbind(-1))[0][0] - C.R_MOON) / 1e3))
    df = pd.DataFrame(rows)
    save_table(df, "q3_llo_spiral")
    return df


def summarise(df, llo):
    v = df[df.validated]
    per_sun = v.groupby(["src", "dst", "arch", "sun_deg"]).tof_days.min().reset_index()
    nsun = df.sun_deg.nunique()
    agg = per_sun.groupby(["src", "dst", "arch"]).agg(best_days=("tof_days", "min"),
                                                       median_days=("tof_days", "median"),
                                                       sun_phases_solved=("tof_days", "size")).reset_index()
    agg["sun_phases_tried"] = nsun
    # LLO estimates: X -> DRO + capture spiral
    for arch, g in llo.groupby("arch"):
        sp = g.days.median()
        for src in SHORT:
            d = agg[(agg.src == src) & (agg.dst == "DRO") & (agg.arch == arch)]
            base = 0.0 if src == "DRO" else (d.best_days.iloc[0] if len(d) else np.nan)
            med = 0.0 if src == "DRO" else (d.median_days.iloc[0] if len(d) else np.nan)
            agg.loc[len(agg)] = dict(src=src, dst="LLO (≈)", arch=arch, best_days=base + g.days.min(),
                                     median_days=med + sp, sun_phases_solved=np.nan, sun_phases_tried=np.nan)
    save_table(agg, "q3_cislunar_transfers")
    return agg


def plots(agg, df, sol, rows, batch, models, crafts, orbits):
    names = SHORT
    cols = names + ["LLO (≈)"]
    f, axes = P.fig(1, 2)
    for ax, sc in zip(axes, crafts):
        M = np.full((len(names), len(cols)), np.nan)
        for i, s in enumerate(names):
            for j, d in enumerate(cols):
                g = agg[(agg.src == s) & (agg.dst == d) & (agg.arch == sc.name)]
                if len(g):
                    M[i, j] = g.median_days.iloc[0]
        Mc = M.copy()
        Mc[:, -1] = np.nan  # LLO column shown as text only (different scale: ~1 yr spirals)
        im = ax.imshow(Mc, cmap=P.CMAP_SEQ, vmin=0, vmax=160)
        ax.axvline(len(cols) - 1.5, color=P.AXIS, linewidth=1.5)
        for (i, j), val in np.ndenumerate(M):
            txt = "—" if i == j else ("n/c" if not np.isfinite(val) else f"{val:.0f}")
            dark = np.isfinite(Mc[i, j]) and Mc[i, j] > 95
            ax.text(j, i, txt, ha="center", va="center", fontsize=15, color="white" if dark else P.INK)
        ax.set_xticks(range(len(cols)), cols, rotation=0)
        ax.set_yticks(range(len(names)), names)
        ax.set_xlabel("To"); ax.set_ylabel("From")
        ax.set_title(sc.name)
        ax.grid(False)
    f.colorbar(im, ax=axes, label="Transit time, days (median over Sun phase)", shrink=0.8, extend="max")
    f.suptitle("Cislunar transit times, a_c = 0.2 mm/s²   (n/c = no converged transfer ≤ 160 d; LLO ≈ via DRO + spiral)",
               x=0.02, ha="left", fontsize=19, fontweight="bold")
    P.save(f, "q3_transfer_matrix", "q3")

    # 3D trajectories of the fastest validated transfer for a few showcase pairs
    mu = cr3bp.MU
    km = C.LU / 1e3
    showcase = [("L1 halo", "L2 halo"), ("DRO", "L2 halo"), ("L2 halo", "DRO"), ("L2 halo", "L5")]
    traces = []
    f3, ax3 = P.fig3d()
    pts = []
    for o, c in zip(orbits[:3], [P.MUTED] * 3):
        ax3.plot(*(o.states[:, :3].T * km - np.array([[(1 - mu) * km], [0], [0]])), color=c, linewidth=1.2)
    for k, (s, d) in enumerate(showcase):
        for ci, sc in enumerate(crafts):
            m = (df.src == s) & (df.dst == d) & (df.arch == sc.name) & df.validated
            if not m.any():
                continue
            b = int(df[m].sort_values("tof_days").index[0])
            traj = sh.dense_trajectory(models, crafts, batch, {k2: v for k2, v in sol.items()}, b,
                                       sh.ShootingConfig(S=2, steps_per_arc=8))
            xyz = traj[:, :3] * km - np.array([(1 - mu) * km, 0, 0])
            pts.append(xyz)
            col = P.ARCH_COLOR[sc.name]
            ls = ["-", "--", "-.", ":"][k]
            ax3.plot(xyz[:, 0], xyz[:, 1], xyz[:, 2], ls, color=col, linewidth=2,
                     label=f"{s} → {d} ({sc.name.split()[0]}, {df.tof_days[b]:.0f} d)")
            traces.append(dict(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], color=col,
                               name=f"{s} → {d} · {sc.name} · {df.tof_days[b]:.0f} d"))
    P.sphere(ax3, (0, 0, 0), C.R_MOON / 1e3 * 2, P.MOON_C)
    if pts:
        P.set_equal_3d(ax3, np.concatenate(pts))
    ax3.set_xlabel("x from Moon (km)", labelpad=14); ax3.set_ylabel("y (km)", labelpad=14); ax3.set_zlabel("z (km)", labelpad=14)
    ax3.set_title("Fastest validated transfers (Earth–Moon rotating frame)")
    ax3.legend(loc="upper left", fontsize=11)
    P.save(f3, "q3_transfers_3d", "q3")
    for o in orbits[:3]:
        xyz = o.states[:, :3] * km - np.array([(1 - mu) * km, 0, 0])
        traces.append(dict(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], color=P.MUTED, name=o.name, width=2))
    L = cr3bp.lagrange_points()
    for n in ("L1", "L2", "L4", "L5"):
        p = (L[n] - [1 - mu, 0, 0]) * km
        traces.append(dict(kind="marker", x=[p[0]], y=[p[1]], z=[p[2]], name=n, color=P.INK))
    traces.append(dict(kind="marker", x=[0], y=[0], z=[0], name="Moon", color=P.MOON_C, size=10))
    traces.append(dict(kind="marker", x=[-km], y=[0], z=[0], name="Earth", color=P.EARTH_C, size=12))
    P.plotly_html(traces, "q3_transfers_interactive", "Cislunar sail transfers (rotating frame, Moon-centred, km)", "q3")

    # small multiples (top view), one panel per showcase pair
    f, axes = P.fig(2, 2)
    for ax, (s_, d_) in zip(axes.ravel(), showcase):
        ext = []
        for o in orbits[:3]:
            xyz = o.states[:, :3] * km - np.array([(1 - mu) * km, 0, 0])
            ax.plot(xyz[:, 0] / 1e3, xyz[:, 1] / 1e3, color=P.GRID, linewidth=1.2)
        for t in traces:
            if t.get("kind") == "marker" or t["color"] == P.MUTED or not t["name"].startswith(f"{s_} → {d_} ·"):
                continue
            ax.plot(t["x"] / 1e3, t["y"] / 1e3, color=t["color"], linewidth=1.8, label=t["name"].split(" · ", 1)[1])
            ext.append(np.stack((t["x"], t["y"]), -1) / 1e3)
        for n in ("L1", "L2", "L4", "L5"):
            p = (L[n] - [1 - mu, 0, 0]) * km / 1e3
            ax.plot(p[0], p[1], "o", color=P.INK, ms=6)
            ax.annotate(n, (p[0], p[1]), xytext=(4, 6), textcoords="offset points", fontsize=13)
        ax.add_patch(P.plt.Circle((0, 0), C.R_MOON / 1e6, color=P.MOON_C))
        if ext:
            pts = np.concatenate(ext)
            lo, hi = pts.min(0), pts.max(0)
            pad = 0.08 * (hi - lo).max()
            ax.set_xlim(lo[0] - pad, hi[0] + pad); ax.set_ylim(lo[1] - pad, hi[1] + pad)
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_title(f"{s_} → {d_}", fontsize=18)
        ax.legend(fontsize=12, loc="best")
        ax.tick_params(labelsize=12)
    for ax in axes[1]:
        ax.set_xlabel("x from Moon (1000 km)", fontsize=14)
    for ax in axes[:, 0]:
        ax.set_ylabel("y (1000 km)", fontsize=14)
    f.suptitle("Fastest validated transfers, top view (rotating frame)", x=0.02, ha="left", fontsize=22, fontweight="bold")
    P.save(f, "q3_transfers_xy", "q3")


def run():
    df, sol, rows, batch, models, crafts, orbits = run_shooting()
    from .common import RESULTS
    torch.save(dict(sol=sol, rows=rows, batch=batch.__dict__), RESULTS / "q3_solutions.pt")
    llo = spiral_to_llo()
    agg = summarise(df, llo)
    plots(agg, df, sol, rows, batch, models, crafts, orbits)
    return agg


def replot():
    """Regenerate Q3 figures from saved results without re-solving."""
    from .common import RESULTS
    saved = torch.load(RESULTS / "q3_solutions.pt", weights_only=False)
    batch = sh.TransferBatch(**{k: v.to(backend.device()) for k, v in saved["batch"].items()})
    orbits = orbit_set()
    models = [sh.FourierOrbit(o) for o in orbits]
    df = pd.read_csv(RESULTS / "q3_shooting_all.csv")
    agg = pd.read_csv(RESULTS / "q3_cislunar_transfers.csv")
    plots(agg, df, saved["sol"], saved["rows"], batch, models, craft_set(), orbits)


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
