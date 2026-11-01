"""Heritage sailcraft, study design points and a parametric mass model.

Mass model (square sail, four booms on the diagonals):
    m_sail_sys = sigma_membrane*A + lambda_boom(L)*4L + m_deployer(A) [+ options]
    L = sqrt(A/2) (half-diagonal), lambda_boom = 23.4 g/m (L/7 m)^0.7
calibrated on ACS3 (7.7 kg SBS for 80 m^2, 0.164 kg per 7 m boom) and the
Solar Cruiser quadrant (6.91 kg for 1653 m^2).  SEP sizing follows Ceriotti &
McInnes (2011): P = T Isp g0 / (2 eta), thruster+PPU 25 kg/kW, gimbal 30 % of
thruster mass, tankage 10 % of propellant, arrays 70 W/kg.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from . import sail as S
from .constants import P_SRP_1AU, G0


@dataclass
class Design:
    key: str
    name: str
    mass_kg: float
    area_m2: float
    material: S.SailMaterial = S.AL_CP1
    sep_thrust_mN: float = 0.0
    isp_s: float = 0.0
    sep_power_W: float = 0.0
    propellant_kg: float = 0.0
    gimbal_deg: float = 0.0
    booms: str = "rigid"            # 'rigid' or 'spin'
    rcd: bool = False
    retractable: bool = False
    heritage: bool = False
    note: str = ""

    @property
    def a_c_mm(self):
        return P_SRP_1AU * self.area_m2 / self.mass_kg * self.material.front.total * 1e3

    @property
    def a_c_ideal_mm(self):
        return 2 * P_SRP_1AU * self.area_m2 / self.mass_kg * 1e3

    @property
    def a_sep_mm(self):
        return self.sep_thrust_mN * 1e-3 / self.mass_kg * 1e3

    @property
    def sail_loading_gm2(self):
        return self.mass_kg / self.area_m2 * 1e3

    @property
    def sep_dv_kms(self):
        if self.propellant_kg <= 0 or self.isp_s <= 0:
            return 0.0
        return self.isp_s * G0 * math.log(self.mass_kg / (self.mass_kg - self.propellant_kg)) / 1e3

    def summary(self):
        d = {"key": self.key, "name": self.name, "mass_kg": self.mass_kg, "area_m2": self.area_m2,
             "material": self.material.name, "a_c_mm_s2": round(self.a_c_mm, 4),
             "a_c_ideal_mm_s2": round(self.a_c_ideal_mm, 4), "sail_loading_g_m2": round(self.sail_loading_gm2, 1),
             "sep_thrust_mN": self.sep_thrust_mN, "isp_s": self.isp_s, "sep_power_W": self.sep_power_W,
             "propellant_kg": self.propellant_kg, "a_sep_mm_s2": round(self.a_sep_mm, 4),
             "sep_dv_km_s": round(self.sep_dv_kms, 2), "gimbal_deg": self.gimbal_deg,
             "booms": self.booms, "rcd": self.rcd, "retractable": self.retractable,
             "heritage": self.heritage, "note": self.note}
        return d


HERITAGE = [
    Design("LS2", "LightSail 2 (2019)", 5.0, 32.0, S.AL_MYLAR, heritage=True,
           note="TRAC metallic booms; 720 km LEO; AO degradation observed"),
    Design("ACS3", "ACS3 (2024)", 16.0, 80.0, S.AL_PEN_CR, heritage=True,
           note="7 m DCB composite booms; quoted effective a_c 0.045 mm/s^2 (ideal formula)"),
    Design("NEAS", "NEA Scout (2022)", 14.0, 86.0, S.AL_CP1, heritage=True,
           note="6U, TRAC booms 6.8 m, AMT + cold-gas RCS; launched on Artemis I"),
    Design("SC", "Solar Cruiser (TRL-6 sail)", 111.0, 1653.0, S.AL_CP1, rcd=True, heritage=True,
           note="ESPA Grande, 29.5 m TRAC booms, AMT pitch/yaw, RCD roll"),
]

# Study design points for DARPA Cattle Run
STUDY = [
    Design("CR-S", "Cattle Run conventional sail", 111.0, 1653.0, S.AL_CP1, rcd=True,
           note="Solar Cruiser-derived sail system; RCD roll + AMT pitch/yaw"),
    Design("CR-H", "Cattle Run hybrid (gimballed SEP)", 131.0, 1653.0, S.AL_CP1, sep_thrust_mN=20.0,
           isp_s=1500.0, sep_power_W=350.0, propellant_kg=6.0, gimbal_deg=30.0, rcd=True,
           note="+20 kg SEP module (20 mN Hall, 350 W, 6 kg Xe/Kr), 2-axis +/-30 deg gimbal"),
    Design("CR-HR", "Cattle Run hybrid, retractable sail", 136.0, 1653.0, S.AL_CP1, sep_thrust_mN=20.0,
           isp_s=1500.0, sep_power_W=350.0, propellant_kg=6.0, gimbal_deg=30.0, rcd=True,
           retractable=True, note="+5 kg motorised re-spooling deployer"),
    Design("CR-A", "Advanced sail (DCB-II, 1 um CP1)", 120.0, 4000.0, S.CP1_THIN, rcd=True,
           note="Far-term: 45 m booms, 1 um film (sigma_total 30 g/m^2)"),
]


def boom_linear_density_gm(L_m):
    return 23.4 * (max(L_m, 1.0) / 7.0) ** 0.7


def sail_system_mass(area_m2, material=S.AL_CP1, booms="rigid", rcd_frac=0.0, retractable=False):
    L = math.sqrt(area_m2 / 2.0)
    membrane = material.areal_density_gm2 * area_m2 / 1e3
    if booms == "rigid":
        boom = 4 * L * boom_linear_density_gm(L) / 1e3
        deployer = 5.5 + 0.008 * area_m2
    else:   # spin-deployed: no booms, tip masses, thicker film for hoop stress, lighter deployer
        membrane *= 1.2
        boom = 1.0 + 0.002 * area_m2
        deployer = 3.0 + 0.004 * area_m2
    rcd = rcd_frac * area_m2 * (S.RCD_AREAL_DENSITY_GM2 - material.areal_density_gm2) / 1e3
    rcd += 0.5 if rcd_frac > 0 else 0.0
    retr = 0.3 * deployer if retractable else 0.0
    return {"membrane": membrane, "booms": boom, "deployer": deployer, "rcd": rcd, "retraction": retr,
            "total": membrane + boom + deployer + rcd + retr}


def sep_system_mass(thrust_mN, isp_s, propellant_kg, eta=0.55, k_kw=25.0, array_w_per_kg=70.0,
                    gimbal_frac=0.3):
    P = thrust_mN * 1e-3 * isp_s * G0 / (2 * eta)        # W
    thruster = k_kw * P / 1e3
    gimbal = gimbal_frac * thruster
    tank = 0.1 * propellant_kg
    arrays = P / array_w_per_kg
    return {"power_W": P, "thruster_ppu": thruster, "gimbal": gimbal, "tank": tank, "arrays": arrays,
            "total_dry": thruster + gimbal + tank + arrays}


def characteristic_acc_mm(area_m2, total_mass_kg, material=S.AL_CP1):
    return P_SRP_1AU * area_m2 / total_mass_kg * material.front.total * 1e3


def design_from_budget(area_m2, bus_payload_kg, material=S.AL_CP1, booms="rigid", **kw):
    ss = sail_system_mass(area_m2, material, booms, **kw)
    m = bus_payload_kg + ss["total"]
    return m, characteristic_acc_mm(area_m2, m, material), ss


def export(path):
    """Write all design points (heritage + study) with derived performance to JSON."""
    import json
    data = {d.key: d.summary() for d in HERITAGE + STUDY}
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    return data
