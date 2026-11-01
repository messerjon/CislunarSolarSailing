"""Q5: Where is the "no-travel" (in irons) region for a sail versus a hybrid?

A sail can never push toward the Sun; with real optics its force is confined
to a cone around the anti-Sun line. Hybrids fill the gap with SEP.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd

from .. import backend, presets
from .. import plotting as P
from .. import envelope as E
from ..spacecraft import fibonacci_sphere
from .common import save_table

IRONS_FRACTION = 0.10  # direction counts as "in irons" if < 10% of a_c is available along it


def architectures(ac=0.2e-3):
    return [presets.conventional(ac), presets.hybrid(ac, gimbal_deg=0.0), presets.hybrid(ac, gimbal_deg=30.0),
            dataclasses.replace(presets.hybrid(ac, gimbal_deg=30.0, retractable=True), name="Retractable hybrid")]


def run():
    rows, curves = [], {}
    for sc in architectures():
        th, rho = E.envelope(sc)
        curves[sc.name] = (th, rho)
        ac = presets.conventional(0.2e-3).characteristic_acceleration
        irons = th[rho < IRONS_FRACTION * ac]
        # solid-angle fraction of in-irons directions (axisymmetric)
        w = np.sin(np.radians(th))
        frac = float((w * (rho < IRONS_FRACTION * ac)).sum() / w.sum())
        sph = fibonacci_sphere(4000)
        sup = E.support(sc, sph).cpu().numpy()
        rows.append(dict(arch=sc.name, ac_mm_s2=sc.characteristic_acceleration * 1e3,
                         sep_mm_s2=sc.sep_acceleration * 1e3,
                         irons_cone_from_sun_deg=float(180 - irons.min()) if len(irons) else 0.0,
                         irons_solid_angle_frac=frac,
                         max_accel_mm_s2=float(rho.max() * 1e3),
                         min_dir_accel_mm_s2=float(rho.min() * 1e3),
                         mean_support_mm_s2=float(np.clip(sup, 0, None).mean() * 1e3)))
    df = pd.DataFrame(rows)
    save_table(df, "q5_in_irons")
    plots(curves)
    return df


def plots(curves):
    # polar "force bubble" cross-section; anti-Sun direction to the right
    f = P.plt.figure(constrained_layout=True)
    ax = f.add_subplot(111, projection="polar")
    ax.set_facecolor(P.SURFACE)
    for name, (th, rho) in curves.items():
        col = P.ARCH_COLOR.get(name, P.SERIES[4])
        t = np.radians(np.concatenate((th, 360 - th[::-1])))
        r = np.concatenate((rho, rho[::-1])) * 1e3
        ax.plot(t, r, color=col, label=name)
        ax.fill(t, r, color=col, alpha=0.06)
    ax.set_theta_zero_location("E")
    ax.set_thetagrids([0, 45, 90, 135, 180, 225, 270, 315],
                      ["anti-Sun", "45°", "90°", "135°", "Sun", "135°", "90°", "45°"])
    ax.set_rlabel_position(100)
    ax.set_title("Achievable acceleration by direction (mm/s²)")
    ax.annotate("sunlight →", xy=(math.pi, ax.get_rmax()), xytext=(-60, 0), textcoords="offset points", color=P.INK2,
                fontsize=14, ha="right", va="center")
    ax.legend(loc="upper left", bbox_to_anchor=(1.05, 1.0))
    P.save(f, "q5_force_bubble_polar", "q5")

    # 2D line version
    f, ax = P.fig()
    for name, (th, rho) in curves.items():
        ax.plot(th, rho * 1e3, color=P.ARCH_COLOR.get(name, P.SERIES[4]), label=name)
    ac = presets.conventional(0.2e-3).characteristic_acceleration * 1e3
    ax.axhline(IRONS_FRACTION * ac, color=P.MUTED, linestyle="--", linewidth=1.3)
    ax.axvspan(90, 180, color=P.GRID, alpha=0.5, linewidth=0)
    ax.text(135, ax.get_ylim()[1] * 0.92, "sunward hemisphere", ha="center", color=P.INK2, fontsize=14)
    ax.text(2, IRONS_FRACTION * ac * 1.15, "in-irons threshold (10% of a_c)", color=P.INK2, fontsize=13)
    ax.set_xlabel("Direction of desired acceleration, angle from anti-Sun line (deg)")
    ax.set_ylabel("Max acceleration along that direction (mm/s²)")
    ax.set_title("The 'in irons' region: where a sail cannot push")
    P.subtitle(ax, "a_c = 0.2 mm/s² for all; hybrids add 10 mN SEP (≈0.10 mm/s²). Fixed SEP thrusts opposite the sail normal; gimbal ±30°")
    ax.set_xlim(0, 180)
    ax.legend(loc="upper right")
    P.save(f, "q5_envelope_vs_angle", "q5")

    # 3D bubbles
    f, ax = P.fig3d()
    phi = np.linspace(0, 2 * np.pi, 72)
    for name, (th, rho) in curves.items():
        T, PH = np.meshgrid(np.radians(th), phi)
        R = np.tile(rho * 1e3, (len(phi), 1))
        X, Y, Z = R * np.cos(T), R * np.sin(T) * np.cos(PH), R * np.sin(T) * np.sin(PH)
        ax.plot_wireframe(X, Y, Z, rstride=6, cstride=8, color=P.ARCH_COLOR.get(name, P.SERIES[4]), linewidth=0.6, label=name)
    ax.quiver(-0.35, 0, 0, 0.12, 0, 0, color=P.SUN_C, linewidth=3)
    ax.text(-0.42, 0, 0.02, "sunlight", color=P.INK2)
    ax.set_xlabel("anti-Sun (mm/s²)", labelpad=12); ax.set_ylabel("(mm/s²)", labelpad=12); ax.set_zlabel("(mm/s²)", labelpad=12)
    ax.set_title("3-D acceleration envelopes")
    ax.legend(loc="upper left")
    lim = max(r.max() for _, r in curves.values()) * 1e3
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim); ax.set_box_aspect((1, 1, 1))
    P.save(f, "q5_force_bubble_3d", "q5")


if __name__ == "__main__":
    backend.configure()
    print(run().to_string())
