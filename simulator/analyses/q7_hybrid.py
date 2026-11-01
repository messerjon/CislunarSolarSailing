"""Q7 - Maneuverability and acceleration of the hybrid (sail + gimballed SEP) approach.

* acceleration envelope per design (along / perpendicular to / against sunlight)
* reachable sets after 3 and 7 days from a DRO (batched CR3BP + SRP propagation of
  constant-direction steering commands - PyTorch/GPU friendly)
* manoeuvre response time vs direction for a given delta-v
* mass trade sail vs SEP vs hybrid for multi-year cislunar operations
"""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import cr3bp as CR, sail as S, plotting as P
from cislunar_sail.backend import get_backend
from cislunar_sail.constants import L_EM_KM, T_EM_S, DAY_S, A_EM_MMS2, YEAR_S, G0
from cislunar_sail.designs import STUDY, sep_system_mass, sail_system_mass
from .q5_in_irons import support

D = {d.key: d for d in STUDY}


def envelope_table():
    rows = []
    for key in ("CR-S", "CR-H", "CR-A"):
        d = D[key]
        if d.sep_thrust_mN > 0:
            th, g = support(d.material.front, d.a_sep_mm / d.a_c_mm, d.gimbal_deg)
        else:
            th, g = support(d.material.front)
        g = g * d.a_c_mm
        rows.append({"design": key, "a_c_mm_s2": d.a_c_mm, "a_sep_mm_s2": d.a_sep_mm,
                     "away_from_sun": float(g[0]), "perpendicular": float(np.interp(np.pi / 2, th, g)),
                     "toward_sun": float(g[-1]), "isotropic_mean": float(np.mean(np.interp(np.arccos(np.linspace(-1, 1, 2001)), th, g))),
                     "theta": th.tolist(), "g": g.tolist()})
    return rows


def fib_sphere(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n); th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)


def reachable(days=(3.0, 7.0), n_dir=400, backend=None):
    B = get_backend(backend)
    dro = CR.dro(70000)
    x0 = dro.s0.copy()
    dirs = fib_sphere(n_dir)
    out = {}
    T = max(days) * DAY_S / T_EM_S
    configs = {"CR-S sail": CR.SailCraftND(a_c_mm=D["CR-S"].a_c_mm),
               "CR-H hybrid": CR.SailCraftND(a_c_mm=D["CR-H"].a_c_mm, a_sep_mm=D["CR-H"].a_sep_mm,
                                             gimbal_deg=D["CR-H"].gimbal_deg)}
    face = S.AL_CP1.front
    # natural (feathered) reference
    ref = CR.propagate_batch(x0[None, :], T, configs["CR-S sail"], law="feather", h=1e-3, record_every=1)
    ref_t, ref_h = ref["hist_t"], ref["hist"][:, 0, :]
    theta0 = 0.0   # Sun beyond the Moon (+x) at t0
    for name, craft in configs.items():
        Dd = B.asarray(dirs)
        def ctrl(Bk, t, X, u_sun, lit, craft=craft, Dd=Dd):
            s_hat = -u_sun
            if craft.a_sep_mm > 0:
                res = S.best_hybrid(Bk, face, s_hat, Dd, craft.ac * lit, craft.asep, gimbal_deg=craft.gimbal_deg)
                n = res["n_hat"]
                return S.sail_accel(Bk, face, S.AL_CP1.back, s_hat, n, craft.ac, lit=lit) + res["comp_sep"][..., None] * Dd
            n, _ = S.optimal_normal(Bk, face, s_hat, Dd)
            return S.sail_accel(Bk, face, S.AL_CP1.back, s_hat, n, craft.ac, lit=lit)
        X0 = np.repeat(x0[None, :], n_dir, axis=0)
        r = CR.propagate_batch(X0, T, craft, law="custom", control_fn=ctrl, theta0=theta0, h=1e-3,
                               record_every=1, backend=backend)
        res = {}
        for dd in days:
            k = np.argmin(abs(r["hist_t"] - dd * DAY_S / T_EM_S))
            kr = np.argmin(abs(ref_t - r["hist_t"][k]))
            disp = (r["hist"][k][:, :3] - ref_h[kr][:3]) * L_EM_KM
            res[f"{dd:g}"] = disp
        out[name] = res
    return out, dirs


def response_time(dvs=(10.0, 50.0)):
    """Days to impart delta-v along a direction at angle theta from sunlight (Sun fixed)."""
    out = {}
    for key in ("CR-S", "CR-H"):
        d = D[key]
        if d.sep_thrust_mN > 0:
            th, g = support(d.material.front, d.a_sep_mm / d.a_c_mm, d.gimbal_deg)
        else:
            th, g = support(d.material.front)
        acc = g * d.a_c_mm * 1e-3
        out[key] = {f"{dv:g}": np.where(acc > 1e-9, dv / np.maximum(acc, 1e-12) / DAY_S, np.nan).tolist() for dv in dvs}
        out[key]["theta_deg"] = np.degrees(th).tolist()
    return out


