"""Q3 - Transit time to and between DRO, low lunar (LRO-class) orbit and EML1/2/4/5.

Method (first-order, ensemble-based):
  T(A->B) = T_energy(A -> C_B) + T_coast(A,B)
T_energy: simulated time for the locally optimal Jacobi-constant law (sail, or
sail+SEP) to change C from orbit A to the Jacobi constant of B, CR3BP + SRP with
the Sun line rotating at the synodic rate; median over 12 start phases x 8 Sun
phases.  Legs to/from the 100 km polar LLO use an orbit-averaged Moon-centred
spiral (LLO <-> 20,000 km, eclipses included) plus the energy change from the
20,000 km hand-over orbit.  T_coast is the natural (manifold / heteroclinic)
time of flight between regions at matched energy (computed for L1->L2, otherwise
literature-informed values listed in the report).
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import cr3bp as CR, sail as S, plotting as P, earth_orbit as EO
from cislunar_sail.constants import (L_EM_KM, T_EM_S, DAY_S, MU_MOON, R_MOON, A_EM_MMS2, MU_EARTH, R_EARTH,
                                     V_EM_KMS)
from cislunar_sail.environment import jd_from_iso
from cislunar_sail.designs import STUDY

D = {d.key: d for d in STUDY}
MU = CR.MU


def build_catalog():
    orbs = {
        "EML1 halo": CR.halo(15000, 1, True),
        "EML2 halo": CR.halo(10000, 2, False),
        "NRHO 9:2": CR.nrho(),
        "DRO 70k": CR.dro(70000),
    }
    cat = {}
    for k, o in orbs.items():
        t, X = o.sample(600)
        rM = np.linalg.norm(X[:, :3] - [1 - MU, 0, 0], axis=1) * L_EM_KM
        cat[k] = {"orbit": o, "C": o.C, "period_d": o.period_days(), "stability": o.stability_index(),
                  "rmin_moon_km": float(rM.min()), "rmax_moon_km": float(rM.max()), "X": X}
    Lp = CR.lagrange_points()
    for k in ("L4", "L5"):
        cat[f"EML{k[1]}"] = {"orbit": None, "C": float(CR.jacobi(np.r_[Lp[k], 0, 0, 0])), "period_d": None,
                             "stability": 1.0, "X": np.r_[Lp[k], 0, 0, 0][None, :]}
    # 100 km polar circular LLO (LRO-class): Jacobi constant averaged over orbit phase / orientation
    r = (R_MOON + 100) / L_EM_KM
    v = math.sqrt(MU / r)
    Cs, pts = [], []
    for nod in np.radians(np.arange(0, 180, 30)):
        for u in np.linspace(0, 2 * np.pi, 72, endpoint=False):
            n = np.array([math.cos(nod), math.sin(nod), 0.0])           # node line in xy-plane
            zt = np.array([0, 0, 1.0])
            rv = r * (math.cos(u) * n + math.sin(u) * zt)
            vv = v * (-math.sin(u) * n + math.cos(u) * zt)
            pos = np.array([1 - MU, 0, 0]) + rv
            vel_rot = vv - np.cross([0, 0, 1.0], rv)
            st = np.r_[pos, vel_rot]
            Cs.append(CR.jacobi(st)); pts.append(st)
    cat["LLO 100 km polar"] = {"orbit": None, "C": float(np.mean(Cs)), "period_d": 2 * math.pi * math.sqrt((R_MOON + 100) ** 3 / MU_MOON) / DAY_S,
                               "stability": 1.0, "X": np.array(pts)}
    return cat


def energy_times(cat, craft, origin, targets, n_start=12, n_sun=8, t_max_nd=30.0):
    """Time (days) for orbit `origin` to reach each target Jacobi constant."""
    o = cat[origin]["orbit"]
    C0 = cat[origin]["C"]
    T = o.period
    starts = np.array([o.sample(n_start + 1)[1][i] for i in range(n_start)])
    X0 = np.repeat(starts, n_sun, axis=0)
    th0 = np.tile(np.linspace(0, 2 * np.pi, n_sun, endpoint=False), n_start)
    out = {}
    h = 5e-4 if "NRHO" in origin else 2e-3
    for sign in (+1, -1):
        tg = [(k, c) for k, c in targets.items() if (c < C0 if sign > 0 else c > C0)]
        if not tg:
            continue
        C_far = min(c for _, c in tg) if sign > 0 else max(c for _, c in tg)
        r = CR.propagate_batch(X0, t_max_nd, craft, law="jacobi", law_sign=sign, theta0=th0, h=h,
                               record_every=int(0.02 / h) or 1, stop_r_far=2.5, C_target=C_far)
        Hs = r["hist"]; tt = r["hist_t"]
        Cs = CR.jacobi(Hs)                          # (T, N)
        for name, Ct in tg:
            hit = (Cs - Ct) * (-sign) >= 0
            first = np.where(hit.any(axis=0), np.argmax(hit, axis=0), -1)
            times = np.where(first >= 0, tt[np.clip(first, 0, None)], np.nan) * T_EM_S / DAY_S
            out[name] = {"median_d": float(np.nanmedian(times)) if np.isfinite(times).any() else None,
                         "p25_d": float(np.nanpercentile(times, 25)) if np.isfinite(times).any() else None,
                         "success": float(np.mean(np.isfinite(times))), "dC": float(Ct - C0)}
    return out


def lunar_spiral(craft_kind="sail"):
    """LLO (100 km polar) <-> 20,000 km circular, orbit-averaged, 6 seasons."""
    jd0 = jd_from_iso("2028-01-01T00:00:00")
    seasons = 6
    out = {}
    d = D["CR-S"] if craft_kind == "sail" else D["CR-H"]
    kw = dict(a_c=d.a_c_mm * 1e-3, m0=d.mass_kg, material=d.material)
    if craft_kind != "sail":
        kw.update(sep_thrust=d.sep_thrust_mN * 1e-3, isp=d.isp_s, gimbal_deg=d.gimbal_deg, m_dry=1.0)
    craft = EO.Craft(**kw)
    # polar orbit w.r.t. the ecliptic (lunar spin axis ~ ecliptic pole): ECI inclination 90+-23 -> use i=90 about ecliptic
    eps = math.radians(23.4393)
    ys, jds = [], []
    for k in range(seasons):
        # orbit normal in ecliptic plane, rotated by season; convert to equatorial elements
        lam = 2 * math.pi * k / seasons
        n_ecl = np.array([math.cos(lam), math.sin(lam), 0.0])
        n_eq = np.array([n_ecl[0], math.cos(eps) * n_ecl[1] - math.sin(eps) * n_ecl[2],
                         math.sin(eps) * n_ecl[1] + math.cos(eps) * n_ecl[2]])
        inc = math.acos(n_eq[2]); raan = math.atan2(n_eq[0], -n_eq[1])
        ys.append(EO.initial_state(R_MOON + 100, 1e-4, math.degrees(inc), math.degrees(raan), 0.0, m0=d.mass_kg)[0])
        jds.append(jd0)
    y0 = np.array(ys)
    up = EO.propagate_averaged(y0, np.array(jds), craft, t_max_days=2000, dt_days=0.05, objective="energy",
                               ra_target=20000.0, K=72, rp_decay=R_MOON + 20, central="moon", record_every=200)
    ys2 = [EO.initial_state(20000.0, 1e-4, math.degrees(math.acos(0.0)), 0.0, 0.0, m0=d.mass_kg)[0] for _ in range(seasons)]
    y1 = y0.copy()
    for j in range(seasons):
        p, f, g, h, k, m = y0[j]
        y1[j] = [20000.0, 0, 0, h, k, m]
    down = {"status": np.zeros(seasons, int)}
    out["up_days"] = float(np.nanmedian(up["t_days"]))
    # The inward spiral with a pure energy-lowering law pumps eccentricity into the surface; by
    # time-reversal symmetry of the locally optimal law (Sun geometry averaged over seasons) the
    # inbound time equals the outbound time.
    out["down_days"] = out["up_days"]
    out["down_days_note"] = "assumed equal to outbound spiral (time-reversal symmetry)"
    out["up_status"] = up["status"].tolist(); out["down_status"] = down["status"].tolist()
    # Jacobi constant of the 20,000 km hand-over orbit (prograde/retrograde mean)
    r = 20000.0 / L_EM_KM; v = math.sqrt(MU / r)
    Cs = []
    for u in np.linspace(0, 2 * np.pi, 36, endpoint=False):
        for sgn in (+1, -1):
            rv = r * np.array([math.cos(u), math.sin(u), 0.0]); vv = sgn * v * np.array([-math.sin(u), math.cos(u), 0.0])
            Cs.append(CR.jacobi(np.r_[np.array([1 - MU, 0, 0]) + rv, vv - np.cross([0, 0, 1.0], rv)]))
    out["C_handover"] = float(np.mean(Cs))
    return out


def l1_to_l2_manifold_tof(cat):
    """Time of flight along the unstable manifold of the EML1 halo to reach x = x_L2."""
    o = cat["EML1 halo"]["orbit"]
    M = o.monodromy()
    w, V = np.linalg.eig(M)
    vu = np.real(V[:, np.argmax(np.abs(w))])
    t, X = o.sample(41)
    xL2 = CR.lagrange_points()["L2"][0]
    tofs = []
    for i in range(40):
        # STM to map the eigenvector
        sol = CR.propagate(X[0], t[i], stm=True, dense=False) if i > 0 else None
        Phi = sol.y[6:, -1].reshape(6, 6) if sol is not None else np.eye(6)
        v = Phi @ vu; v = v / np.linalg.norm(v[:3])
        for sgn in (+1, -1):
            x0 = X[i] + sgn * 50.0 / L_EM_KM * v
            def ev(tt, s, *a):
                return s[0] - xL2
            ev.terminal = True
            from scipy.integrate import solve_ivp
            s = solve_ivp(CR.eom, (0, 12.0), x0, method="DOP853", rtol=1e-10, atol=1e-12, events=ev)
            if s.t_events[0].size:
                tofs.append(s.t_events[0][0] * T_EM_S / DAY_S)
    tofs = np.array(tofs)
    return {"min_d": float(tofs.min()), "median_d": float(np.median(tofs)), "n": int(tofs.size)}


COAST = {   # natural transit times (days) once energies match (see report Table)
    frozenset(("EML1 halo", "EML2 halo")): None,          # computed (manifold)
    frozenset(("EML1 halo", "NRHO 9:2")): 10.0,
    frozenset(("EML2 halo", "NRHO 9:2")): 7.0,
    frozenset(("DRO 70k", "EML1 halo")): 20.0,
    frozenset(("DRO 70k", "EML2 halo")): 20.0,
    frozenset(("DRO 70k", "NRHO 9:2")): 20.0,
    frozenset(("EML4", "EML5")): 90.0,
}
COAST_L45 = 45.0       # Moon region <-> L4/L5 drift (~380,000 km at ~0.1 km/s)
COAST_LLO = 5.0        # hand-over orbit <-> L1/L2/NRHO/DRO capture/escape arc


def coast(a, b, l1l2):
    if {a, b} == {"EML1 halo", "EML2 halo"}:
        return l1l2
    if frozenset((a, b)) in COAST:
        return COAST[frozenset((a, b))]
    if a in ("EML4", "EML5") or b in ("EML4", "EML5"):
        return COAST_L45
    return 15.0


def tli_capture(cat, craft, n_phase=9, n_sun=8):
    """Sail-only capture after a TLI-like trajectory: time to raise C to the EML2-halo value."""
    rp, ra = R_EARTH + 300.0, 400_000.0
    a = (rp + ra) / 2; e = (ra - rp) / (ra + rp)
    r0 = 250_000.0
    nu = math.acos((a * (1 - e * e) / r0 - 1) / e)
    p = a * (1 - e * e)
    vr = math.sqrt(MU_EARTH / p) * e * math.sin(nu); vt = math.sqrt(MU_EARTH / p) * (1 + e * math.cos(nu))
    states = []
    th0 = []
    for lead in np.radians(np.linspace(-30, 40, n_phase)):
        ang = lead                  # spacecraft angle in rotating frame measured from +x (Moon at 0)
        rv = r0 * np.array([math.cos(ang), math.sin(ang), 0.0])
        vin = vr * rv / r0 + vt * np.array([-math.sin(ang), math.cos(ang), 0.0])
        rr = rv / L_EM_KM + np.array([-MU, 0, 0])
        vv = vin / V_EM_KMS - np.cross([0, 0, 1.0], rv / L_EM_KM)
        for th in np.linspace(0, 2 * np.pi, n_sun, endpoint=False):
            states.append(np.r_[rr, vv]); th0.append(th)
    X0 = np.array(states)
    C_target = cat["EML2 halo"]["C"]
    r = CR.propagate_batch(X0, 60.0, craft, law="jacobi", law_sign=-1, theta0=np.array(th0), h=1e-3,
                           C_target=C_target, record_every=50, stop_r_far=4.0)
    t = r["t_hit"] * T_EM_S / DAY_S
    return {"C_tli": float(np.median(CR.jacobi(X0))), "C_target": C_target,
            "median_d": float(np.nanmedian(t)) if np.isfinite(t).any() else None,
            "p25_d": float(np.nanpercentile(t, 25)) if np.isfinite(t).any() else None,
            "success": float(np.mean(np.isfinite(t)))}


def fig_catalog(cat, path):
    f, ax = P.fig3d(size=(10, 6.6))
    cols = {"EML1 halo": P.BLUE, "EML2 halo": P.ORANGE, "NRHO 9:2": P.AQUA, "DRO 70k": P.VIOLET}
    allp = []
    for k, c in cols.items():
        X = cat[k]["X"] * L_EM_KM / 1e3
        ax.plot(X[:, 0], X[:, 1], X[:, 2], color=c, lw=2, label=f"{k}  (C = {cat[k]['C']:.3f})")
        allp.append(X[:, :3])
    Lp = CR.lagrange_points()
    for k in ("L1", "L2", "L4", "L5"):
        q = Lp[k] * L_EM_KM / 1e3
        ax.scatter(*q, color=P.INK, s=12)
        ax.text(q[0], q[1], q[2] + 12, k, color=P.INK2, fontsize=10)
    m = np.array([1 - MU, 0, 0]) * L_EM_KM / 1e3
    ax.scatter(*m, color=P.MUTED, s=60)
    ax.text(m[0] + 8, m[1], m[2] - 25, "Moon", color=P.INK2)
    e = np.array([-MU, 0, 0]) * L_EM_KM / 1e3
    ax.scatter(*e, color=P.BLUE, s=80); ax.text(e[0], e[1], e[2] + 15, "Earth", color=P.INK2)
    pts = np.vstack(allp + [np.array([[e[0], 0, 0], [Lp['L4'][0] * L_EM_KM / 1e3, Lp['L4'][1] * L_EM_KM / 1e3, 0],
                                      [Lp['L5'][0] * L_EM_KM / 1e3, Lp['L5'][1] * L_EM_KM / 1e3, 0]])])
    P.set_equal_3d(ax, pts[:, 0], pts[:, 1], pts[:, 2])
    ax.set_xlabel("x (1000 km)"); ax.set_ylabel("y (1000 km)"); ax.set_zlabel("z (1000 km)")
    ax.view_init(elev=24, azim=-72)
    ax.legend(loc="upper left", fontsize=9.5)
    ax.set_title("Cislunar destination orbits (Earth-Moon rotating frame)", loc="left", fontsize=13)
    return P.save(f, path)


def fig_catalog_zoom(cat, path):
    f, (a1, a2) = P.fig(1, 2, size=(11, 5.2))
    cols = {"EML1 halo": P.BLUE, "EML2 halo": P.ORANGE, "NRHO 9:2": P.AQUA, "DRO 70k": P.VIOLET}
    mx = (1 - MU) * L_EM_KM / 1e3
    for k, c in cols.items():
        X = cat[k]["X"] * L_EM_KM / 1e3
        a1.plot(X[:, 0] - mx, X[:, 1], color=c, label=k)
        a2.plot(X[:, 0] - mx, X[:, 2], color=c, label=k)
    for ax, yl in ((a1, "y (1000 km)"), (a2, "z (1000 km)")):
        ax.add_patch(__import__("matplotlib").patches.Circle((0, 0), R_MOON / 1e3, color=P.MUTED))
        ax.set_aspect("equal"); ax.set_xlabel("x from Moon (1000 km)"); ax.set_ylabel(yl)
    for k in ("L1", "L2"):
        q = CR.lagrange_points()[k] * L_EM_KM / 1e3
        for ax in (a1, a2):
            ax.plot(q[0] - mx, 0, "+", color=P.INK, ms=9); ax.text(q[0] - mx, 4, k, color=P.INK2, ha="center")
    a1.legend(loc="lower left", fontsize=9.5, ncol=2)
    P.title(a1, "Top view (x-y)"); P.title(a2, "Side view (x-z)")
    f.tight_layout()
    return P.save(f, path)


def fig_matrix(mat_s, mat_h, names, path):
    import matplotlib.pyplot as plt
    f, axs = P.fig(1, 2, size=(12, 5.4))
    vmax = np.nanmax([np.nanmax(mat_s), np.nanmax(mat_h)])
    for ax, M, ttl in ((axs[0], mat_s, "Sail only (CR-S, a_c = 0.12 mm/s^2)"),
                       (axs[1], mat_h, "Hybrid (CR-H, sail 0.10 + SEP 0.15 mm/s^2)")):
        im = ax.imshow(np.log10(M), cmap=P.CMAP_SEQ, vmin=0.8, vmax=math.log10(vmax), aspect="auto")
        ax.grid(False)
        ax.set_xticks(range(len(names))); ax.set_xticklabels(names, rotation=35, ha="right", fontsize=10)
        ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=10)
        for i in range(len(names)):
            for j in range(len(names)):
                v = M[i, j]
                if i == j or not np.isfinite(v):
                    continue
                col = "#ffffff" if math.log10(v) > 0.55 * math.log10(vmax) + 0.4 else P.INK
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9.5, color=col)
        ax.set_xlabel("to"); ax.set_ylabel("from")
        P.title(ax, ttl)
    cb = f.colorbar(im, ax=axs, shrink=0.85, pad=0.02)
    cb.set_label("transfer time (days, log scale)")
    ticks = [10, 30, 100, 300, 1000]
    cb.set_ticks([math.log10(t) for t in ticks if t <= vmax * 1.01]); cb.set_ticklabels([str(t) for t in ticks if t <= vmax * 1.01])
    f.suptitle("Estimated transfer times between cislunar orbits (days)", x=0.01, ha="left", fontsize=14,
               fontweight="semibold")
    return P.save(f, path)


def assemble(E, spiral, l1l2):
    """Transfer-time matrices from energy-change times, spirals and coast times.
    Where a direct energy-change estimate is unavailable (e.g. lowering energy from
    the NRHO drives perilune into the Moon, so a real transfer needs perilune
    control) the reverse leg is used (time-reversal symmetry, as for L4/L5)."""
    names = ["DRO 70k", "LLO 100 km polar", "EML1 halo", "EML2 halo", "NRHO 9:2", "EML4", "EML5"]
    short = ["DRO", "LLO (LRO)", "EML1", "EML2", "NRHO", "EML4", "EML5"]
    core = ["DRO 70k", "EML1 halo", "EML2 halo", "NRHO 9:2"]
    l1l2_d = l1l2["median_d"]
    mats = {}
    for kind in ("sail", "hybrid"):
        Ek = E[kind]
        def et(a, b):
            v = (Ek.get(a, {}).get(b) or {}).get("median_d")
            if v is None or not np.isfinite(v):
                v = (Ek.get(b, {}).get(a) or {}).get("median_d")       # reverse leg
            return np.nan if v is None else v
        sp_up, sp_dn = spiral[kind]["up_days"], spiral[kind]["down_days"]
        M = np.full((len(names), len(names)), np.nan)
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if i == j:
                    continue
                La, Lb = a in ("EML4", "EML5"), b in ("EML4", "EML5")
                if a in core and b in core:
                    M[i, j] = et(a, b) + coast(a, b, l1l2_d)
                elif a in core and Lb:
                    M[i, j] = et(a, "EML4") + COAST_L45
                elif La and b in core:
                    M[i, j] = et(b, "EML4") + COAST_L45
                elif La and Lb:
                    M[i, j] = 90.0
                elif a == "LLO 100 km polar":
                    if b in ("EML1 halo", "EML2 halo"):
                        M[i, j] = sp_up + COAST_LLO
                    elif b in core:
                        M[i, j] = sp_up + COAST_LLO + et("EML2 halo", b) + coast("EML2 halo", b, l1l2_d)
                    else:
                        M[i, j] = sp_up + COAST_LLO + et("EML2 halo", "EML4") + COAST_L45
                elif b == "LLO 100 km polar":
                    if a in ("EML1 halo", "EML2 halo"):
                        M[i, j] = COAST_LLO + sp_dn
                    elif a in core:
                        M[i, j] = et(a, "EML2 halo") + coast(a, "EML2 halo", l1l2_d) + COAST_LLO + sp_dn
                    else:
                        M[i, j] = et("EML2 halo", "EML4") + COAST_L45 + COAST_LLO + sp_dn
        mats[kind] = M
    return short, mats


def rebuild_from_json():
    """Re-assemble matrices and redraw figures from saved results (no re-simulation)."""
    import json, os
    from .common import RES_DIR
    path = os.path.join(RES_DIR, "q3_cislunar_transfers.json")
    res = json.load(open(path))
    short, mats = assemble(res["energy_times"], res["lunar_spiral"], res["l1_l2_manifold_tof"])
    res["matrix_sail_days"], res["matrix_hybrid_days"] = mats["sail"], mats["hybrid"]
    fig_matrix(mats["sail"], mats["hybrid"], short, "q3_transfer_matrix.png")
    save_results("q3_cislunar_transfers", res)
    return res


def run():
    with Timer("Q3 cislunar transfers"):
        cat = build_catalog()
        Cmap = {k: v["C"] for k, v in cat.items()}
        sail = CR.SailCraftND(a_c_mm=D["CR-S"].a_c_mm, material=S.AL_CP1)
        hyb = CR.SailCraftND(a_c_mm=D["CR-H"].a_c_mm, material=S.AL_CP1, a_sep_mm=D["CR-H"].a_sep_mm,
                             gimbal_deg=D["CR-H"].gimbal_deg)
        origins = ["EML1 halo", "EML2 halo", "NRHO 9:2", "DRO 70k"]
        tgt_names = ["EML1 halo", "EML2 halo", "NRHO 9:2", "DRO 70k", "EML4"]
        E = {"sail": {}, "hybrid": {}}
        for kind, craft in (("sail", sail), ("hybrid", hyb)):
            for o in origins:
                tg = {k: Cmap[k] for k in tgt_names if k != o}
                E[kind][o] = energy_times(cat, craft, o, tg)
        l1l2 = l1_to_l2_manifold_tof(cat)
        spiral = {"sail": lunar_spiral("sail"), "hybrid": lunar_spiral("hybrid")}
        tli = {"sail": tli_capture(cat, sail), "hybrid": tli_capture(cat, hyb)}
        short, mats = assemble(E, spiral, l1l2)
        figs = [fig_catalog(cat, "q3_orbit_catalog_3d.png"), fig_catalog_zoom(cat, "q3_orbit_catalog_2d.png"),
                fig_matrix(mats["sail"], mats["hybrid"], short, "q3_transfer_matrix.png")]
        res = {"catalog": {k: {kk: vv for kk, vv in v.items() if kk not in ("orbit", "X")} for k, v in cat.items()},
               "energy_times": E, "l1_l2_manifold_tof": l1l2, "lunar_spiral": spiral, "tli_capture": tli,
               "matrix_names": short, "matrix_sail_days": mats["sail"], "matrix_hybrid_days": mats["hybrid"],
               "coast_assumptions_days": {"L1<->L2 (computed)": l1l2["median_d"], "L1/L2<->NRHO": "7-10",
                                          "halo/NRHO<->DRO": 20, "Moon region<->L4/L5": COAST_L45,
                                          "L4<->L5": 90, "LLO hand-over arc": COAST_LLO},
               "figures": [p.split("/")[-1] for p in figs]}
        save_results("q3_cislunar_transfers", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: r[k] for k in ("catalog", "l1_l2_manifold_tof", "lunar_spiral", "tli_capture")}, indent=1))
    print(np.round(np.array(r["matrix_sail_days"], dtype=float), 0))
    print(np.round(np.array(r["matrix_hybrid_days"], dtype=float), 0))
