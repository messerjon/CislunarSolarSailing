"""Q6: Field of view for fixed cameras / antennas / arrays, with and without a gimballed bus.

The sail attitude is dictated by propulsion (normal within ~60 deg of the
anti-Sun line, any clock angle), so body-fixed sensors see whatever the
steering law leaves them. We fly 180 days of an L2 southern halo and a DRO,
sample operational sail attitudes (cone U[0,60 deg], clock U[0,360)), and
compute the fraction of time each target is inside the sensor field of view:

* bus BEHIND the sail (anti-Sun side): looks along +n; Sun always blocked
* bus IN FRONT of the sail (Sun side): looks along -n; sail blocks anti-Sun sky
A gimbal of range gamma lets the boresight tilt up to gamma from its axis.
The film occludes directions within 5 deg of the sail plane.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from .. import constants as C
from .. import cr3bp
from .. import plotting as P
from .common import quick, save_table

TARGETS = {"Earth (antenna, 20° beam)": ("earth", 20.0), "Moon (camera, 10° FOV)": ("moon", 10.0),
           "Sun (body-mounted array, ±60°)": ("sun", 120.0)}
GAMMAS = np.arange(0, 91, 5)


def trajectory(orbit, days=180, dt_h=2.0):
    T = days * C.DAY / C.TU
    t = np.arange(0, T, dt_h * 3600 / C.TU)
    sol = solve_ivp(cr3bp._eom_np, (0, T), orbit.state0, t_eval=t, rtol=1e-10, atol=1e-11)
    return t, sol.y[:3].T


def coverage(orbit, n_att=24, seed=0):
    rng = np.random.default_rng(seed)
    t, r = trajectory(orbit, 90 if quick() else 180)
    mu = cr3bp.MU
    th = -C.OMEGA_SUN_SYNODIC * t
    sun = np.stack((np.cos(th), np.sin(th), 0 * th), -1)
    u = -sun  # Sun -> s/c
    targets = {"earth": np.array([-mu, 0, 0]) - r, "moon": np.array([1 - mu, 0, 0]) - r, "sun": sun}
    targets = {k: v / np.linalg.norm(v, axis=-1, keepdims=True) for k, v in targets.items()}
    # attitude samples
    alpha = np.radians(rng.uniform(0, 60, (len(t), n_att)))
    clock = rng.uniform(0, 2 * np.pi, (len(t), n_att))
    e2 = np.cross(np.array([0, 0, 1.0]), u); e2 /= np.linalg.norm(e2, axis=-1, keepdims=True)
    e3 = np.cross(u, e2)
    n = (np.cos(alpha)[..., None] * u[:, None] + np.sin(alpha)[..., None]
         * (np.cos(clock)[..., None] * e2[:, None] + np.sin(clock)[..., None] * e3[:, None]))
    rows = []
    for tname, (key, fov) in TARGETS.items():
        d = targets[key][:, None, :]
        ang_back = np.degrees(np.arccos(np.clip((n * d).sum(-1), -1, 1)))  # from +n
        for placement, ang in (("Bus behind sail", ang_back), ("Bus in front of sail", 180 - ang_back)):
            unblocked = ang <= 85.0
            for g in GAMMAS:
                vis = unblocked & (ang <= g + fov / 2)
                rows.append(dict(orbit=orbit.name, target=tname, placement=placement, gimbal_deg=int(g),
                                 coverage=float(vis.mean())))
    # thin-film arrays on the sail front: power ~ cos(cone)
    rows.append(dict(orbit=orbit.name, target="Sail-mounted thin-film array (power fraction)", placement="On sail",
                     gimbal_deg=0, coverage=float(np.cos(alpha).mean())))
    return rows


def run():
    rows = []
    for orbit in (cr3bp.find_halo("L2", 15000), cr3bp.find_dro(70000)):
        rows += coverage(orbit)
    df = pd.DataFrame(rows)
    save_table(df, "q6_field_of_view")
    plots(df)
    return df


def plots(df):
    for orbit in df.orbit.unique():
        f, axes = P.fig(1, 2, sharey=True)
        for ax, placement in zip(axes, ["Bus behind sail", "Bus in front of sail"]):
            for k, t in enumerate(TARGETS):
                d = df[(df.orbit == orbit) & (df.target == t) & (df.placement == placement)]
                ax.plot(d.gimbal_deg, d.coverage * 100, marker="o", color=[P.EARTH_C, P.SERIES[4], P.SUN_C][k], label=t)
            ax.set_title(placement)
            ax.set_xlabel("Bus gimbal range relative to sail (deg)")
            ax.set_ylim(-3, 103)
        axes[0].set_ylabel("Time target is in view (%)")
        axes[1].legend(loc="center right")
        f.suptitle(f"Sensor coverage vs gimbal range — {orbit}", x=0.02, ha="left", fontsize=22, fontweight="bold")
        P.save(f, f"q6_coverage_{orbit.split()[0].lower()}_{orbit.split()[1].lower()}", "q6")


if __name__ == "__main__":
    print(run().query("gimbal_deg in (0, 30, 60, 90)").to_string())