def mass_trade(dv_tot=np.linspace(0, 15, 61), bus=60.0, f_irons=0.18, isp=1500.0):
    """Initial mass vs cumulative manoeuvre delta-v (km/s) for a 60 kg bus.
    SEP-only: 20 mN-class SEP does all delta-v.  Hybrid: 1653 m^2 sail does the
    reachable share, SEP the in-irons share f_irons.  Sail-only: no propellant, but
    f_irons of the demands must wait for better Sun geometry."""
    sail = sail_system_mass(1653.0)["total"]
    sep = sep_system_mass(20.0, isp, 0.0)["total_dry"]
    ve = isp * G0 / 1e3
    out = {"dv_tot_km_s": dv_tot.tolist()}
    for name, dry, frac in (("SEP only", bus + sep, 1.0), ("Hybrid (CR-H class)", bus + sep + sail, f_irons),
                            ("Sail only (CR-S class)", bus + sail, 0.0)):
        mr = np.exp(frac * dv_tot / ve)
        out[name] = (dry * mr / (1 - 0.1 * (mr - 1))).tolist()       # 10 % tankage on propellant
    x_h = math.log((bus + sep + sail) / (bus + sep)) * ve / (1 - f_irons)
    x_s = math.log((bus + sail) / (bus + sep)) * ve
    out["notes"] = {"bus_kg": bus, "sail_system_kg": sail, "sep_dry_kg": sep, "isp_s": isp,
                    "in_irons_fraction": f_irons, "hybrid_beats_sep_above_km_s": x_h,
                    "sail_beats_sep_above_km_s": x_s}
    return out


def fig_envelopes(rows, path):
    f, ax = P.fig(size=(10, 5.0))
    for r, c in zip(rows, [P.BLUE, P.ORANGE, P.AQUA]):
        ax.plot(np.degrees(r["theta"]), r["g"], color=c, label=f"{r['design']}  (a_c {r['a_c_mm_s2']:.3f}"
                + (f" + SEP {r['a_sep_mm_s2']:.3f}" if r['a_sep_mm_s2'] > 0 else "") + " mm/s^2)")
    ax.set_xlim(0, 180); ax.set_xticks(range(0, 181, 30)); ax.set_ylim(0, None)
    ax.set_xlabel("angle between commanded thrust and sunlight (deg)")
    ax.set_ylabel("max acceleration along command (mm/s^2)")
    ax.legend(loc="upper right", fontsize=10)
    P.title(ax, "Acceleration available in every direction")
    return P.save(f, path)


def fig_reach(reach, path, day="7"):
    f, axs = P.fig(1, 2, size=(12, 5.3), sharex=True, sharey=True)
    for ax, (name, res), c in zip(axs, reach.items(), [P.BLUE, P.ORANGE]):
        dsp = res[day] / 1e3
        ax.scatter(dsp[:, 0], dsp[:, 1], s=9, color=c, alpha=0.75, lw=0)
        d3 = res["3"] / 1e3
        ax.scatter(d3[:, 0], d3[:, 1], s=7, color=P.MUTED, alpha=0.6, lw=0)
        ax.plot(0, 0, "+", color=P.INK, ms=12, mew=1.5)
        ax.annotate("", xy=(22, -17), xytext=(40, -17), arrowprops=dict(arrowstyle="-|>", color=P.YELLOW, lw=2),
                    annotation_clip=True)
        ax.text(31, -15.5, "sunlight", color=P.INK2, fontsize=10, ha="center")
        ax.set_aspect("equal")
        ax.set_xlabel("displacement x (1000 km)")
        P.title(ax, f"{name}: grey = 3 days, colour = {day} days")
    axs[0].set_ylabel("displacement y (1000 km)")
    f.suptitle("Reachable positions from a 70,000 km DRO relative to the natural trajectory (Sun initially at +x)",
               x=0.01, ha="left", fontsize=13.5, fontweight="semibold")
    f.tight_layout()
    return P.save(f, path)


def fig_reach3d(reach, path, day="7"):
    f, ax = P.fig3d(size=(9.5, 6.4))
    for (name, res), c in zip(reach.items(), [P.BLUE, P.ORANGE]):
        dsp = res[day] / 1e3
        ax.scatter(dsp[:, 0], dsp[:, 1], dsp[:, 2], s=6, color=c, alpha=0.7, label=name, depthshade=False)
    ax.quiver(90, 0, 0, -40, 0, 0, color=P.YELLOW, linewidth=2.5, arrow_length_ratio=0.2)
    ax.text(90, 0, 8, "sunlight", color=P.INK2)
    allp = np.vstack([r[day] for r in reach.values()]) / 1e3
    P.set_equal_3d(ax, allp[:, 0], allp[:, 1], allp[:, 2])
    ax.set_xlabel("dx (1000 km)"); ax.set_ylabel("dy (1000 km)"); ax.set_zlabel("dz (1000 km)")
    ax.legend(loc="upper left", fontsize=10)
    ax.view_init(elev=20, azim=-55)
    ax.set_title(f"{day}-day reachable set from the DRO: sail (blue) vs hybrid (orange)", loc="left", fontsize=13)
    return P.save(f, path)


