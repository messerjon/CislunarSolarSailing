"""Design-option trades: sail size/mass/material, rigid booms vs spin deployment,
single- vs double-sided film, electrochromic reflectivity control (RCD), bus
gimbal / active mass translation, and a retractable (reefable) sail."""
import math
import numpy as np

from .common import save_results, Timer
from cislunar_sail import sail as S, plotting as P
from cislunar_sail.backend import get_backend
from cislunar_sail.constants import P_SRP_1AU
from cislunar_sail.designs import HERITAGE, STUDY, sail_system_mass, characteristic_acc_mm

B = get_backend("numpy")
D = {d.key: d for d in HERITAGE + STUDY}


def ac_vs_area():
    A = np.logspace(np.log10(30), np.log10(10000), 80)
    out = {"area": A.tolist()}
    for bus in (10.0, 50.0, 100.0):
        for booms in ("rigid", "spin"):
            for mat, lab in ((S.AL_CP1, "CP1 2.5um"), (S.CP1_THIN, "CP1 1um")):
                m = np.array([bus + sail_system_mass(a, mat, booms)["total"] for a in A])
                out[f"bus{bus:.0f}_{booms}_{lab}"] = (P_SRP_1AU * A / m * mat.front.total * 1e3).tolist()
    return out


def thermal():
    cone = np.linspace(0, 89, 90)
    out = {"cone": cone.tolist()}
    for m in (S.AL_CP1, S.AL_PEN_CR, S.AL_AL_CP1):
        out[m.name] = S.equilibrium_temperature_K(m.front, cone).tolist()
        out[m.name + " eff"] = m.front.efficiency
    return out


def rcd_torque(area=1653.0, fracs=(0.01, 0.02, 0.05), arm_frac=0.8):
    """Pitch/yaw torque from differential RCD switching at the tips (normal-force
    difference) and roll torque from 30-deg canted panels, vs Sun incidence angle."""
    sia = np.linspace(0, 80, 81)
    c = np.cos(np.radians(sia))
    def normal_coeff(f, cc):
        return cc * (f.a3 * cc + f.a1 * cc + f.a2)
    def tang_coeff(f, cc):
        return f.a3 * cc * np.sqrt(1 - cc ** 2)
    L = arm_frac * math.sqrt(area / 2)
    out = {"sia": sia.tolist(), "arm_m": L}
    for fr in fracs:
        Ar = fr * area / 2                     # half the panels switched against the other half
        dn = np.abs(normal_coeff(S.RCD_ON, c) - normal_coeff(S.RCD_OFF, c))
        out[f"pitch_{fr}"] = (P_SRP_1AU * Ar * dn * L).tolist()
        inc = sia + 30.0                                       # canted panels see a larger incidence
        cc = np.cos(np.radians(np.minimum(inc, 90.0)))
        dt = np.abs(normal_coeff(S.RCD_ON, cc) - normal_coeff(S.RCD_OFF, cc)) * math.sin(math.radians(30))
        dt = np.where(inc < 89.5, dt, np.nan)                  # panel edge-on: no authority
        out[f"roll_{fr}"] = (P_SRP_1AU * Ar * dt * L).tolist()
    d = D["CR-S"]
    F = d.a_c_mm * 1e-3 * d.mass_kg
    out["F_sail_N"] = F
    out["amt_10cm"] = F * 0.10
    out["gimbal_30deg_1m_bus60pct"] = F * 0.6 * 1.0 * math.sin(math.radians(30))
    out["disturbance_cmcp"] = {f"{e*100:.0f} cm": F * e for e in (0.01, 0.05, 0.10)}
    out["solar_cruiser_roll_req"] = 2.96e-5
    out["momentum_per_day_5cm_Nms"] = F * 0.05 * 86400
    return out


