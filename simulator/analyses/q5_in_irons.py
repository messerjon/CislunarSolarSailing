"""Q5 - Region of 'no travel' ('in irons') for a solar sail versus a hybrid sail/SEP.

A sail can only push away from the Sun: the force lies inside a 'bubble' that
touches the origin.  For each direction at angle theta from the photon
direction we compute the maximum achievable acceleration component (support
function).  Directions where it falls below a threshold are 'in irons'.
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import sail as S, plotting as P, cr3bp as CR
from cislunar_sail.backend import get_backend
from cislunar_sail.designs import STUDY

B = get_backend("numpy")
CRH = {d.key: d for d in STUDY}["CR-H"]
RATIO_CRH = CRH.a_sep_mm / CRH.a_c_mm


def support(face, ratio=0.0, gimbal=180.0, both=True, n=721):
    th = np.linspace(0, np.pi, n)
    s = np.tile([1.0, 0, 0], (n, 1))
    d = np.stack([np.cos(th), np.sin(th), 0 * th], 1)
    if ratio <= 0:
        _, g = S.optimal_normal(B, face, s, d)
        return th, np.asarray(g)
    r = S.best_hybrid(B, face, s, d, 1.0, ratio, gimbal_deg=gimbal, both_sides=both, n_alpha=1441)
    return th, np.asarray(r["comp"])


def nogo_half_angle(th, g, tau):
    bad = np.where(g <= tau)[0]
    if bad.size == 0:
        return 0.0
    return float(180.0 - np.degrees(th[bad[0]]))


CONFIGS = [
    ("Ideal sail", S.IDEAL.front, 0.0, 180.0),
    ("Al/CP1 sail (CR-S)", S.AL_CP1.front, 0.0, 180.0),
    ("Al/PEN/Cr sail (ACS3)", S.AL_PEN_CR.front, 0.0, 180.0),
    ("Hybrid, fixed SEP (0 deg)", S.AL_CP1.front, RATIO_CRH, 0.0),
    ("Hybrid, +/-30 deg gimbal (CR-H)", S.AL_CP1.front, RATIO_CRH, 30.0),
    ("Hybrid, free SEP pointing", S.AL_CP1.front, RATIO_CRH, 180.0),
    ("Hybrid, small SEP (0.25 a_c, +/-30 deg)", S.AL_CP1.front, 0.25, 30.0),
]


def operational_fractions(curves, tau=0.05):
    """Fraction of time a desired thrust direction is 'in irons' for typical manoeuvres."""
    out = {}
    rng = np.random.default_rng(1)
    # (a) Earth-orbit raising: velocity direction sweeps the orbit plane, Sun within +/-23.4 deg of the plane
    beta = np.radians(rng.uniform(-23.44, 23.44, 4000))
    u = rng.uniform(0, 2 * np.pi, 4000)
    v = np.stack([-np.sin(u), np.cos(u), 0 * u], 1)
    s = -np.stack([np.cos(beta), 0 * beta, np.sin(beta)], 1)
    th_orbit = np.arccos(np.clip(np.sum(v * s, 1), -1, 1))
    # (b) Cislunar Jacobi-constant change in an NRHO and a DRO: rotating-frame velocity vs Sun line
    th_cis = {}
    for key, orb in (("NRHO", CR.nrho()), ("DRO", CR.dro(70000))):
        t, X = orb.sample(400)
        vv = X[:, 3:] / np.linalg.norm(X[:, 3:], axis=1, keepdims=True)
        ph = rng.uniform(0, 2 * np.pi, (400, 10))
        sh = -np.stack([np.cos(ph), np.sin(ph), 0 * ph], -1)
        th_cis[key] = np.arccos(np.clip(np.sum(vv[:, None, :] * sh, -1), -1, 1)).ravel()
    # (c) station keeping: isotropic correction directions
    z = rng.uniform(-1, 1, 20000)
    th_iso = np.arccos(z)
    for name, (th, g) in curves.items():
        gi = lambda x: np.interp(x, th, g)
        out[name] = {
            "orbit_raising": float(np.mean(gi(th_orbit) < tau)),
            "orbit_raising_mean_eff": float(np.mean(gi(th_orbit))),
            "NRHO_jacobi": float(np.mean(gi(th_cis["NRHO"]) < tau)),
            "DRO_jacobi": float(np.mean(gi(th_cis["DRO"]) < tau)),
            "isotropic_SK": float(np.mean(gi(th_iso) < tau)),
            "isotropic_mean_eff": float(np.mean(gi(th_iso))),
        }
    return out


def fig_bubbles(path):
    f, (ax1, ax2) = P.fig(1, 2, size=(11, 5.4), gridspec_kw={"width_ratios": [1, 1.25]})
    cols = [P.MUTED, P.BLUE, P.ORANGE, P.AQUA]
    mats = [("Ideal", S.IDEAL.front), ("Al/CP1", S.AL_CP1.front), ("Al/PEN/Cr", S.AL_PEN_CR.front),
            ("Al/CP1/Al 2-sided", S.AL_AL_CP1.front)]
    for (nm, face), c in zip(mats, cols):
        a, fs, fp = S.meridian(face)
        fs, fp = fs / face.total, fp / face.total
        ax1.plot(np.r_[fs[::-1], fs], np.r_[-fp[::-1], fp], color=c, lw=2, label=nm)
    # no-go cone for Al/CP1
    cone = S.max_force_cone_angle_deg(S.AL_CP1.front)
    half = 90 - cone
    ang = np.radians(np.linspace(180 - half, 180 + half, 50))
    ax1.fill(np.r_[0, 0.95 * np.cos(ang), 0], np.r_[0, 0.95 * np.sin(ang), 0], color=P.RED, alpha=0.12, lw=0)
    ax1.annotate("", xy=(0.55, 0), xytext=(-0.05, 0), arrowprops=dict(arrowstyle="-|>", color=P.YELLOW, lw=2))
    ax1.text(-0.62, 0.05, f"no-go cone\n(Al/CP1, +/-{half:.0f} deg)", color=P.INK2, fontsize=10.5)
    ax1.text(0.10, -0.12, "sunlight", color=P.INK2, fontsize=10.5)
    ax1.set_aspect("equal"); ax1.set_xlim(-0.75, 1.1); ax1.set_ylim(-0.75, 0.75)
    ax1.set_xlabel("acceleration along sunlight / a_c"); ax1.set_ylabel("perpendicular / a_c")
    ax1.legend(loc="upper left", fontsize=10)
    P.title(ax1, "Sail force 'bubbles'")
    th = np.linspace(0, 180, 721)
    show = [CONFIGS[1], CONFIGS[3], CONFIGS[4], CONFIGS[5]]
    for (nm, face, r, gb), c in zip(show, [P.BLUE, P.ORANGE, P.AQUA, P.YELLOW]):
        _, g = support(face, r, gb)
        ax2.plot(th, g, color=c, label=nm)
    ax2.axhline(0.05, color=P.RED, lw=1)
    ax2.text(2, 0.08, "5 % 'in irons' threshold", color=P.INK2, fontsize=10)
    ax2.set_xlabel("angle between desired thrust and sunlight, theta (deg)")
    ax2.set_ylabel("max. useful acceleration / a_c")
    ax2.set_xlim(0, 180); ax2.set_ylim(-0.02, 2.6); ax2.set_xticks(range(0, 181, 30))
    ax2.legend(loc="upper right", fontsize=10)
    P.title(ax2, "Useful acceleration vs direction")
    f.tight_layout()
    return P.save(f, path)


def fig_3d(path):
    f, ax = P.fig3d(size=(9, 6.2))
    face = S.AL_CP1.front
    a, fs, fp = S.meridian(face, 181)
    fs, fp = fs / face.total, fp / face.total
    ph = np.linspace(0, 2 * np.pi, 73)
    X = np.outer(fs, np.ones_like(ph)); Y = np.outer(fp, np.cos(ph)); Z = np.outer(fp, np.sin(ph))
    ax.plot_surface(X, Y, Z, color=P.BLUE, alpha=0.35, linewidth=0, shade=True)
    th, g = support(face, RATIO_CRH, 30.0, n=181)
    Xh = np.outer(g * np.cos(th), np.ones_like(ph)); R = g * np.sin(th)
    Yh = np.outer(R, np.cos(ph)); Zh = np.outer(R, np.sin(ph))
    ax.plot_wireframe(Xh, Yh, Zh, color=P.ORANGE, linewidth=0.5, rstride=8, cstride=6, alpha=0.8)
    ax.quiver(-1.9, 0, 0, 1.2, 0, 0, color=P.YELLOW, linewidth=2.5, arrow_length_ratio=0.15)
    ax.text(-1.9, 0, 0.18, "sunlight", color=P.INK2)
    ax.set_xlabel("along sunlight / a_c", labelpad=8); ax.set_ylabel("y / a_c", labelpad=8); ax.set_zlabel("z / a_c")
    for setter in (ax.set_xticks, ax.set_yticks, ax.set_zticks):
        setter([-2, -1, 0, 1, 2])
    P.set_equal_3d(ax, np.r_[Xh.ravel(), -1.9], Yh.ravel(), Zh.ravel())
    ax.view_init(elev=22, azim=-58)
    ax.set_title("Reachable acceleration: sail bubble (blue) vs CR-H hybrid reach (orange mesh)",
                 loc="left", fontsize=13)
    return P.save(f, path)


def fig_fractions(path, fr):
    names = [("Ideal sail", "Ideal sail"), ("Al/CP1 sail (CR-S)", "Al/CP1 sail (CR-S, Solar Cruiser film)"),
             ("Al/PEN/Cr sail (ACS3)", "Al/PEN/Cr sail (ACS3 film)")]
    keys = [("orbit_raising", "Earth-orbit\nraising"), ("NRHO_jacobi", "NRHO energy\nchange"),
            ("DRO_jacobi", "DRO energy\nchange"), ("isotropic_SK", "Station-keeping\n(any direction)")]
    f, ax = P.fig(size=(10, 5.2))
    w = 0.24
    x = np.arange(len(keys))
    for i, ((nm, lab), c) in enumerate(zip(names, [P.MUTED, P.BLUE, P.ORANGE])):
        vals = [100 * fr[nm][k] for k, _ in keys]
        ax.bar(x + (i - 1) * w, vals, w * 0.9, color=c, label=lab)
        for xb, v in zip(x + (i - 1) * w, vals):
            ax.text(xb, v + 0.6, f"{v:.0f}", ha="center", fontsize=10, color=P.INK2)
    ax.text(0.37, 0.62, "All hybrid sail + SEP variants\n(fixed, +/-30 deg gimbal, free): 0 %",
            transform=ax.transAxes, ha="center", va="top", fontsize=11, color=P.INK,
            bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec=P.GRID))
    ax.set_xticks(x); ax.set_xticklabels([k[1] for k in keys])
    ax.set_ylabel("time 'in irons' (useful accel. < 5 % a_c), %")
    ax.set_ylim(0, 46)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(axis="x", visible=False)
    P.title(ax, "How often the desired thrust direction is unreachable")
    return P.save(f, path)


def run():
    with Timer("Q5 in-irons"):
        curves = {}
        table = []
        for nm, face, r, gb in CONFIGS:
            th, g = support(face, r, gb)
            curves[nm] = (th, g)
            table.append({"config": nm, "a_sep_over_ac": r, "gimbal_deg": gb,
                          "nogo_half_angle_deg_tau0": nogo_half_angle(th, g, 1e-6),
                          "nogo_half_angle_deg_tau5pct": nogo_half_angle(th, g, 0.05),
                          "nogo_half_angle_deg_tau10pct": nogo_half_angle(th, g, 0.10),
                          "max_force_cone_deg": S.max_force_cone_angle_deg(face) if r == 0 else None,
                          "sunward_capability_over_ac": float(g[-1]),
                          "perp_capability_over_ac": float(np.interp(np.pi / 2, th, g))})
        fr = operational_fractions(curves)
        figs = [fig_bubbles("q5_force_bubbles.png"), fig_3d("q5_envelope_3d.png"),
                fig_fractions("q5_in_irons_fraction.png", fr)]
        res = {"configs": table, "operational_in_irons": fr, "ratio_crh": RATIO_CRH,
               "figures": [f.split("/")[-1] for f in figs]}
        save_results("q5_in_irons", res)
        return res


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1)[:3000])
