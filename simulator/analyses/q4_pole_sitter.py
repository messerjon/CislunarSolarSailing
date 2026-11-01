"""Q4 - What is necessary to achieve a lunar pole-sitter orbit?

A pole-sitter hovers (stays fixed in the Earth-Moon rotating frame) below the
lunar south pole.  The control acceleration must cancel gravity + centrifugal
acceleration, a_req = -g(r) (= grad U).  A sail can only supply vectors on its
force bubble, which rotates with the Sun once per synodic month, so a static
hover needs SEP for the residual.  We map the requirement, the residual SEP
demand for sails of increasing a_c, and size the propellant.
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import cr3bp as CR, sail as S, plotting as P
from cislunar_sail.backend import get_backend
from cislunar_sail.constants import L_EM_KM, A_EM_MMS2, R_MOON, YEAR_S, G0
from cislunar_sail.designs import STUDY

B = get_backend("numpy")
MU = CR.MU
FACE = S.AL_CP1.front
D = {d.key: d for d in STUDY}
AC_SET = [0.0, D["CR-S"].a_c_mm, 0.5, 1.0, 1.7]


def a_req_mm(xkm, zkm, ykm=0.0):
    """Required hover acceleration (mm/s^2) at Moon-centred coordinates (km)."""
    r = np.stack([1 - MU + np.asarray(xkm) / L_EM_KM, np.asarray(ykm) / L_EM_KM + 0 * np.asarray(xkm),
                  np.asarray(zkm) / L_EM_KM], -1)
    return -CR.accel_gc(B, r) * A_EM_MMS2


def residual_sep(areq, ac, n_sun=36, n_alpha=241):
    """Minimum SEP acceleration |a_req - a_sail| over sail attitudes, per Sun phase.
    areq (...,3) mm/s^2 -> (..., n_sun)."""
    th = np.linspace(0, 2 * np.pi, n_sun, endpoint=False)
    u_sun = np.stack([np.cos(th), np.sin(th), 0 * th], -1)         # (S,3)
    s = -u_sun
    A = areq[..., None, :]                                          # (...,1,3)
    if ac <= 0:
        return np.broadcast_to(np.linalg.norm(areq, axis=-1)[..., None], areq.shape[:-1] + (n_sun,)).copy()
    a_par = np.sum(A * s, -1)                                       # (...,S)
    perp = A - a_par[..., None] * s
    a_perp = np.linalg.norm(perp, axis=-1)
    al = np.linspace(0, np.pi / 2, n_alpha)
    c = np.cos(al)
    fn = c * (FACE.a1 * c + FACE.a2)
    Fs = (c * FACE.a3 + fn * c) / FACE.total * ac                   # (A,)
    Fp = (fn * np.sin(al)) / FACE.total * ac
    d2 = (a_par[..., None] - Fs) ** 2 + (a_perp[..., None] - Fp) ** 2
    best = np.sqrt(np.min(d2, axis=-1))
    return np.minimum(best, np.linalg.norm(areq, axis=-1)[..., None])


def elevation_from_south_pole(xkm, zkm):
    zp = zkm + R_MOON
    return np.degrees(np.arctan2(-zp, np.abs(xkm)))


def maps():
    x = np.linspace(-120e3, 120e3, 121)
    z = np.linspace(-160e3, -5e3, 79)
    X, Z = np.meshgrid(x, z)
    areq = a_req_mm(X, Z)
    mag = np.linalg.norm(areq, axis=-1)
    inside = np.hypot(X, Z) < R_MOON * 1.5
    sep = {}
    for ac in AC_SET:
        sep[ac] = residual_sep(areq, ac).mean(axis=-1)
    return x, z, X, Z, mag, sep, inside


def stations():
    """Candidate stations: straight below the pole and the minimum-demand point with
    elevation >= 45 deg and altitude <= 100,000 km (all Moon-centred, km)."""
    x, z, X, Z, mag, sep, inside = maps()
    el = elevation_from_south_pole(X, Z)
    ok = (el >= 45) & (np.hypot(X, Z) <= 100e3) & ~inside
    out = {"below pole 60,000 km": (0.0, -60e3), "below pole 100,000 km": (0.0, -100e3)}
    for ac in (0.0, D["CR-S"].a_c_mm):
        k = np.argmin(np.where(ok, sep[ac], np.inf))
        out[f"min-demand (el>=45, a_c={ac:.2f})"] = (float(X.flat[k]), float(Z.flat[k]))
    return out, (x, z, X, Z, mag, sep, inside)


def station_budget(xz, years=(1, 2, 3, 5), payload_dry=100.0, isps=(1500.0, 3000.0)):
    areq = a_req_mm(np.array([xz[0]]), np.array([xz[1]]))[0]
    out = {"a_req_mm_s2": float(np.linalg.norm(areq)), "by_ac": {}}
    for ac in AC_SET:
        r = residual_sep(areq[None, :], ac, n_sun=72)[0]
        mean = float(r.mean()); peak = float(r.max())
        dv_yr = mean * 1e-3 * YEAR_S / 1e3              # km/s per year
        row = {"mean_sep_mm_s2": mean, "peak_sep_mm_s2": peak, "dv_km_s_per_yr": dv_yr,
               "frac_month_sail_alone_ok": float(np.mean(r < 0.05 * np.linalg.norm(areq)))}
        for isp in isps:
            ve = isp * G0 / 1e3
            row[f"prop_frac_1yr_isp{int(isp)}"] = 1 - math.exp(-dv_yr / ve)
            row[f"years_with_30pct_prop_isp{int(isp)}"] = -ve * math.log(0.7) / dv_yr if dv_yr > 0 else None
        out["by_ac"][f"{ac:.3f}"] = row
    return out


def sun_phase_curve(xz):
    areq = a_req_mm(np.array([xz[0]]), np.array([xz[1]]))[0]
    th = np.linspace(0, 360, 72, endpoint=False)
    return th, {ac: residual_sep(areq[None, :], ac, n_sun=72)[0] for ac in AC_SET}


def fig_requirement(x, z, X, Z, mag, inside, st, path):
    f, ax = P.fig(size=(10, 6.2))
    m = np.where(inside, np.nan, mag)
    levels = [0.3, 0.58, 1.0, 1.7, 2.5, 4.0, 8.0]
    cf = ax.contourf(X / 1e3, Z / 1e3, np.log10(m), levels=np.log10([0.2] + levels + [50]), cmap=P.CMAP_SEQ_R, alpha=0.9)
    cs = ax.contour(X / 1e3, Z / 1e3, m, levels=levels, colors=P.INK2, linewidths=0.8)
    ax.clabel(cs, fmt=lambda v: f"{v:g}", fontsize=9.5)
    el = elevation_from_south_pole(X, Z)
    ce = ax.contour(X / 1e3, Z / 1e3, el, levels=[15, 30, 45, 60, 75], colors=P.ORANGE, linewidths=1.0)
    ax.clabel(ce, fmt=lambda v: f"{v:.0f} deg", fontsize=9)
    ax.add_patch(__import__("matplotlib").patches.Circle((0, 0), R_MOON / 1e3, color=P.MUTED))
    Lp = CR.lagrange_points()
    for k in ("L1", "L2"):
        xx = (Lp[k][0] - (1 - MU)) * L_EM_KM / 1e3
        ax.plot(xx, 0, "+", color=P.INK, ms=10, mew=1.5); ax.text(xx, -6, k, ha="center", va="top", color=P.INK)
    for i, (k, (sx, sz)) in enumerate(st.items()):
        if k.startswith("min-demand") and "0.00" in k:
            continue
        ax.plot(sx / 1e3, sz / 1e3, "o", color=[P.AQUA, P.VIOLET, P.RED, P.YELLOW][i % 4], ms=9, mec=P.SURFACE, mew=2, label=k)
    ax.set_aspect("equal")
    ax.set_xlabel("x from Moon, away from Earth (1000 km)"); ax.set_ylabel("z (1000 km), south < 0")
    ax.legend(loc="lower left", fontsize=9.5)
    cb = f.colorbar(cf, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("|a_required| (mm/s^2), log scale")
    cb.set_ticks(np.log10([0.3, 0.58, 1, 1.7, 2.5, 4, 8])); cb.set_ticklabels(["0.3", "0.58", "1", "1.7", "2.5", "4", "8"])
    ax.text(0.99, 0.02, "orange: elevation of the spacecraft seen from the south pole", transform=ax.transAxes,
            ha="right", fontsize=9.5, color=P.INK2)
    P.title(ax, "Acceleration needed to hover below the lunar south pole")
    return P.save(f, path)


def fig_sep(x, z, X, Z, sep, inside, path):
    f, axs = P.fig(1, 2, size=(12, 5.4), sharey=True)
    base = np.where(inside, np.nan, sep[0.0])
    for ax, ac in zip(axs, (D["CR-S"].a_c_mm, 1.7)):
        red = 100 * (1 - np.where(inside, np.nan, sep[ac]) / base)
        cf = ax.contourf(X / 1e3, Z / 1e3, red, levels=np.arange(0, 101, 10), cmap=P.CMAP_SEQ)
        cs = ax.contour(X / 1e3, Z / 1e3, red, levels=[5, 10, 25, 50, 75], colors=P.INK2, linewidths=0.7)
        ax.clabel(cs, fmt=lambda v: f"{v:.0f}%", fontsize=9)
        ax.add_patch(__import__("matplotlib").patches.Circle((0, 0), R_MOON / 1e3, color=P.MUTED))
        ax.set_aspect("equal"); ax.set_xlabel("x from Moon (1000 km)")
        P.title(ax, f"Sail a_c = {ac:.2f} mm/s^2")
    axs[0].set_ylabel("z (1000 km)")
    cb = f.colorbar(cf, ax=axs, shrink=0.85, pad=0.02); cb.set_label("SEP propellant saved by the sail (%)")
    f.suptitle("Hybrid pole-sitter: share of the SEP demand removed by the sail (month-averaged)",
               x=0.01, ha="left", fontsize=14, fontweight="semibold")
    return P.save(f, path)


def fig_phase(th, curves, areq_mag, path, label):
    f, ax = P.fig(size=(10, 5.0))
    cols = [P.MUTED, P.BLUE, P.AQUA, P.ORANGE, P.VIOLET]
    for (ac, r), c in zip(curves.items(), cols):
        lab = "pure SEP (no sail)" if ac == 0 else f"sail a_c = {ac:.2f} mm/s^2"
        ax.plot(th, r, color=c, label=lab)
    ax.set_xlim(0, 360); ax.set_xticks(range(0, 361, 45))
    ax.set_ylim(0, areq_mag * 1.1)
    ax.set_xlabel("Sun phase in the Earth-Moon rotating frame (deg; 0 = Sun beyond the Moon)")
    ax.set_ylabel("SEP acceleration still needed (mm/s^2)")
    ax.legend(loc="lower left", fontsize=10, ncol=2)
    P.title(ax, f"Residual SEP demand over one synodic month: {label}")
    return P.save(f, path)


def fig_mass(budget, path, label, payload_dry=100.0, isp=3000.0):
    f, ax = P.fig(size=(10, 5.0))
    yrs = np.linspace(0.1, 5, 60)
    cols = [P.MUTED, P.BLUE, P.AQUA, P.ORANGE, P.VIOLET]
    ve = isp * G0 / 1e3
    for (k, row), c in zip(budget["by_ac"].items(), cols):
        ac = float(k)
        dv = row["dv_km_s_per_yr"] * yrs
        # sail adds mass: area = a_c * m / (P * eff) ... use sail loading 10 g/m^2 incl. booms for the sail system
        m0 = payload_dry * np.exp(dv / ve) / (1 - 0.1 * (np.exp(dv / ve) - 1))
        m0 = np.where(m0 > 0, m0, np.nan)
        lab = "pure SEP" if ac == 0 else f"hybrid, sail a_c = {ac:.2f} mm/s^2"
        ax.semilogy(yrs, m0, color=c, label=lab)
    ax.set_xlabel("pole-sitting duration (years)"); ax.set_ylabel("initial mass for 100 kg dry (kg)")
    ax.set_ylim(80, 3000)
    ax.legend(loc="upper left", fontsize=10)
    P.title(ax, f"Propellant cost of pole-sitting at {label} (Isp {isp:.0f} s, 10 % tankage)")
    return P.save(f, path)


def run():
    with Timer("Q4 pole-sitter"):
        st, (x, z, X, Z, mag, sep, inside) = stations()
        budgets = {k: station_budget(v) for k, v in st.items()}
        main = "below pole 60,000 km"
        th, curves = sun_phase_curve(st[main])
        figs = [fig_requirement(x, z, X, Z, mag, inside, st, "q4_hover_requirement.png"),
                fig_sep(x, z, X, Z, sep, inside, "q4_sail_savings_map.png"),
                fig_phase(th, curves, budgets[main]["a_req_mm_s2"], "q4_sun_phase.png", "60,000 km below the south pole"),
                fig_mass(budgets[main], "q4_mass_vs_duration.png", "60,000 km below the pole")]
        res = {"stations_km": st, "budgets": budgets,
               "literature": {"Ozimek_2009_kappa_mm_s2": {"low-elevation (4-7 deg) periodic coverage near L1/L2": 0.58,
                                                          "high elevation / hover-like periodic orbits": 1.7},
                              "Wawrzyniak_Howell_2009": "a0 >= 1.5 mm/s^2 for 15 deg elevation constraint",
                              "Grebow_2010_SEP": "500 kg wet, 150 mN NSTAR-class: 387-554 days of pole-sitting"},
               "figures": [p.split("/")[-1] for p in figs]}
        save_results("q4_pole_sitter", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({"stations": r["stations_km"], "budgets": r["budgets"]}, indent=1)[:6000])
