"""Q4: What does it take to hold a lunar (south) pole-sitter?

A pole-sitter hovers at a fixed point of the Earth-Moon rotating frame below
the Moon (z < 0) with continuous view of the south pole. Holding a fixed point
requires a = -(gravity + centrifugal) (Coriolis vanishes at rest). The Sun
circles once per synodic month, so the sail must deliver that acceleration at
every Sun angle; whatever it cannot is supplied by SEP.

For a grid of hover points and 36 Sun phases we find the sail attitude that
minimises the residual |a_req - a_sail| (candidate search, batched), then report:
  * a_req and the minimum characteristic acceleration for sail-only hovering;
  * SEP residual acceleration and the propellant needed per year (hybrid).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import torch

from .. import backend, cr3bp, presets
from .. import constants as C
from .. import plotting as P
from ..spacecraft import Batch, fibonacci_sphere, sail_force_per_area
from .common import quick, save_table


def residual_map(xs, zs, sc, n_sun=36, k=3000):
    """Return a_req [X,Z] and residual SEP accel [X,Z,n_sun] (m/s^2)."""
    T = backend.tensor
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    r = T(np.stack((X, np.zeros_like(X), Z), -1).reshape(-1, 3))
    v = torch.zeros_like(r)
    a_req = -cr3bp.accel_natural(r, v) * C.AU_ACC        # [N,3] m/s^2
    b = Batch([sc])
    nrm = fibonacci_sphere(k)
    res = []
    for th in np.linspace(0, 2 * math.pi, n_sun, endpoint=False):
        sun = T([math.cos(th), math.sin(th), 0.0])
        f = sail_force_per_area(nrm[None], -sun, b.front, b.back)[0]       # [k,3]
        a_s = C.SOLAR_PRESSURE_1AU * sc.sail.area / sc.mass * f
        a_s = torch.cat((a_s, torch.zeros(1, 3, dtype=a_s.dtype, device=a_s.device)), 0)  # include "no sail"
        d = (a_req[:, None, :] - a_s[None]).norm(dim=-1)                  # [N,k+1]
        res.append(d.min(-1).values)
    res = torch.stack(res, -1)
    return a_req.norm(dim=-1).reshape(X.shape).cpu().numpy(), res.reshape(*X.shape, n_sun).cpu().numpy()


def run():
    nx, nz = (40, 30) if quick() else (90, 70)
    mu = cr3bp.MU
    xs = np.linspace(0.80, 1.20, nx)
    zs = np.linspace(-0.30, -0.02, nz)
    acs = [0.2e-3, 0.5e-3, 1.0e-3, 1.5e-3]  # 1.5 needs a ~370 m sail: the practical ceiling for CP1 + booms
    out = {}
    rows = []
    for ac in acs:
        sc = presets.conventional(ac)
        a_req, resid = residual_map(xs, zs, sc)
        worst, mean = resid.max(-1), resid.mean(-1)
        out[ac] = (a_req, worst, mean)
        # pole visibility: elevation of the point above the south-pole horizon >= 10 deg
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    pole = np.array([1 - mu, 0, -C.R_MOON / C.LU])
    rel = np.stack((X - pole[0], np.zeros_like(X), Z - pole[2]), -1)
    elev = np.degrees(np.arcsin(-rel[..., 2] / np.linalg.norm(rel, axis=-1)))
    visible = elev >= 10
    hyb = presets.hybrid(0.2e-3, gimbal_deg=30)
    for ac in acs:
        a_req, worst, mean = out[ac]
        sail_only = (worst < 1e-6) & visible
        rows.append(dict(ac_mm_s2=ac * 1e3,
                         sail_only_feasible_points=int(sail_only.sum()),
                         min_req_accel_visible_mm_s2=float(a_req[visible].min() * 1e3),
                         min_mean_sep_residual_mm_s2=float(mean[visible].min() * 1e3),
                         min_dv_per_year_km_s=float(mean[visible].min() * C.YEAR / 1e3),
                         prop_kg_per_year_100kg_isp1500=float(100 * (1 - math.exp(-mean[visible].min() * C.YEAR / (C.G0 * 1500))))))
    df = pd.DataFrame(rows)
    save_table(df, "q4_pole_sitter")
    plots(xs, zs, out, visible, acs)
    return df


def plots(xs, zs, out, visible, acs):
    mu = cr3bp.MU
    km = C.LU / 1e3
    X, Z = np.meshgrid((xs - (1 - mu)) * km, zs * km, indexing="ij")
    a_req = out[acs[0]][0]
    f, ax = P.fig()
    lv = [0.2, 0.5, 1, 2, 5, 10, 20]
    from matplotlib.colors import BoundaryNorm
    levels = [0] + lv + [1e3]
    cs = ax.contourf(X, Z, a_req * 1e3, levels=levels, cmap=P.CMAP_SEQ, norm=BoundaryNorm(levels, P.CMAP_SEQ.N))
    cl = ax.contour(X, Z, a_req * 1e3, levels=lv, colors=P.INK2, linewidths=0.8)
    ax.clabel(cl, fmt="%g", fontsize=12)
    ax.contour(X, Z, visible, levels=[0.5], colors=P.SERIES[1], linewidths=2.2, linestyles="--")
    moon = P.plt.Circle((0, 0), C.R_MOON / 1e3, color=P.MOON_C)
    ax.add_patch(moon)
    L = cr3bp.lagrange_points()
    for n in ("L1", "L2"):
        ax.plot((L[n][0] - (1 - mu)) * km, 0, "o", color=P.INK, ms=8)
        ax.text((L[n][0] - (1 - mu)) * km, 2500, n, ha="center", color=P.INK)
    ax.set_aspect("equal")
    ax.set_ylim(zs.min() * km, 8000)
    ax.set_xlabel("x from Moon centre, toward L2 (km)")
    ax.set_ylabel("z below lunar orbit plane (km)")
    ax.set_title("Acceleration needed to hover below the lunar south pole (mm/s²)")
    P.subtitle(ax, "Rotating Earth–Moon frame; south pole ≥10° above the horizon everywhere below the dashed orange line. Sail a_c today ≈ 0.05–0.2 mm/s²")
    f.colorbar(cs, ax=ax, label="Required acceleration (mm/s²)", shrink=0.9, ticks=levels[:-1], format="%g")
    P.save(f, "q4_required_acceleration", "q4")

    f, axes = P.fig(1, 2, sharey=True)
    for ax, ac in zip(axes, [acs[1], acs[3]]):
        _, worst, mean = out[ac]
        from matplotlib.colors import BoundaryNorm
        levels = [0, 0.01, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 1e3]
        cs = ax.contourf(X, Z, mean * 1e3, levels=levels, cmap=P.CMAP_SEQ, norm=BoundaryNorm(levels, P.CMAP_SEQ.N))
        ax.contour(X, Z, (worst < 1e-6).astype(float), levels=[0.5], colors=P.SERIES[2], linewidths=2.5)
        ax.contour(X, Z, visible, levels=[0.5], colors=P.SERIES[1], linewidths=2.0, linestyles="--")
        ax.add_patch(P.plt.Circle((0, 0), C.R_MOON / 1e3, color=P.MOON_C))
        ax.set_aspect("equal")
        ax.set_title(f"Sail a_c = {ac*1e3:g} mm/s²")
        ax.set_xlabel("x from Moon (km)")
    axes[0].set_ylabel("z (km)")
    f.colorbar(cs, ax=axes, label="Month-average SEP acceleration still needed (mm/s²)", shrink=0.85,
               ticks=levels[:-1], format="%g")
    f.suptitle("Hybrid pole-sitter: what the sail cannot cover, SEP must  (green = sail-only feasible all month)",
               x=0.02, ha="left", fontsize=20, fontweight="bold")
    P.save(f, "q4_sep_residual", "q4")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
