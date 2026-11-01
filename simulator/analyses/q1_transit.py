"""Q1 - How quickly can a sail (or hybrid) transit from LEO, GTO, GEO and TLI to cislunar space?

Arrival is defined as an osculating apogee of 326 000 km (Earth-Moon L1
distance); the L1 'energy gateway' (Jacobi C = C_L1) is crossed earlier at
r_a ~ 260 000 km.  Locally optimal apogee-raising steering with perigee
protection, eclipses, J2 and (where relevant) NRLMSIS drag.  Results are
medians over six launch seasons (Sun geometry).
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import earth_orbit as EO, sail as S, plotting as P
from cislunar_sail.constants import MU_EARTH, R_EARTH, DAY_S, D_EARTH_MOON
from cislunar_sail.environment import jd_from_iso, moon_state_eci
from cislunar_sail.designs import HERITAGE, STUDY

D = {d.key: d for d in HERITAGE + STUDY}
AC_LIST = [0.03, 0.045, 0.07, 0.1, 0.123, 0.15, 0.2, 0.3, 0.5, 1.0]   # mm/s^2
SEASONS = 6
EPOCH = "2028-01-01T00:00:00"
RA_TARGET = 326_000.0

ORBITS = {
    "LEO 1,000 km (28.5 deg)": dict(rp=R_EARTH + 1000, ra=R_EARTH + 1000, inc=28.5, rp_safe=R_EARTH + 900),
    "GTO, perigee raised to 1,000 km": dict(rp=R_EARTH + 1000, ra=R_EARTH + 35786, inc=27.0, rp_safe=R_EARTH + 900),
    "GEO (35,786 km)": dict(rp=R_EARTH + 35786, ra=R_EARTH + 35786, inc=0.0, rp_safe=R_EARTH + 20000),
}
GTO_STD = dict(rp=R_EARTH + 250, ra=R_EARTH + 35786, inc=27.0)


def _states(orb, n_each, m0=100.0):
    a = (orb["rp"] + orb["ra"]) / 2; e = (orb["ra"] - orb["rp"]) / (orb["ra"] + orb["rp"])
    jd0 = jd_from_iso(EPOCH)
    y, jd = [], []
    for k in range(SEASONS):
        st = EO.initial_state(a, max(e, 1e-4), orb["inc"], 0.0, 180.0, m0=m0)[0]
        for _ in range(n_each):
            y.append(st); jd.append(jd0 + k * 365.25 / SEASONS)
    return np.array(y), np.array(jd)


def sweep_sail(orb):
    y, jd = _states(orb, len(AC_LIST))
    acs = np.tile(np.array(AC_LIST) * 1e-3, SEASONS)
    craft = EO.Craft(a_c=acs, m0=100.0, material=S.AL_CP1)
    r = EO.propagate_averaged(y, jd, craft, t_max_days=3650, dt_days=1.0, objective="apogee",
                              ra_target=RA_TARGET, K=64, rp_safe=orb["rp_safe"], record_every=5)
    t = r["t_days"].reshape(SEASONS, len(AC_LIST))
    return t, r


def sweep_hybrid(orb):
    """CR-H as designed (6 kg propellant) and with unlimited propellant."""
    d = D["CR-H"]
    y, jd = _states(orb, 2, m0=d.mass_kg)
    m_dry = np.tile([d.mass_kg - d.propellant_kg, 1.0], SEASONS)
    craft = EO.Craft(a_c=d.a_c_mm * 1e-3, m0=d.mass_kg, material=d.material,
                     sep_thrust=d.sep_thrust_mN * 1e-3, isp=d.isp_s, gimbal_deg=d.gimbal_deg, m_dry=m_dry)
    r = EO.propagate_averaged(y, jd, craft, t_max_days=3650, dt_days=1.0, objective="apogee",
                              ra_target=RA_TARGET, K=64, rp_safe=orb["rp_safe"], record_every=5)
    t = r["t_days"].reshape(SEASONS, 2)
    prop = (d.mass_kg - r["y_final"][:, 5]).reshape(SEASONS, 2)
    return t, prop


def gto_standard_fate():
    """Sail deployed directly in a standard GTO (250 km perigee): drag at perigee."""
    acs = np.array([0.045, 0.123, 0.3, 1.0]) * 1e-3
    orb = GTO_STD
    a = (orb["rp"] + orb["ra"]) / 2; e = (orb["ra"] - orb["rp"]) / (orb["ra"] + orb["rp"])
    y = np.array([EO.initial_state(a, e, orb["inc"], 0.0, 180.0, m0=100.0)[0]] * len(acs))
    jd = np.full(len(acs), jd_from_iso(EPOCH))
    out = {}
    for lab, f107 in (("moderate", 150.0), ("high", 230.0)):
        craft = EO.Craft(a_c=acs, m0=100.0, material=S.AL_CP1, cd=2.2, min_area_frac=0.01)
        r = EO.propagate_averaged(y, jd, craft, t_max_days=120, dt_days=0.1, objective="apogee",
                                  ra_target=1e12, K=96, rp_safe=R_EARTH + 800, f107=f107, record_every=10,
                                  rp_decay=R_EARTH + 150.0)
        yf = r["y_final"]; ef = np.hypot(yf[:, 1], yf[:, 2])
        out[lab] = {"a_c_mm": (acs * 1e3).tolist(), "status": r["status"].tolist(),
                    "rp_final_km": (yf[:, 0] / (1 + ef) - R_EARTH).tolist(),
                    "ra_final_km": (yf[:, 0] / (1 - ef) - R_EARTH).tolist()}
    # perigee-raise delta-v needed at apogee (250 -> 1000 km)
    ra = R_EARTH + 35786
    def v_ap(rp):
        return math.sqrt(MU_EARTH * (2 / ra - 2 / (ra + rp)))
    dv = (v_ap(R_EARTH + 1000) - v_ap(R_EARTH + 250)) * 1e3
    out["perigee_raise_dv_m_s"] = dv
    return out


def validate_cowell():
    """Averaged (no third body) vs Cowell (Sun+Moon, J2) for 60 days from raised GTO, a_c=0.5 mm/s^2."""
    orb = ORBITS["GTO, perigee raised to 1,000 km"]
    a = (orb["rp"] + orb["ra"]) / 2; e = (orb["ra"] - orb["rp"]) / (orb["ra"] + orb["rp"])
    jd0 = jd_from_iso(EPOCH)
    craft = EO.Craft(a_c=0.5e-3, m0=100.0, material=S.AL_CP1)
    y0 = EO.initial_state(a, e, orb["inc"], 0.0, 180.0, m0=100.0)
    ra_avg = EO.propagate_averaged(y0, [jd0], craft, t_max_days=60, dt_days=0.5, objective="apogee",
                                   ra_target=1e12, K=96, rp_safe=orb["rp_safe"], record_every=4)
    ya = ra_avg["hist_y"][:, 0, :]; ea = np.hypot(ya[:, 1], ya[:, 2])
    ra_a = ya[:, 0] / (1 - ea)
    # Cowell initial state at perigee
    p, f, g, h, k, L = EO.coe_to_mee(a, e, math.radians(orb["inc"]), 0.0, math.pi, 0.0)
    from cislunar_sail.backend import get_backend
    B = get_backend("numpy")
    r0, v0, *_ = EO.mee_to_rv(B, np.array(p), np.array(f), np.array(g), np.array(h), np.array(k), np.array(L))
    sol = EO.propagate_cowell(np.asarray(r0), np.asarray(v0), jd0, craft, 60.0, objective="apogee",
                              third_body=True, max_step_s=900.0, rtol=1e-8, rp_safe=orb["rp_safe"])
    rr, vv = sol.y[:3].T, sol.y[3:6].T
    a_c, e_c, i_c = EO.rv_to_coe(rr, vv)
    ra_c = a_c * (1 + e_c)
    tc = sol.t / DAY_S
    # compare at 15-day marks
    marks = [15, 30, 45, 60]
    cmp = []
    for mk in marks:
        ia = np.argmin(abs(ra_avg["hist_t"] - mk))
        sel = (tc > mk - 1.0) & (tc <= mk)
        cmp.append({"day": mk, "ra_avg_km": float(ra_a[ia]), "ra_cowell_km": float(np.max(ra_c[sel])) if sel.any() else None})
    return {"compare": cmp, "t_cowell": tc[::50].tolist(), "ra_cowell": ra_c[::50].tolist(),
            "t_avg": ra_avg["hist_t"].tolist(), "ra_avg": ra_a.tolist()}


def fig_transit(results, hyb, path):
    f, ax = P.fig(size=(10, 5.6))
    cols = [P.BLUE, P.ORANGE, P.AQUA]
    acs = np.array(AC_LIST)
    for (name, t), c in zip(results.items(), cols):
        med = np.nanmedian(t, axis=0)
        lo, hi = np.nanmin(t, axis=0), np.nanmax(t, axis=0)
        ax.fill_between(acs, lo, hi, color=c, alpha=0.12, lw=0)
        ax.loglog(acs, med, "-o", color=c, label=f"{name} (sail only)", mec=P.SURFACE, mew=1.5)
        th = np.nanmedian(hyb[name][0][:, 0])
        ax.plot(D["CR-H"].a_c_mm, th, "D", color=c, ms=9, mec=P.INK, mew=0.8)
    ax.plot([], [], "D", color=P.MUTED, mec=P.INK, mew=0.8, ms=8, label="CR-H hybrid (sail 0.104 + SEP 0.153 mm/s^2)")
    for key, lab in (("ACS3", "ACS3"), ("NEAS", "NEA Scout"), ("CR-S", "CR-S"), ("CR-A", "CR-A advanced")):
        x = D[key].a_c_mm
        ax.axvline(x, color=P.GRID, lw=1.2, zorder=0)
        ax.text(x * 1.03, 5000, lab, rotation=90, va="top", ha="left", fontsize=9.5, color=P.INK2)
    for yv, lab in ((365, "1 yr"), (730, "2 yr"), (1825, "5 yr")):
        ax.axhline(yv, color=P.AXIS, lw=0.9)
        ax.text(1.02, yv, lab, color=P.INK2, fontsize=9.5, va="center", transform=ax.get_yaxis_transform())
    ax.set_xlim(0.028, 1.1); ax.set_ylim(40, 5000)
    ax.set_xlabel("sail characteristic acceleration a_c (mm/s^2)")
    ax.set_ylabel("days to reach lunar-distance apogee")
    ax.legend(loc="lower left", fontsize=9.5)
    P.title(ax, "Transit time to cislunar space scales as 1 / a_c",
            "median over six launch seasons; band = seasonal spread; arrival = apogee at 326,000 km (L1 distance)")
    return P.save(f, path)


def fig_spiral(path):
    """3-D view of a CR-S spiral from raised GTO: osculating ellipses coloured by time."""
    orb = ORBITS["GTO, perigee raised to 1,000 km"]
    a = (orb["rp"] + orb["ra"]) / 2; e = (orb["ra"] - orb["rp"]) / (orb["ra"] + orb["rp"])
    jd0 = jd_from_iso(EPOCH)
    craft = EO.Craft(a_c=D["CR-S"].a_c_mm * 1e-3, m0=111.0, material=S.AL_CP1)
    y0 = EO.initial_state(a, e, orb["inc"], 0.0, 180.0, m0=111.0)
    r = EO.propagate_averaged(y0, [jd0], craft, t_max_days=2000, dt_days=1.0, objective="apogee",
                              ra_target=RA_TARGET, K=64, rp_safe=orb["rp_safe"], record_every=1)
    from cislunar_sail.backend import get_backend
    B = get_backend("numpy")
    H = r["hist_y"][:, 0, :]; T = r["hist_t"]
    f, ax = P.fig3d(size=(10, 6.4))
    idx = np.linspace(0, len(T) - 1, 26).astype(int)
    cmap = P.CMAP_SEQ
    Ls = np.linspace(0, 2 * np.pi, 361)
    allx = []
    for j, i in enumerate(idx):
        p, fq, g, h, k = H[i, :5]
        rv, *_ = EO.mee_to_rv(B, p + 0 * Ls, fq + 0 * Ls, g + 0 * Ls, h + 0 * Ls, k + 0 * Ls, Ls)
        rv = np.asarray(rv) / 1e3
        last = j == len(idx) - 1
        ax.plot(rv[:, 0], rv[:, 1], rv[:, 2], color=P.ORANGE if last else cmap(0.25 + 0.75 * j / len(idx)),
                lw=2.0 if last else 1.1)
        allx.append(rv)
    ax.text(rv[0, 0], rv[0, 1], rv[0, 2] + 20, "arrival orbit", color=P.INK2)
    rm, _ = moon_state_eci(jd0 + np.linspace(0, 27.3, 200))
    rm = rm / 1e3
    ax.plot(rm[:, 0], rm[:, 1], rm[:, 2], color=P.MUTED, lw=1.5)
    ax.text(rm[50, 0], rm[50, 1], rm[50, 2] + 30, "Moon's orbit", color=P.INK2)
    ax.scatter([0], [0], [0], color=P.BLUE, s=40)
    allx = np.vstack(allx + [rm])
    P.set_equal_3d(ax, allx[:, 0], allx[:, 1], allx[:, 2])
    ax.set_xlabel("x (1000 km)"); ax.set_ylabel("y (1000 km)"); ax.set_zlabel("z (1000 km)")
    ax.view_init(elev=62, azim=-70)
    ax.set_title(f"CR-S sail spiral from raised GTO to lunar distance: {T[-1]:.0f} days "
                 "(osculating orbits, light = early, dark = late)", loc="left", fontsize=12.5)
    return P.save(f, path), float(T[-1])


def fig_validation(val, path):
    f, ax = P.fig(size=(10, 4.8))
    ax.plot(val["t_cowell"], np.array(val["ra_cowell"]) / 1e3, color=P.ORANGE, lw=1.4,
            label="Cowell: J2 + Sun + Moon gravity (osculating apogee)")
    ax.plot(val["t_avg"], np.array(val["ra_avg"]) / 1e3, color=P.BLUE, label="Orbit-averaged model (J2 only)")
    ax.set_xlabel("days"); ax.set_ylabel("apogee radius (1000 km)")
    ax.legend(loc="upper left", fontsize=10)
    P.title(ax, "Model check: averaged vs Cowell propagation (raised GTO, a_c = 0.5 mm/s^2)")
    return P.save(f, path)


def run():
    with Timer("Q1 transit"):
        results, raw_hyb = {}, {}
        for name, orb in ORBITS.items():
            t, _ = sweep_sail(orb)
            results[name] = t
            raw_hyb[name] = sweep_hybrid(orb)
        gto = gto_standard_fate()
        val = validate_cowell()
        figs = [fig_transit(results, raw_hyb, "q1_transit_vs_ac.png")]
        p3, t_cr = fig_spiral("q1_spiral_3d.png")
        figs.append(p3)
        figs.append(fig_validation(val, "q1_model_validation.png"))
        table = {}
        for name, t in results.items():
            med = np.nanmedian(t, axis=0)
            table[name] = {f"{ac:g}": float(m) if np.isfinite(m) else None for ac, m in zip(AC_LIST, med)}
            th, prop = raw_hyb[name]
            table[name]["CR-H (6 kg prop)"] = float(np.nanmedian(th[:, 0]))
            table[name]["CR-H prop used kg"] = float(np.nanmedian(prop[:, 0]))
            table[name]["CR-H unlimited prop"] = float(np.nanmedian(th[:, 1]))
            table[name]["CR-H unlimited prop used kg"] = float(np.nanmedian(prop[:, 1]))
            table[name]["seasonal_min"] = {f"{ac:g}": float(np.nanmin(t[:, j])) for j, ac in enumerate(AC_LIST)}
            table[name]["seasonal_max"] = {f"{ac:g}": float(np.nanmax(t[:, j])) for j, ac in enumerate(AC_LIST)}
        # TLI: ballistic time from 300 km perigee to 326 000 km on a lunar-distance ellipse
        rp, ra = R_EARTH + 300, 384_400.0
        a = (rp + ra) / 2; e = (ra - rp) / (ra + rp)
        r_t = 326_000.0
        nu = math.acos((a * (1 - e * e) / r_t - 1) / e)
        E = 2 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu / 2))
        M = E - e * math.sin(E)
        t_tli = M / math.sqrt(MU_EARTH / a ** 3) / DAY_S
        res = {"definition": "days to osculating apogee >= 326,000 km; median of 6 launch seasons",
               "a_c_list_mm_s2": AC_LIST, "transit_days": table, "gto_standard": gto,
               "tli_ballistic_days_to_326000km": t_tli, "cowell_validation": val["compare"],
               "crs_spiral_days_from_raised_gto": t_cr, "figures": [p.split("/")[-1] for p in figs]}
        save_results("q1_transit", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: r[k] for k in ("transit_days", "gto_standard", "tli_ballistic_days_to_326000km", "cowell_validation", "crs_spiral_days_from_raised_gto")}, indent=1))


def figures_from_json():
    """Redraw Q1 figures from results/q1_transit.json (no re-simulation)."""
    import json, os
    from .common import RES_DIR
    d = json.load(open(os.path.join(RES_DIR, "q1_transit.json")))
    results, hyb = {}, {}
    for name in ORBITS:
        row = d["transit_days"][name]
        med = np.array([row[f"{a:g}"] if row[f"{a:g}"] is not None else np.nan for a in AC_LIST], float)
        lo = np.array([row["seasonal_min"][f"{a:g}"] if row["seasonal_min"][f"{a:g}"] is not None else np.nan for a in AC_LIST], float)
        hi = np.array([row["seasonal_max"][f"{a:g}"] if row["seasonal_max"][f"{a:g}"] is not None else np.nan for a in AC_LIST], float)
        results[name] = np.vstack([lo, med, hi])
        hyb[name] = (np.array([[row["CR-H (6 kg prop)"], row["CR-H unlimited prop"]]]), None)
    fig_transit(results, hyb, "q1_transit_vs_ac.png")
    return fig_spiral("q1_spiral_3d.png")
