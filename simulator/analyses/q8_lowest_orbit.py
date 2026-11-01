"""Q8 - Lowest acceptable orbit for the below-GEO Cattle Run demonstrator.

Criteria evaluated vs altitude and solar activity:
 1. drag vs SRP (Mengali-Quarta f = rho v^2 / P_ideal <= 2/C_D) and simulated
    net semi-major-axis (SMA) raising rate with drag-aware locally optimal steering;
 2. gravity-gradient torque vs SRP-based attitude-control authority;
 3. environment: eclipse fraction, atomic-oxygen fluence;
 4. SEP-assisted climb from a 550 km rideshare with the sail stowed.
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import earth_orbit as EO, sail as S, plotting as P
from cislunar_sail.constants import MU_EARTH, R_EARTH, J2_EARTH, P_SRP_1AU, DAY_S, YEAR_S
from cislunar_sail.environment import jd_from_iso, sun_vector_eci, density_table, orbit_mean_density
from cislunar_sail.designs import HERITAGE, STUDY, sail_system_mass

F107 = {"Solar minimum (F10.7=70)": 70.0, "Moderate (F10.7=150)": 150.0, "Solar maximum (F10.7=230)": 230.0}
EPOCH = "2028-03-20T00:00:00"
D = {d.key: d for d in HERITAGE + STUDY}


def i_sso(a):
    n = math.sqrt(MU_EARTH / a ** 3)
    rate = 2 * math.pi / (365.2422 * 86400)
    return math.degrees(math.acos(-rate / (1.5 * n * J2_EARTH * (R_EARTH / a) ** 2)))


def f_criterion_altitudes(cd=2.7):
    """Altitude where rho v^2 / P_ideal = 2/C_D (max drag = max SRP), Mengali & Quarta (2005)."""
    out = {}
    h = np.arange(300, 1601, 5.0)
    v = np.sqrt(MU_EARTH / (R_EARTH + h)) * 1e3
    for k, f107 in F107.items():
        hh, lst, rho = density_table(f107)
        rmean = np.interp(h, hh, rho.mean(axis=1))
        rmax = np.interp(h, hh, rho.max(axis=1))
        fm = rmean * v ** 2 / (2 * P_SRP_1AU)
        fx = rmax * v ** 2 / (2 * P_SRP_1AU)
        thr = 2 / cd
        out[k] = {"h_mean": float(h[np.argmax(fm < thr)]), "h_dayside": float(h[np.argmax(fx < thr)]),
                  "f_mean": fm.tolist(), "f_day": fx.tolist()}
    out["h"] = h.tolist()
    return out


def sma_rate_sweep(design, alts, days=30.0, drag=True):
    """Mean SMA rate (km/day) over `days` for orbit types x altitudes x F10.7."""
    jd0 = jd_from_iso(EPOCH)
    u, _ = sun_vector_eci(jd0)
    ra_sun = math.degrees(math.atan2(u[1], u[0]))
    craft = EO.Craft(a_c=design.a_c_mm * 1e-3, m0=design.mass_kg, material=design.material,
                     area=design.area_m2, cd=2.2, min_area_frac=0.01)
    cases = []
    for h in alts:
        a = R_EARTH + h
        cases.append(("SSO noon-midnight", h, i_sso(a), ra_sun + 180.0, 0.0))
        cases.append(("SSO dawn-dusk", h, i_sso(a), ra_sun + 90.0, 0.0))
        for k in range(4):   # 28.5 deg, four seasons (launch dates spread over a year)
            cases.append(("28.5 deg inclined", h, 28.5, ra_sun + 180.0, k * 91.3))
    y0 = np.array([EO.initial_state(R_EARTH + h, 1e-4, inc, raan, 0.0, m0=design.mass_kg)[0]
                   for (_, h, inc, raan, _) in cases])
    jd = np.array([jd0 + c[4] for c in cases])
    res = {}
    levels = F107.items() if drag else [("No drag", None)]
    for lab, f107 in levels:
        r = EO.propagate_averaged(y0, jd, craft, t_max_days=days, dt_days=0.25, objective="energy",
                                  ra_target=1e12, f107=f107, K=72, record_every=1000,
                                  rp_decay=R_EARTH + 150.0)
        yf = r["y_final"]
        e = np.hypot(yf[:, 1], yf[:, 2]); af = yf[:, 0] / (1 - e ** 2)
        a0 = y0[:, 0] / (1 - np.hypot(y0[:, 1], y0[:, 2]) ** 2)
        rate = (af - a0) / days
        # decayed (status 2) or numerically invalid after rapid decay (status 3) -> NaN = 'decays'
        rate[(r["status"] >= 2) | (np.abs(rate) > 50.0)] = np.nan
        tab = {}
        for typ in ("SSO noon-midnight", "SSO dawn-dusk", "28.5 deg inclined"):
            idx = [i for i, c in enumerate(cases) if c[0] == typ]
            hs = np.array([cases[i][1] for i in idx])
            vals = rate[idx]
            uniq = np.unique(hs)
            tab[typ] = {"alt_km": uniq.tolist(),
                        "rate_km_day": [float(np.nanmean(vals[hs == u])) for u in uniq]}
        res[lab] = tab
    return res


def zero_crossing(alts, rates):
    alts = np.asarray(alts, float)
    rates = np.array([np.nan if r is None else r for r in rates], float)
    rates = np.where(np.isnan(rates), -1e3, rates)          # decaying cases count as negative
    pos = np.where(rates > 0)[0]
    if pos.size == 0:
        return None
    i = pos[0]
    if i == 0:
        return float(alts[0])
    return float(alts[i - 1] + (0 - rates[i - 1]) * (alts[i] - alts[i - 1]) / (rates[i] - rates[i - 1]))


def gravity_gradient(design, cm_offset_m=0.10):
    ss = sail_system_mass(design.area_m2, design.material)
    s = math.sqrt(design.area_m2)
    L = math.sqrt(design.area_m2 / 2)
    dI = ss["membrane"] * s ** 2 / 12 + (2 / 3) * (ss["booms"] / 4) * L ** 2
    F = design.a_c_mm * 1e-3 * design.mass_kg
    tau_amt = F * cm_offset_m
    h = np.arange(300, 40001, 50.0)
    r = (R_EARTH + h) * 1e3
    tau_gg = 1.5 * MU_EARTH * 1e9 / r ** 3 * dI
    P = 2 * math.pi * np.sqrt(r ** 3 / (MU_EARTH * 1e9))
    h_cross = float(h[np.argmax(tau_gg < tau_amt)])
    mom = tau_gg * P / (2 * math.pi) / 2           # cyclic momentum (twice-per-orbit torque)
    return {"dI_kgm2": dI, "srp_force_N": F, "tau_amt_Nm": tau_amt, "h_gg_equals_amt_km": h_cross,
            "h": h.tolist(), "tau_gg": tau_gg.tolist(), "cyclic_momentum_Nms": mom.tolist()}


def environment_table(alts):
    import pymsis
    out = []
    date = np.datetime64("2028-03-20T12:00")
    for h in alts:
        a = R_EARTH + h
        beta0_eclipse = 1 - math.degrees(math.acos(math.sqrt(h * (2 * R_EARTH + h)) / a)) / 180.0
        frac_ecl = 1 - beta0_eclipse          # eclipse fraction at beta = 0
        v = math.sqrt(MU_EARTH / a) * 1e5      # cm/s
        flu = {}
        for lab, f107 in (("low", 70.0), ("moderate", 150.0), ("high", 230.0)):
            d = pymsis.calculate(date, np.linspace(-180, 165, 24), 0.0, h, f107s=f107, f107as=f107, aps=[[15] * 7])
            nO = np.nanmean(np.squeeze(d[..., pymsis.Variable.O])) * 1e-6   # m^-3 -> cm^-3
            flu[lab] = nO * v * YEAR_S         # atoms/cm^2/yr (ram-facing)
        out.append({"alt_km": h, "eclipse_frac_beta0": frac_ecl, "period_min": 2 * math.pi * math.sqrt(a ** 3 / MU_EARTH) / 60,
                    "AO_fluence_low": flu["low"], "AO_fluence_mod": flu["moderate"], "AO_fluence_high": flu["high"]})
    return out


def decay_time_years(design, h0, f107=150.0, frac_area=0.5, cd=2.2, hmin=200.0):
    hh, lst, rho = density_table(f107)
    rm = rho.mean(axis=1)
    h = h0; t = 0.0; dt = 86400.0 * 5
    bc = cd * design.area_m2 * frac_area / design.mass_kg
    while h > hmin and t < 200 * YEAR_S:
        a = (R_EARTH + h) * 1e3
        rr = np.interp(h, hh, rm)
        dadt = -math.sqrt(MU_EARTH * 1e9 * a) * rr * bc
        h += dadt * dt / 1e3
        t += dt
    return t / YEAR_S


def sep_climb(h0=550.0, h1=1000.0):
    d = D["CR-H"]
    craft = EO.Craft(a_c=0.0, m0=d.mass_kg, material=d.material, area=2.5, min_area_frac=1.0, cd=2.2,
                     sep_thrust=d.sep_thrust_mN * 1e-3, isp=d.isp_s, gimbal_deg=180.0,
                     sail_deployed=False, m_dry=d.mass_kg - d.propellant_kg)
    jd0 = jd_from_iso(EPOCH)
    u, _ = sun_vector_eci(jd0)
    y0 = EO.initial_state(R_EARTH + h0, 1e-4, i_sso(R_EARTH + h0), math.degrees(math.atan2(u[1], u[0])) + 90, 0.0, m0=d.mass_kg)
    out = {}
    for lab, f107 in (("moderate", 150.0), ("high", 230.0)):
        r = EO.propagate_averaged(y0, [jd0], craft, t_max_days=200, dt_days=0.25, objective="energy",
                                  ra_target=1e12, f107=f107, K=48, record_every=4, stop_on_target=False)
        hist_y = r["hist_y"][:, 0, :]
        e = np.hypot(hist_y[:, 1], hist_y[:, 2]); a = hist_y[:, 0] / (1 - e ** 2)
        hgt = a - R_EARTH
        k = np.argmax(hgt >= h1)
        out[lab] = {"days": float(r["hist_t"][k]), "propellant_kg": float(d.mass_kg - hist_y[k, 5])}
    return out


def figures(fcrit, sweep, gg_list, env, sweep_nodrag):
    figs = []
    # 1) drag / SRP ratio
    f, ax = P.fig(size=(10, 5.4))
    h = np.array(fcrit["h"])
    cols = [P.AQUA, P.BLUE, P.ORANGE]
    for (lab, _), c in zip(F107.items(), cols):
        ax.semilogy(h, fcrit[lab]["f_mean"], color=c, label=f"{lab}, orbit mean")
        ax.semilogy(h, fcrit[lab]["f_day"], color=c, lw=1.2, alpha=0.55)
        ax.plot(fcrit[lab]["h_mean"], 2 / 2.7, "o", color=c, ms=8, mec=P.SURFACE, mew=2)
        P.label_end(ax, fcrit[lab]["h_mean"], 2 / 2.7 * 0.62, f"{fcrit[lab]['h_mean']:.0f} km", color=P.INK2, dx=-14)
    ax.axhline(2 / 2.7, color=P.RED, lw=1)
    ax.text(1250, 0.85, "max drag = max SRP  (f = 2/C_D, Mengali & Quarta)", color=P.INK2, fontsize=10.5, ha="center")
    ax.text(1260, 0.03, "thin lines: day-side (14 LST) peak density", color=P.INK2, fontsize=10)
    ax.set_xlim(400, 1600); ax.set_ylim(1e-3, 1e3)
    ax.set_xlabel("circular altitude (km)"); ax.set_ylabel("f = rho v^2 / P_ideal  (drag / SRP)")
    ax.legend(loc="upper right", fontsize=10)
    P.title(ax, "Atmospheric drag overwhelms sunlight pressure below ~600-850 km")
    figs.append(P.save(f, "q8_drag_vs_srp.png"))
    # 2) net SMA rate vs altitude (CR-S)
    f, axs = P.fig(1, 3, size=(12, 4.8), sharey=True)
    for ax, typ in zip(axs, ("SSO noon-midnight", "SSO dawn-dusk", "28.5 deg inclined")):
        nd = sweep_nodrag["No drag"][typ]
        ax.plot(nd["alt_km"], nd["rate_km_day"], color=P.MUTED, lw=1.6, label="no drag")
        for (lab, _), c in zip(F107.items(), cols):
            d = sweep[lab][typ]
            ax.plot(d["alt_km"], d["rate_km_day"], color=c, label=lab.split(" (")[0])
            z = zero_crossing(d["alt_km"], d["rate_km_day"])
            if z:
                ax.plot(z, 0, "o", color=c, ms=7, mec=P.SURFACE, mew=1.5)
        ax.axhline(0, color=P.AXIS, lw=1)
        ax.set_title(typ, fontsize=12.5)
        ax.set_xlabel("altitude (km)")
        ax.set_xlim(500, 1500)
    axs[0].set_ylabel("net SMA change (km/day), CR-S")
    axs[0].set_ylim(-4, 8.5)
    axs[2].legend(loc="lower right", fontsize=9.5)
    f.suptitle("Simulated net orbit raising vs altitude (30-day average, drag-aware steering)", x=0.01, ha="left",
               fontsize=14, fontweight="semibold")
    f.tight_layout()
    figs.append(P.save(f, "q8_sma_rate_vs_altitude.png"))
    # 3) gravity gradient
    f, ax = P.fig(size=(10, 5.2))
    for (key, g), c in zip(gg_list.items(), [P.BLUE, P.ORANGE, P.AQUA]):
        hh = np.array(g["h"]); tg = np.array(g["tau_gg"])
        ax.loglog(hh, tg, color=c, label=f"{key}: gravity-gradient torque (dI = {g['dI_kgm2']:.0f} kg m^2)")
        ax.axhline(g["tau_amt_Nm"], color=c, lw=1.0, alpha=0.7)
        ax.text(330, g["tau_amt_Nm"] * 1.18, f"{key} SRP trim authority (10 cm CM offset)", color=P.INK2, fontsize=9.5)
        if tg[0] > g["tau_amt_Nm"]:
            ax.plot(g["h_gg_equals_amt_km"], g["tau_amt_Nm"], "o", color=c, ms=8, mec=P.SURFACE, mew=2)
            P.label_end(ax, g["h_gg_equals_amt_km"], g["tau_amt_Nm"],
                        f"GG exceeds trim below {g['h_gg_equals_amt_km']:.0f} km", dy=-12)
        else:
            ax.text(1500, tg[0] * 1.5, f"{key}: gravity gradient never exceeds trim authority", color=P.INK2, fontsize=9.5)
    ax.set_xlim(300, 40000)
    ax.set_xlabel("altitude (km)"); ax.set_ylabel("torque (N m)")
    ax.axvline(35786, color=P.AXIS, lw=1); ax.text(30000, 3e-8, "GEO", color=P.INK2, ha="right")
    ax.legend(loc="lower left", fontsize=9.5)
    P.title(ax, "Gravity-gradient torque vs solar-sail trim authority")
    figs.append(P.save(f, "q8_gravity_gradient.png"))
    return figs


def run():
    with Timer("Q8 lowest orbit"):
        fcrit = f_criterion_altitudes()
        alts = list(range(500, 1501, 50))
        sweep = sma_rate_sweep(D["CR-S"], alts)
        sweep_nd = sma_rate_sweep(D["CR-S"], alts, drag=False)
        sweep_acs3 = sma_rate_sweep(D["ACS3"], [600, 700, 800, 900, 1000])
        zc = {lab: {typ: zero_crossing(sweep[lab][typ]["alt_km"], sweep[lab][typ]["rate_km_day"])
                    for typ in sweep[lab]} for lab in sweep}
        # altitude where drag removes <= 25 % of the drag-free raising rate (robust demo margin)
        margin = {}
        for lab in sweep:
            margin[lab] = {}
            for typ in sweep[lab]:
                r = np.array([np.nan if v is None else v for v in sweep[lab][typ]["rate_km_day"]], float)
                r0 = np.array(sweep_nd["No drag"][typ]["rate_km_day"], float)
                good = np.nan_to_num(r, nan=-1e3) >= 0.75 * r0
                # first altitude above which the criterion holds everywhere
                ok = [i for i in range(len(good)) if good[i:].all()]
                margin[lab][typ] = float(np.array(alts)[ok[0]]) if len(ok) else None
        gg = {k: gravity_gradient(D[k]) for k in ("ACS3", "CR-S")}
        env = environment_table([550, 700, 800, 900, 1000, 1200, 1500])
        decay = {h: {"CR-S deployed (yr)": decay_time_years(D["CR-S"], h), "ACS3 deployed (yr)": decay_time_years(D["ACS3"], h)}
                 for h in (550, 700, 800, 900, 1000)}
        climb = sep_climb()
        figs = figures(fcrit, sweep, gg, env, sweep_nd)
        res = {"f_criterion": {k: {kk: vv for kk, vv in v.items() if kk.startswith("h_")} for k, v in fcrit.items() if k != "h"},
               "sma_sweep_CR-S": sweep, "sma_sweep_no_drag": sweep_nd, "sma_sweep_ACS3": sweep_acs3,
               "break_even_alt_km": zc, "alt_drag_loss_le_25pct_km": margin,
               "gravity_gradient": {k: {kk: v[kk] for kk in ("dI_kgm2", "srp_force_N", "tau_amt_Nm", "h_gg_equals_amt_km")} for k, v in gg.items()},
               "environment": env, "decay_years": decay, "sep_climb_550_to_1000km": climb,
               "figures": [p.split("/")[-1] for p in figs]}
        save_results("q8_lowest_orbit", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: r[k] for k in ("f_criterion", "break_even_alt_km", "alt_drag_loss_le_25pct_km", "gravity_gradient", "decay_years", "sep_climb_550_to_1000km")}, indent=1))
    for e in r["environment"]:
        print(e)
