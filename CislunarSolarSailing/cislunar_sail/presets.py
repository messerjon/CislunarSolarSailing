"""Reference spacecraft. Heritage values are approximate public figures, rounded.

The Cattle Run concept presets share a 60 kg bus (ESPA-class) so sail-vs-hybrid
comparisons isolate the propulsion choice.
"""
import dataclasses

from .spacecraft import SEP, Sail, Spacecraft

# --- heritage (for calibration plots) --------------------------------------
HERITAGE = {
    "LightSail 2": Spacecraft("LightSail 2", bus_mass=4.4, sail=Sail(32, "Mylar_4.5um", double_sided=True, boom_linear_density=0.02), bus_drag_area=0.03),
    "NEA Scout": Spacecraft("NEA Scout", bus_mass=12.5, sail=Sail(86, "CP1_2.5um", boom_linear_density=0.02), bus_drag_area=0.06),
    "ACS3": Spacecraft("ACS3", bus_mass=14.5, sail=Sail(80, "PEN_2.5um", boom_linear_density=0.02), bus_drag_area=0.06),
    "IKAROS": Spacecraft("IKAROS", bus_mass=290.0, sail=Sail(196, "Kapton_7.5um", structure="spin"), bus_drag_area=2.0),
    "Solar Cruiser": Spacecraft("Solar Cruiser", bus_mass=60.0, sail=Sail(1653, "CP1_2.5um", boom_linear_density=0.10), bus_drag_area=1.0),
}

# --- Cattle Run trade-space presets ----------------------------------------
BUS = 60.0  # kg


def conventional(ac=0.2e-3, **sail_kw):
    sc = Spacecraft("Conventional sail", BUS, Sail(**sail_kw))
    return sc.with_ac(ac)


def hybrid(ac=0.2e-3, thrust=10e-3, isp=1500.0, gimbal_deg=0.0, propellant=8.0, **sail_kw):
    name = "Hybrid (gimballed SEP)" if gimbal_deg > 0 else "Hybrid (fixed SEP)"
    sep = SEP(thrust=thrust, isp=isp, power=thrust / 10e-3 * 250, gimbal_max_deg=gimbal_deg,
              propellant=propellant, dry_mass=4.0 + (1.5 if gimbal_deg > 0 else 0.0))
    sc = Spacecraft(name, BUS, Sail(**sail_kw), sep)
    return sc.with_ac(ac)


def sep_only(thrust=10e-3, isp=1500.0, propellant=8.0):
    sep = SEP(thrust=thrust, isp=isp, gimbal_max_deg=180.0, propellant=propellant, dry_mass=4.0)
    return Spacecraft("SEP only", BUS, None, sep)


def concept_set(ac=0.2e-3):
    """The four architectures the outline asks to compare."""
    return [
        conventional(ac),
        dataclasses.replace(conventional(ac, structure="spin"), name="Spin-stabilised sail"),
        hybrid(ac, gimbal_deg=0.0),
        hybrid(ac, gimbal_deg=30.0),
    ]


def architectures(ac=0.2e-3, include_spin=True, include_retract=False):
    """All architecture variants named in the objectives, at equal characteristic acceleration."""
    out = [
        conventional(ac),
        dataclasses.replace(conventional(ac, double_sided=True), name="Double-sided sail"),
        hybrid(ac, gimbal_deg=0.0),
        hybrid(ac, gimbal_deg=30.0),
    ]
    if include_spin:
        out.append(dataclasses.replace(conventional(ac, structure="spin"), name="Spin-stabilised sail"))
    if include_retract:
        out.append(dataclasses.replace(hybrid(ac, gimbal_deg=30.0, retractable=True), name="Retractable hybrid"))
    return out
