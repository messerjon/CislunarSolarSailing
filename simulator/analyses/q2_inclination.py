"""Q2 - Optimal launch inclination for reaching cislunar space with a sail.

Three effects: (1) the lunar orbit plane is inclined 18.3-28.6 deg to the
equator over the 18.6-yr nodal cycle; (2) sail orbit-raising effectiveness
depends on the Sun's elevation above the orbit plane (beta) and on eclipses;
(3) any plane mismatch must be removed by the sail, cheapest near apogee.
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import earth_orbit as EO, sail as S, plotting as P
from cislunar_sail.constants import MU_EARTH, R_EARTH, DAY_S
from cislunar_sail.environment import jd_from_iso, moon_orbit_inclination_to_equator_deg
from cislunar_sail.designs import STUDY

D = {d.key: d for d in STUDY}
SITES = {"Kourou": 5.2, "Cape Canaveral / KSC": 28.5, "Tanegashima": 30.4, "Wallops": 37.8,
         "Mahia (Rocket Lab)": 39.3, "Vandenberg SSO": 97.6}
INCS = [0.0, 10.0, 18.3, 23.4, 28.5, 35.0, 45.0, 51.6, 63.4, 90.0, 97.6]


def lunar_cycle():
    years = np.linspace(2024, 2046, 600)
    jd = 2451545.0 + (years - 2000.0) * 365.25
    return years, moon_orbit_inclination_to_equator_deg(jd)


def beta_efficiency(alts=(1000.0, 20000.0, 35786.0)):
    th, al, g = S.steering_table(S.AL_CP1.front)
    betas = np.linspace(0, 90, 91)
    u = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    out = {}
    for h in alts:
        r = R_EARTH + h
        eff, ecl = [], []
        for b in np.radians(betas):
            usun = np.array([math.cos(b), 0.0, math.sin(b)])
            pos = np.stack([np.cos(u), np.sin(u), 0 * u], 1) * r
            vel = np.stack([-np.sin(u), np.cos(u), 0 * u], 1)
            proj = pos @ usun
            perp = np.linalg.norm(pos - proj[:, None] * usun, axis=1)
            lit = ~((proj < 0) & (perp < R_EARTH))
            cth = vel @ (-usun)
            gg = np.interp(np.arccos(np.clip(cth, -1, 1)), th, g)
            eff.append(float(np.mean(gg * lit))); ecl.append(float(1 - np.mean(lit)))
        out[f"{h:.0f}"] = {"beta_deg": betas.tolist(), "useful_fraction": eff, "eclipse_fraction": ecl}
    return out


def raise_time_vs_inclination():
    rp, ra = R_EARTH + 1000.0, R_EARTH + 35786.0
    a = (rp + ra) / 2; e = (ra - rp) / (ra + rp)
    jd0 = jd_from_iso("2028-01-01T00:00:00")
    seasons = 6
    y, jd = [], []
    for inc in INCS:
        for k in range(seasons):
            y.append(EO.initial_state(a, e, inc, 0.0, 180.0, m0=111.0)[0]); jd.append(jd0 + k * 365.25 / seasons)
    craft = EO.Craft(a_c=D["CR-S"].a_c_mm * 1e-3, m0=111.0, material=S.AL_CP1)
    r = EO.propagate_averaged(np.array(y), np.array(jd), craft, t_max_days=3000, dt_days=1.0, objective="apogee",
                              ra_target=326_000.0, K=64, rp_safe=R_EARTH + 900.0, record_every=1000)
    t = r["t_days"].reshape(len(INCS), seasons)
    yf = r["y_final"].reshape(len(INCS), seasons, 6)
    inc_f = np.degrees(2 * np.arctan(np.hypot(yf[..., 3], yf[..., 4])))
    return t, inc_f


def plane_change_rate():
    """Days per degree of inclination change on the arrival orbit (r_p 7,378 km, r_a 326,000 km)."""
    rp, ra = R_EARTH + 1000.0, 326_000.0
    a = (rp + ra) / 2; e = (ra - rp) / (ra + rp)
    jd0 = jd_from_iso("2030-01-01T00:00:00")
    seasons = 6
    dis = [5.0, 10.0, 20.0]
    y, jd, tg = [], [], []
    for di in dis:
        for k in range(seasons):
            for argp in (0.0, 90.0):        # apsides aligned with / perpendicular to the node line
                y.append(EO.initial_state(a, e, 28.5, 0.0, argp, m0=111.0)[0]); jd.append(jd0 + k * 365.25 / seasons)
                tg.append(math.radians(28.5 - di))
    craft = EO.Craft(a_c=D["CR-S"].a_c_mm * 1e-3, m0=111.0, material=S.AL_CP1)
    r = EO.propagate_averaged(np.array(y), np.array(jd), craft, t_max_days=1500, dt_days=0.5,
                              objective="inclination", inc_target=np.array(tg), inc_tol_deg=0.2,
                              ra_target=1e12, K=96, record_every=1000, rp_decay=R_EARTH + 200.0)
    t = r["t_days"].reshape(len(dis), seasons, 2)
    per_deg = {f"{di:g}": {"aligned": float(np.nanmedian(t[i, :, 0]) / di), "perpendicular": float(np.nanmedian(t[i, :, 1]) / di),
                           "median_days": float(np.nanmedian(t[i]))} for i, di in enumerate(dis)}
    return per_deg


def figures(years, inc_moon, beff, t_raise, per_deg, i_arrival, inc_final):
    figs = []
    f, ax = P.fig(size=(10, 4.8))
    ax.plot(years, inc_moon, color=P.BLUE)
    ax.text(2031.0, 14.0, "lunar orbit plane vs Earth's equator", color=P.INK2, fontsize=10, ha="center")
    for (k, v), c in zip(list(SITES.items())[:5], [P.MUTED, P.ORANGE, P.AQUA, P.YELLOW, P.VIOLET]):
        ax.axhline(v, color=c, lw=1.2)
        ax.text(2045.9, v, k, ha="right", va="bottom", fontsize=9.5, color=P.INK2)
    ax.axvspan(2028, 2031, color=P.AQUA, alpha=0.08, lw=0)
    ax.text(2029.5, 4, "Cattle Run\ndemo -> cislunar", ha="center", fontsize=9.5, color=P.INK2)
    ax.set_xlim(2024, 2046); ax.set_ylim(0, 42)
    ax.set_xlabel("year"); ax.set_ylabel("inclination (deg)")
    P.title(ax, "The Moon's orbit plane swings between 18.3 and 28.6 deg (18.6-yr cycle)")
    figs.append(P.save(f, "q2_lunar_plane_cycle.png"))

    f, ax = P.fig(size=(10, 4.8))
    for (h, d), c in zip(beff.items(), [P.BLUE, P.ORANGE, P.AQUA]):
        lab = {"1000": "LEO 1,000 km", "20000": "MEO 20,000 km", "35786": "GEO"}[h]
        ax.plot(d["beta_deg"], d["useful_fraction"], color=c, label=f"{lab}")
    ax.set_xlabel("Sun elevation above orbit plane, beta (deg)")
    ax.set_ylabel("orbit-averaged useful fraction of a_c")
    ax.set_xlim(0, 90); ax.set_ylim(0, 0.45)
    ax.legend(loc="lower right", fontsize=10)
    ax.text(2, 0.04, "beta = 0: Sun in the orbit plane, longest eclipses;  beta = 90: dawn-dusk geometry, no eclipse",
            fontsize=9.5, color=P.INK2)
    P.title(ax, "Sail orbit-raising effectiveness vs Sun geometry (Al/CP1, energy-raising law)")
    figs.append(P.save(f, "q2_beta_efficiency.png"))

    f, ax = P.fig(size=(10, 5.2))
    med = np.nanmedian(t_raise, axis=1)
    dpd = np.mean([v["median_days"] / float(k) for k, v in per_deg.items()])
    plane = np.abs(inc_final - i_arrival) * dpd
    ax.plot(INCS, med, "-o", color=P.BLUE, label="spiral to lunar-distance apogee (raised GTO start)", mec=P.SURFACE, mew=1.5)
    ax.plot(INCS, plane, "-o", color=P.ORANGE, label=f"residual plane change to lunar plane (~{dpd:.1f} d/deg near apogee)", mec=P.SURFACE, mew=1.5)
    tot = med + plane
    ax.plot(INCS, tot, "-o", color=P.INK, label="total", mec=P.SURFACE, mew=1.5)
    k = int(np.nanargmin(tot))
    ax.annotate(f"minimum at {INCS[k]:.1f} deg launch\n({tot[k]:.0f} d)", (INCS[k], tot[k]), xytext=(INCS[k] + 14, tot[k] - 160),
                arrowprops=dict(arrowstyle="-", color=P.INK2), fontsize=10, color=P.INK)
    ax.axvline(i_arrival, color=P.AXIS, lw=1)
    ax.text(i_arrival + 1, ax.get_ylim()[1] * 0.02 if False else 30, f"lunar plane at arrival ~{i_arrival:.1f} deg",
            fontsize=9.5, color=P.INK2, rotation=90, va="bottom")
    ax.set_xlabel("launch (initial) inclination (deg)"); ax.set_ylabel("days (CR-S, a_c = 0.123 mm/s^2)")
    ax.set_xlim(-2, 100); ax.set_ylim(0, 1050)
    ax.legend(loc="center left", bbox_to_anchor=(0.30, 0.42), fontsize=10)
    P.title(ax, "Transit time vs launch inclination")
    figs.append(P.save(f, "q2_time_vs_inclination.png"))
    return figs


def run():
    with Timer("Q2 inclination"):
        years, incm = lunar_cycle()
        beff = beta_efficiency()
        t_raise, inc_f = raise_time_vs_inclination()
        per_deg = plane_change_rate()
        med = np.nanmedian(t_raise, axis=1)
        arrival_year = 2028.0 + float(np.nanmedian(med)) / 365.25
        i_arr = float(moon_orbit_inclination_to_equator_deg(2451545.0 + (arrival_year - 2000) * 365.25))
        incf_med = np.nanmedian(inc_f, 1)
        figs = figures(years, incm, beff, t_raise, per_deg, i_arr, incf_med)
        dpd = float(np.mean([v["median_days"] / float(k) for k, v in per_deg.items()]))
        tot = med + np.abs(incf_med - i_arr) * dpd
        res = {"inclinations": INCS, "raise_days_median": med.tolist(),
               "raise_days_min": np.nanmin(t_raise, 1).tolist(), "raise_days_max": np.nanmax(t_raise, 1).tolist(),
               "final_inclination_deg_median": np.nanmedian(inc_f, 1).tolist(),
               "plane_change": per_deg, "days_per_degree": dpd, "arrival_year": arrival_year,
               "lunar_plane_inclination_at_arrival_deg": i_arr, "total_days": tot.tolist(),
               "optimal_inclination_deg": INCS[int(np.nanargmin(tot))],
               "lunar_inclination_2028": float(moon_orbit_inclination_to_equator_deg(jd_from_iso("2028-01-01T00:00:00"))),
               "lunar_inclination_2030": float(moon_orbit_inclination_to_equator_deg(jd_from_iso("2030-01-01T00:00:00"))),
               "lunar_inclination_2034": float(moon_orbit_inclination_to_equator_deg(jd_from_iso("2034-06-01T00:00:00"))),
               "beta_efficiency": {k: {"beta0": v["useful_fraction"][0], "beta45": v["useful_fraction"][45],
                                       "beta90": v["useful_fraction"][90], "eclipse_beta0": v["eclipse_fraction"][0]}
                                   for k, v in beff.items()},
               "sites_deg": SITES, "figures": [p.split("/")[-1] for p in figs]}
        save_results("q2_inclination", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k not in ("figures",)}, indent=1))