def reefing_feasibility(n=20000, seed=5):
    """Fraction of random control-acceleration demands (direction isotropic, magnitude
    uniform in [0, a_c]) that each configuration can produce exactly (within 5 %)."""
    rng = np.random.default_rng(seed)
    face = S.AL_CP1.front
    a, fs, fp = S.meridian(face, 2001)
    fs, fp = fs / face.total, fp / face.total
    ang = np.arctan2(fp, fs)                   # direction of force from Sun line
    rad = np.hypot(fs, fp)
    z = rng.uniform(-1, 1, n); th = np.arccos(z)           # demand angle from Sun line
    mag = rng.uniform(0, 1, n)
    order = np.argsort(ang)
    r_dir = np.interp(th, ang[order], rad[order], right=-1.0)   # bubble radius in that direction (-1 if impossible)
    fixed = (r_dir > 0) & (np.abs(mag - r_dir) <= 0.05)
    reef = (r_dir > 0) & (mag <= r_dir * 1.0)
    # hybrid CR-H: SEP (1.47 a_c, +/-30 deg) closes any residual up to its magnitude
    from .q5_in_irons import support, RATIO_CRH
    tt, g = support(face, RATIO_CRH, 30.0)
    hyb = mag <= np.interp(th, tt, g)
    return {"fixed_area_sail": float(fixed.mean()), "reefable_sail": float(reef.mean()),
            "hybrid_CR-H": float(hyb.mean()), "max_force_cone_deg": float(np.degrees(ang.max()))}


def figs(acA, th, rcd, reef):
    out = []
    f, ax = P.fig(size=(10, 5.2))
    A = np.array(acA["area"])
    for (bus, c) in ((10, P.AQUA), (50, P.BLUE), (100, P.ORANGE)):
        ax.loglog(A, acA[f"bus{bus}_rigid_CP1 2.5um"], color=c, label=f"{bus} kg bus, rigid booms, 2.5 um CP1")
        ax.loglog(A, acA[f"bus{bus}_spin_CP1 2.5um"], color=c, lw=1.2, alpha=0.6, label=f"{bus} kg bus, spin-deployed")
    for key, mk in (("LS2", "o"), ("ACS3", "s"), ("NEAS", "^"), ("SC", "D"), ("CR-A", "*")):
        d = D[key]
        ax.plot(d.area_m2, d.a_c_mm, mk, color=P.INK, ms=9 if mk != "*" else 13, mec=P.SURFACE, mew=1.2)
        ax.annotate(d.name.split(" (")[0], (d.area_m2, d.a_c_mm), xytext=(6, -12 if key != "CR-A" else 6),
                    textcoords="offset points", fontsize=9.5, color=P.INK2)
    ax.axhspan(0.58, 2.0, color=P.RED, alpha=0.06, lw=0)
    ax.text(35, 0.95, "pole-sitter / hover regime (>= 0.58 mm/s^2)", fontsize=9.5, color=P.INK2)
    ax.set_xlabel("sail area (m^2)"); ax.set_ylabel("characteristic acceleration a_c (mm/s^2)")
    ax.set_xlim(30, 10000); ax.set_ylim(0.01, 2.0)
    ax.legend(loc="lower right", fontsize=8.8, ncol=1)
    P.title(ax, "Characteristic acceleration vs sail size and bus mass (mass model calibrated on ACS3 & Solar Cruiser)")
    out.append(P.save(f, "dt_ac_vs_area.png"))

    f, ax = P.fig(size=(10, 4.8))
    cone = th["cone"]
    for (m, c) in ((S.AL_CP1, P.BLUE), (S.AL_PEN_CR, P.ORANGE), (S.AL_AL_CP1, P.RED)):
        ax.plot(cone, np.array(th[m.name]) - 273.15, color=c, label=f"{m.name}  (thrust eff. {th[m.name + ' eff']:.3f})")
    ax.axhline(150, color=P.AXIS, lw=1); ax.text(1, 153, "PEN / Mylar sustained-use limit ~150 C", fontsize=9.5, color=P.INK2)
    ax.set_xlabel("cone (Sun-incidence) angle (deg)"); ax.set_ylabel("membrane temperature at 1 AU (C)")
    ax.set_xlim(0, 89)
    ax.legend(loc="upper right", fontsize=10)
    P.title(ax, "Single- vs double-sided film: a reflective back face runs ~150 C hotter")
    out.append(P.save(f, "dt_thermal_single_double.png"))

    f, ax = P.fig(size=(10, 5.0))
    sia = rcd["sia"]
    for fr, c in ((0.01, P.AQUA), (0.02, P.BLUE), (0.05, P.VIOLET)):
        ax.semilogy(sia, rcd[f"pitch_{fr}"], color=c, label=f"RCD {fr*100:.0f} % area: pitch/yaw")
        ax.semilogy(sia, rcd[f"roll_{fr}"], color=c, lw=1.2, alpha=0.6, label=f"RCD {fr*100:.0f} %: roll (30 deg canted)")
    ax.axhline(rcd["amt_10cm"], color=P.ORANGE, lw=1.4); ax.text(1, rcd["amt_10cm"] * 1.15, "active mass translator, 10 cm", fontsize=9.5, color=P.INK2)
    ax.axhline(rcd["gimbal_30deg_1m_bus60pct"], color=P.RED, lw=1.4)
    ax.text(1, rcd["gimbal_30deg_1m_bus60pct"] * 1.15, "bus gimbal +/-30 deg on 1 m arm (CM shift)", fontsize=9.5, color=P.INK2)
    ax.axhline(rcd["solar_cruiser_roll_req"], color=P.MUTED, lw=1.2)
    ax.text(1, rcd["solar_cruiser_roll_req"] * 1.15, "Solar Cruiser roll requirement 2.96e-5 N m", fontsize=9.5, color=P.INK2)
    ax.axhline(rcd["disturbance_cmcp"]["5 cm"], color=P.MUTED, lw=1.0)
    ax.text(40, rcd["disturbance_cmcp"]["5 cm"] * 1.15, "disturbance: 5 cm CM-CP offset", fontsize=9.5, color=P.INK2)
    ax.set_xlabel("Sun incidence angle (deg)"); ax.set_ylabel("control torque (N m), CR-S 1,653 m^2 sail")
    ax.set_xlim(0, 80); ax.set_ylim(1e-6, 2e-2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=9, ncol=3)
    P.title(ax, "Propellant-free momentum management: electrochromic RCDs vs mass shift")
    out.append(P.save(f, "dt_momentum_actuators.png"))   # (legend below axes)

    f, ax = P.fig(size=(10, 4.4))
    labs = ["Fixed-area sail", "Retractable / reefable sail", "Hybrid CR-H (sail + SEP)"]
    vals = [100 * reef["fixed_area_sail"], 100 * reef["reefable_sail"], 100 * reef["hybrid_CR-H"]]
    ax.barh(labs, vals, color=[P.MUTED, P.BLUE, P.ORANGE], height=0.5)
    for i, v in enumerate(vals):
        ax.text(v + 1, i, f"{v:.0f} %", va="center", fontsize=11, color=P.INK)
    ax.set_xlim(0, 110); ax.invert_yaxis()
    ax.set_xlabel("% of random control demands (any direction, |a| <= a_c) met exactly")
    ax.grid(axis="y", visible=False)
    P.title(ax, "Throttling by partial retraction turns the force 'bubble' surface into a volume")
    out.append(P.save(f, "dt_reefing.png"))
    return out


