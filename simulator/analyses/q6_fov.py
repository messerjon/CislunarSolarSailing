"""Q6 - Field of view of a fixed camera, antenna and solar array with and without a
gimballed bus relative to the sail.

The sail attitude is dictated by propulsion (sail normal n from the locally
optimal law for the current thrust demand), so a body-fixed instrument points
wherever propulsion puts it.  Free roll about n is assumed (sail force is roll
invariant), so access depends only on the angle psi between a target and the
instrument axis.  The sail membrane blocks +/-5 deg about its plane.
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import cr3bp as CR, sail as S, plotting as P
from cislunar_sail.backend import get_backend
from cislunar_sail.constants import L_EM_KM, T_EM_S, DAY_S, OMEGA_SUN_SYNODIC, R_MOON

B = get_backend("numpy")
MU = CR.MU
FACE = S.AL_CP1.front
OBSTRUCT = 85.0      # deg from the instrument face normal (sail plane +/- 5 deg)
CONFIGS = [("Fixed, boresight on sail normal", "fixed", 0.0),
           ("Fixed, best tilt (design-time)", "tilt", 0.0),
           ("Gimbal +/-30 deg", "gimbal", 30.0),
           ("Gimbal +/-60 deg", "gimbal", 60.0),
           ("Gimbal +/-90 deg (hemisphere)", "gimbal", 90.0)]
TARGETS = {"Earth (HGA, 10 deg beam)": 10.0, "Lunar south pole (camera, 10 deg)": 10.0,
           "SDA field, anti-Sun hemisphere (camera, 15 deg)": 15.0}


def attitude_history(orbit, demand="maneuver", days=118.0, dt_d=0.25, seed=3):
    rng = np.random.default_rng(seed)
    t, X = orbit.sample(600)
    P_nd = orbit.period
    tt = np.arange(0, days, dt_d)
    tn = tt * DAY_S / T_EM_S
    idx = np.clip(((tn % P_nd) / P_nd * (len(t) - 1)).astype(int), 0, len(t) - 1)
    Xs = X[idx]
    th0 = rng.uniform(0, 2 * np.pi)
    th = th0 - OMEGA_SUN_SYNODIC * tn
    u_sun = np.stack([np.cos(th), np.sin(th), 0 * th], 1)
    s_hat = -u_sun
    if demand == "maneuver":
        blocks = np.floor(tt / 0.5).astype(int)
        dirs = rng.normal(size=(blocks.max() + 1, 3)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        d = dirs[blocks]
    else:
        d = Xs[:, 3:] / np.linalg.norm(Xs[:, 3:], axis=1, keepdims=True)
    n, g = S.optimal_normal(B, FACE, s_hat, d)
    r = Xs[:, :3]
    earth = np.array([-MU, 0, 0]) - r
    pole = np.array([1 - MU, 0, -R_MOON / L_EM_KM]) - r
    blocks = np.floor(tt / 0.5).astype(int)
    sda = rng.normal(size=(blocks.max() + 1, 3)); sda /= np.linalg.norm(sda, axis=1, keepdims=True)
    sda = sda[blocks]
    flip = np.sum(sda * u_sun, 1) > 0
    sda[flip] *= -1                                    # keep targets in the anti-Sun hemisphere
    tg = {"Earth (HGA, 10 deg beam)": earth / np.linalg.norm(earth, axis=1, keepdims=True),
          "Lunar south pole (camera, 10 deg)": pole / np.linalg.norm(pole, axis=1, keepdims=True),
          "SDA field, anti-Sun hemisphere (camera, 15 deg)": sda}
    return {"t": tt, "n": n, "u_sun": u_sun, "targets": tg, "cone_deg": np.degrees(np.arccos(np.clip(np.sum(n * s_hat, 1), -1, 1)))}


def access(hist):
    n = hist["n"]
    out = {}
    for name, w in TARGETS.items():
        tdir = hist["targets"][name]
        psi_plus = np.degrees(np.arccos(np.clip(np.sum(tdir * n, 1), -1, 1)))      # instrument on +n (anti-Sun) face
        psi_minus = 180.0 - psi_plus                                                # instrument on -n (Sun) face
        res = {}
        for lab, kind, G in CONFIGS:
            best = 0.0
            for psi in (psi_plus, psi_minus):
                vis_ok = psi <= OBSTRUCT
                if kind == "fixed":
                    v = (psi <= w) & vis_ok
                    best = max(best, v.mean())
                elif kind == "tilt":
                    for gam in np.arange(0, OBSTRUCT + 0.1, 2.5):
                        v = (np.abs(psi - gam) <= w) & vis_ok
                        best = max(best, v.mean())
                else:
                    v = (psi <= G + w) & vis_ok
                    best = max(best, v.mean())
            res[lab] = float(best)
        out[name] = res
    # solar array on the Sun-facing side (normal -n): incidence = sail cone angle
    cone = hist["cone_deg"]
    pw = {}
    for lab, kind, G in CONFIGS:
        if kind in ("fixed", "tilt"):
            inc = cone
        else:
            inc = np.maximum(cone - G, 0)
        pw[lab] = float(np.mean(np.cos(np.radians(np.minimum(inc, 90.0)))))
    out["Solar array power (fraction of max)"] = pw
    return out


def fig_access(acc, path, title):
    groups = list(acc.keys())
    labels = [c[0] for c in CONFIGS]
    f, ax = P.fig(size=(11, 5.4))
    w = 0.16
    x = np.arange(len(groups))
    cols = [P.MUTED, P.BLUE, P.AQUA, P.ORANGE, P.VIOLET]
    for i, (lab, c) in enumerate(zip(labels, cols)):
        vals = [100 * acc[g][lab] for g in groups]
        ax.bar(x + (i - 2) * w, vals, w * 0.9, color=c, label=lab)
        for xb, v in zip(x + (i - 2) * w, vals):
            ax.text(xb, v + 1, f"{v:.0f}", ha="center", fontsize=8.5, color=P.INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(["Earth link\n(HGA, 10 deg)", "Lunar south pole\n(camera, 10 deg)",
                        "SDA targets, anti-Sun\n(camera, 15 deg)", "Solar-array power\n(% of maximum)"], fontsize=10.5)
    ax.set_ylabel("% of time target in view / % power")
    ax.set_ylim(0, 112)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=9.5, ncol=3)
    P.title(ax, title)
    return P.save(f, path)


def fig_psi(hist, path):
    f, ax = P.fig(size=(10, 4.8))
    n = hist["n"]
    bins = np.linspace(0, 180, 37)
    for (name, w), c in zip(TARGETS.items(), [P.BLUE, P.ORANGE, P.AQUA]):
        psi = np.degrees(np.arccos(np.clip(np.sum(hist["targets"][name] * n, 1), -1, 1)))
        h, e = np.histogram(psi, bins=bins, density=True)
        ax.plot(0.5 * (e[1:] + e[:-1]), h * 100 * 5, color=c, label=name.split(" (")[0])
    cone = hist["cone_deg"]
    h, e = np.histogram(180 - cone, bins=bins, density=True)
    ax.plot(0.5 * (e[1:] + e[:-1]), h * 100 * 5, color=P.YELLOW, label="Sun")
    ax.axvspan(0, 10, color=P.MUTED, alpha=0.15, lw=0)
    ax.text(5, ax.get_ylim()[1] * 0.92 if False else 26, "fixed\n10 deg", ha="center", fontsize=9, color=P.INK2)
    ax.axvspan(10, 70, color=P.ORANGE, alpha=0.06, lw=0)
    ax.text(40, 26, "+/-60 deg gimbal adds this band", ha="center", fontsize=9.5, color=P.INK2)
    ax.axvline(85, color=P.AXIS, lw=1); ax.axvline(95, color=P.AXIS, lw=1)
    ax.text(90, 1, "sail\nplane", ha="center", fontsize=9, color=P.INK2)
    ax.set_xlim(0, 180); ax.set_xticks(range(0, 181, 30)); ax.set_ylim(0, 30)
    ax.set_xlabel("angle between target direction and sail normal (+n = anti-Sun face), deg")
    ax.set_ylabel("% of time per 5 deg bin")
    ax.legend(loc="upper right", fontsize=10)
    P.title(ax, "Propulsion-driven attitude scatters targets across the whole sky")
    return P.save(f, path)


def fig_cones(path):
    """3-D schematic: sail, normal, fixed narrow FOV and gimballed field of regard."""
    f, ax = P.fig3d(size=(9, 6.2))
    L = 1.0
    sq = np.array([[-L, -L, 0], [L, -L, 0], [L, L, 0], [-L, L, 0], [-L, -L, 0]])
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ax.add_collection3d(Poly3DCollection([sq[:4]], facecolor="#cde2fb", edgecolor=P.BLUE, alpha=0.55, linewidths=1.2))
    for c in sq[:4]:
        ax.plot([0, c[0]], [0, c[1]], [0, 0], color=P.INK2, lw=1)
    def cone(half_deg, h, color, alpha, wire=False):
        a = math.radians(half_deg)
        th = np.linspace(0, 2 * np.pi, 60); z = np.linspace(0, h, 12)
        T, Z = np.meshgrid(th, z)
        R = Z * math.tan(a)
        Xc, Yc = R * np.cos(T), R * np.sin(T)
        if wire:
            ax.plot_wireframe(Xc, Yc, Z, color=color, linewidth=0.5, rstride=2, cstride=4, alpha=alpha)
        else:
            ax.plot_surface(Xc, Yc, Z, color=color, alpha=alpha, linewidth=0)
    cone(70.0, 0.55, P.ORANGE, 0.55, wire=True)
    cone(10.0, 1.6, P.VIOLET, 0.55)
    ax.quiver(0, 0, 0, 0, 0, 1.9, color=P.INK, linewidth=2, arrow_length_ratio=0.08)
    ax.text(0.05, 0.05, 1.95, "sail normal n (anti-Sun side)", color=P.INK)
    ax.quiver(-1.2, -1.2, -1.5, 0.8, 0.8, 1.0, color=P.YELLOW, linewidth=2.5, arrow_length_ratio=0.12)
    ax.text(-1.25, -1.25, -1.62, "sunlight", color=P.INK2)
    ax.text(0.35, 0.0, 1.55, "fixed camera / HGA\n(10 deg FOV)", color=P.VIOLET, fontsize=10)
    ax.text(-1.55, -1.0, 0.25, "field of regard with\n+/-60 deg 2-axis gimbal", color=P.ORANGE, fontsize=10)
    ax.set_xlim(-1.3, 1.3); ax.set_ylim(-1.3, 1.3); ax.set_zlim(-1.6, 2.0)
    ax.set_box_aspect((1, 1, 1.25))
    ax.set_axis_off()
    ax.view_init(elev=18, azim=-62)
    ax.set_title("Body-fixed vs gimballed instruments on a sailcraft", loc="left", fontsize=13)
    return P.save(f, path)


def run():
    with Timer("Q6 FOV"):
        res = {}
        figs = []
        for oname, orb in (("DRO 70k", CR.dro(70000)), ("NRHO 9:2", CR.nrho())):
            for demand in ("maneuver", "energy"):
                h = attitude_history(orb, demand)
                acc = access(h)
                res[f"{oname} / {demand}"] = acc
                if oname == "DRO 70k" and demand == "maneuver":
                    figs.append(fig_access(acc, "q6_fov_access.png",
                                           "Share of time each target is reachable (DRO, propulsion-driven attitude)"))
                    figs.append(fig_psi(h, "q6_target_angles.png"))
        figs.append(fig_cones("q6_fov_schematic_3d.png"))
        out = {"assumptions": {"obstruction_deg_from_face_normal": OBSTRUCT, "roll_free_about_normal": True,
                               "demand_models": {"maneuver": "isotropic random thrust demand, new every 12 h",
                                                 "energy": "Jacobi-constant change along rotating-frame velocity"}},
               "access": res, "figures": [p.split("/")[-1] for p in figs]}
        save_results("q6_fov", out)
        return out


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps(r["access"], indent=1))
