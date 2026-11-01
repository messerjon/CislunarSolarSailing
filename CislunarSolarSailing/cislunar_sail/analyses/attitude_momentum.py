"""Attitude & momentum management: electrochromic (reflectivity-control) films vs
gimballed-bus centre-of-mass translation (CMT), against centre-of-pressure offsets.

Disturbance: tau_d = F_srp * delta, delta = epsilon * L (CP/CM offset as % of sail side).
Electrochromic films (RCDs) on opposite edges switch between specular (r~0.88) and
diffuse/absorbing states; normal-force coefficient change dCn per unit area.
  tau_rcd = P * (f A / 2) * dCn * cos^2(alpha) * 0.45 L
CMT: bus of mass m_b on a gimbal arm l shifts the CM by (m_b/m) l sin(gamma):
  tau_cmt = F_srp * (m_b/m) * l * sin(gamma)
Both scale with F_srp (i.e. with cos^2 alpha), so authority ratios are attitude-independent.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .. import constants as C
from .. import plotting as P
from .. import presets
from .common import save_table


def run():
    sc = presets.conventional(0.2e-3)
    L, A, m = sc.sail.side, sc.sail.area, sc.mass
    coeff = sc.characteristic_acceleration * m / (C.SOLAR_PRESSURE_1AU * A)  # normal-force coefficient (~1.8)
    F = sc.characteristic_acceleration * m
    eps = np.linspace(0.0005, 0.02, 60)  # 0.05% .. 2% of side
    rows = []
    for e in [0.0025, 0.005, 0.01]:
        tau = F * e * L
        h_day = tau * C.DAY
        rcd = {}
        for dcn in (0.3, 0.5, 0.8):
            f_req = tau / (C.SOLAR_PRESSURE_1AU * A / 2 * dcn * 0.45 * L)
            rcd[dcn] = f_req
        for arm in (0.5, 1.0, 2.0):
            s = e * L * m / (sc.bus_mass * arm)
            g = math.degrees(math.asin(s)) if s <= 1 else float("nan")
            rows.append(dict(cp_offset_pct=e * 100, disturbance_mNm=tau * 1e3, momentum_Nms_per_day=h_day,
                             gimbal_arm_m=arm, cmt_gimbal_deg_required=g,
                             rcd_area_frac_dCn0p3=rcd[0.3], rcd_area_frac_dCn0p5=rcd[0.5], rcd_area_frac_dCn0p8=rcd[0.8]))
    df = pd.DataFrame(rows)
    save_table(df, "attitude_momentum")

    f, axes = P.fig(1, 2)
    ax = axes[0]
    for k, dcn in enumerate((0.3, 0.5, 0.8)):
        frac = F * eps * L / (C.SOLAR_PRESSURE_1AU * A / 2 * dcn * 0.45 * L)
        ax.plot(eps * 100, frac * 100, color=P.SERIES[k], label=f"ΔCn = {dcn} (switching contrast)")
    ax.set_xlabel("CP–CM offset (% of sail side)")
    ax.set_ylabel("Sail area covered by electrochromic film (%)")
    ax.set_title("Electrochromic film needed")
    ax.legend()
    ax = axes[1]
    for k, arm in enumerate((0.5, 1.0, 2.0)):
        s = eps * L * m / (sc.bus_mass * arm)
        g = np.degrees(np.arcsin(np.where(s <= 1, s, np.nan)))
        ax.plot(eps * 100, g, color=P.SERIES[k + 3], label=f"gimbal arm {arm} m")
    ax.set_xlabel("CP–CM offset (% of sail side)")
    ax.set_ylabel("Bus gimbal angle needed (deg)")
    ax.set_title("Gimballed-bus CM shift needed")
    ax.legend()
    f.suptitle(f"Trimming a {L:.0f} m sail (a_c 0.2 mm/s², {m:.0f} kg): 0.5% offset = {F*0.005*L*1e3:.1f} mN·m, "
               f"{F*0.005*L*C.DAY:.0f} N·m·s/day if uncorrected", x=0.02, ha="left", fontsize=19, fontweight="bold")
    P.save(f, "attitude_trim_authority", "attitude")
    return df


if __name__ == "__main__":
    print(run().to_string())