def run():
    with Timer("Design trades"):
        acA = ac_vs_area(); th = thermal(); rcd = rcd_torque(); reef = reefing_feasibility()
        figs_ = figs(acA, th, rcd, reef)
        ss = {k: sail_system_mass(D[k].area_m2, D[k].material) for k in ("ACS3", "SC", "CR-A")}
        spin = {k: sail_system_mass(D[k].area_m2, D[k].material, "spin") for k in ("ACS3", "SC", "CR-A")}
        res = {"thermal_peak_C": {k: float(np.max(v)) - 273.15 for k, v in th.items() if k not in ("cone",) and not k.endswith("eff")},
               "efficiency": {m.name: m.front.efficiency for m in (S.AL_CP1, S.AL_PEN_CR, S.AL_AL_CP1, S.AL_MYLAR)},
               "rcd": {"arm_m": rcd["arm_m"], "pitch_2pct_at_0": rcd["pitch_0.02"][0], "pitch_2pct_at_40": rcd["pitch_0.02"][40],
                       "roll_2pct_at_17": float(np.nan_to_num(rcd["roll_0.02"][17])), "amt_10cm": rcd["amt_10cm"],
                       "gimbal_30deg": rcd["gimbal_30deg_1m_bus60pct"], "disturbance": rcd["disturbance_cmcp"],
                       "sc_roll_req": rcd["solar_cruiser_roll_req"], "momentum_per_day_5cm_Nms": rcd["momentum_per_day_5cm_Nms"]},
               "reefing": reef, "sail_system_mass_rigid": ss, "sail_system_mass_spin": spin,
               "figures": [p.split("/")[-1] for p in figs_]}
        save_results("design_trades", res)
        return res


if __name__ == "__main__":
    import json
    print(json.dumps({k: v for k, v in run().items() if k != "figures"}, indent=1))