def fig_response(rt, path):
    f, ax = P.fig(size=(10, 4.8))
    for key, c in (("CR-S", P.BLUE), ("CR-H", P.ORANGE)):
        th = rt[key]["theta_deg"]
        ax.semilogy(th, rt[key]["10"], color=c, label=f"{key}: 10 m/s")
        ax.semilogy(th, rt[key]["50"], color=c, lw=1.2, alpha=0.6, label=f"{key}: 50 m/s")
    ax.set_xlim(0, 180); ax.set_xticks(range(0, 181, 30)); ax.set_ylim(0.3, 300)
    ax.set_xlabel("direction of the manoeuvre relative to sunlight (deg)")
    ax.set_ylabel("days to deliver the delta-v")
    ax.legend(loc="upper left", fontsize=10, ncol=2)
    P.title(ax, "Manoeuvre response time: the sail stalls toward the Sun, the hybrid does not")
    return P.save(f, path)


def fig_mass(mt, path):
    f, ax = P.fig(size=(10, 4.8))
    x = mt["dv_tot_km_s"]
    for name, c in (("SEP only", P.MUTED), ("Hybrid (CR-H class)", P.ORANGE), ("Sail only (CR-S class)", P.BLUE)):
        ax.plot(x, mt[name], color=c, label=name)
    n = mt["notes"]
    for xv, lab in ((n["sail_beats_sep_above_km_s"], "sail-only lighter"), (n["hybrid_beats_sep_above_km_s"], "hybrid lighter")):
        ax.axvline(xv, color=P.AXIS, lw=1)
        ax.text(xv + 0.15, 210, f"{lab}\nthan SEP-only\nabove {xv:.1f} km/s", fontsize=9.5, color=P.INK2, va="top")
    ax.set_xlabel("cumulative manoeuvre delta-v over the mission (km/s)"); ax.set_ylabel("initial mass (kg)")
    ax.set_ylim(0, 220); ax.set_xlim(0, 15)
    ax.legend(loc="upper left", fontsize=10)
    P.title(ax, "When does a sail pay for itself? (60 kg bus, 20 mN SEP at Isp 1500 s)")
    return P.save(f, path)


def run():
    with Timer("Q7 hybrid"):
        rows = envelope_table()
        reach, dirs = reachable()
        rt = response_time()
        mt = mass_trade()
        cross = mt["notes"]["hybrid_beats_sep_above_km_s"]
        stats = {}
        for name, res in reach.items():
            stats[name] = {}
            for dd, disp in res.items():
                sunward = disp[:, 0]          # Sun initially along +x
                stats[name][dd] = {"max_disp_km": float(np.max(np.linalg.norm(disp, axis=1))),
                                   "max_sunward_km": float(np.max(sunward)),
                                   "max_antisun_km": float(np.max(-disp[:, 0])),
                                   "max_out_of_plane_km": float(np.max(np.abs(disp[:, 2])))}
        figs = [fig_envelopes(rows, "q7_acceleration_envelope.png"), fig_reach(reach, "q7_reachable_2d.png"),
                fig_reach3d(reach, "q7_reachable_3d.png"), fig_response(rt, "q7_response_time.png"),
                fig_mass(mt, "q7_mass_trade.png")]
        res = {"envelopes": [{k: v for k, v in r.items() if k not in ("theta", "g")} for r in rows],
               "reachable_stats": stats, "response_days": {k: {"10_at_0": v["10"][0], "10_at_90": v["10"][len(v["10"]) // 2],
                                                               "10_at_180": v["10"][-1], "50_at_0": v["50"][0],
                                                               "50_at_90": v["50"][len(v["50"]) // 2], "50_at_180": v["50"][-1]}
                                                           for k, v in rt.items()},
               "mass_trade": {k: (v if k in ("notes",) else [v[0], v[len(v) // 2], v[-1]]) for k, v in mt.items()},
               "hybrid_beats_sep_above_cumulative_dv_km_s": cross,
               "annual_dv_km_s": {"CR-S isotropic-mean": rows[0]["isotropic_mean"] * 1e-3 * YEAR_S / 1e3,
                                  "CR-H isotropic-mean (SEP always on)": rows[1]["isotropic_mean"] * 1e-3 * YEAR_S / 1e3,
                                  "CR-H SEP propellant-limited total": D["CR-H"].sep_dv_kms},
               "figures": [p.split("/")[-1] for p in figs]}
        save_results("q7_hybrid", res)
        return res


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "figures"}, indent=1))
