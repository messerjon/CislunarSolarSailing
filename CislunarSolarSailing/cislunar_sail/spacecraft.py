"""Spacecraft, sail-material and SEP definitions plus the batched tensor form.

Sail force uses the McInnes non-ideal optical model:
    F = P A [ Fn(c) n + Ft(c) t ]
    Fn = (1 + r s) c^2 + Bf (1 - s) r c + (1 - r)(ef Bf - eb Bb)/(ef + eb) c
    Ft = (1 - r s) c sqrt(1 - c^2)
with c = cos(cone angle) = n . u (u = Sun -> spacecraft unit vector) and t the
in-plane transverse unit vector. A sail lit from behind uses its back-side optics
(a single-sided sail has a chromium back; a double-sided sail is coated on both).

Body convention: +Z is the sail normal on the front (reflective) face.
The SEP thrust axis is `sep_axis_sign * Z` and can be gimballed `gimbal_max_deg`
from that axis. Default sign -1: thrusting toward the front face (sunward when
the sail faces the Sun) so the plume exhausts away from the film.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import torch

from . import backend
from . import constants as C


@dataclass(frozen=True)
class Optics:
    r: float   # reflectivity
    s: float   # specular fraction
    B: float   # non-Lambertian coefficient of the lit face
    eps: float # emissivity of the lit face


@dataclass(frozen=True)
class SailMaterial:
    name: str
    areal_density: float  # kg/m^2, film + coatings + seams
    front: Optics
    back: Optics
    max_temp_c: float = 250.0


AL = Optics(r=0.88, s=0.94, B=0.79, eps=0.05)   # aluminised face (McInnes)
CR = Optics(r=0.60, s=0.30, B=0.55, eps=0.64)   # chromium back face

MATERIALS = {
    "PEN_2.5um": SailMaterial("Al/PEN 2.5 um (ACS3-class)", 4.0e-3, AL, CR, 200),
    "CP1_2.5um": SailMaterial("Al/CP1 2.5 um (NEA Scout / Solar Cruiser-class)", 4.3e-3, AL, CR, 250),
    "Mylar_4.5um": SailMaterial("Al/Mylar 4.5 um (LightSail-class)", 6.8e-3, AL, CR, 120),
    "Kapton_7.5um": SailMaterial("Al/polyimide 7.5 um (IKAROS-class)", 11.5e-3, AL, CR, 300),
}


@dataclass
class Sail:
    area: float = 1653.0                 # m^2
    material: str = "CP1_2.5um"
    double_sided: bool = False
    structure: str = "booms"             # "booms" (3-axis) or "spin" (yo-yo deployed, spin-stabilised)
    boom_linear_density: float = 0.10    # kg/m for rigid/TRAC composite booms
    spin_hardware_fraction: float = 0.15 # tip masses + yo-yo despin, fraction of film mass
    retractable: bool = False
    retract_mass_penalty: float = 1.5    # kg extra for a re-stowable deployer
    electrochromic_fraction: float = 0.0 # fraction of sail area covered by reflectivity-control film
    electrochromic_areal_density: float = 30e-3  # kg/m^2 (IKAROS RCDs ~ this order)

    @property
    def mat(self) -> SailMaterial:
        return MATERIALS[self.material]

    @property
    def side(self) -> float:
        return math.sqrt(self.area)

    @property
    def mass(self) -> float:
        film = self.area * self.mat.areal_density
        if self.structure == "booms":
            struct = 4 * (self.side / math.sqrt(2)) * self.boom_linear_density
        else:
            struct = self.spin_hardware_fraction * film
        rcd = self.electrochromic_fraction * self.area * self.electrochromic_areal_density
        return film + struct + rcd + (self.retract_mass_penalty if self.retractable else 0.0)

    @property
    def back_optics(self) -> Optics:
        return self.mat.front if self.double_sided else self.mat.back


@dataclass
class SEP:
    thrust: float = 0.0          # N
    isp: float = 1500.0          # s
    power: float = 0.0           # W (informational)
    gimbal_max_deg: float = 0.0  # 0 = fixed to bus
    axis_sign: float = -1.0
    propellant: float = 0.0      # kg
    dry_mass: float = 0.0        # kg thruster + PPU + tank + extra array

    @property
    def enabled(self) -> bool:
        return self.thrust > 0


@dataclass
class Spacecraft:
    name: str
    bus_mass: float                     # kg, everything except sail and SEP
    sail: Sail | None = field(default_factory=Sail)
    sep: SEP = field(default_factory=SEP)
    bus_drag_area: float = 1.0          # m^2
    cd: float = 2.2

    @property
    def mass(self) -> float:
        m = self.bus_mass + self.sep.dry_mass + self.sep.propellant
        return m + (self.sail.mass if self.sail else 0.0)

    @property
    def characteristic_acceleration(self) -> float:
        """Sail acceleration (m/s^2) at 1 AU, Sun-facing, with the optical model."""
        if self.sail is None:
            return 0.0
        return C.SOLAR_PRESSURE_1AU * self.sail.area * normal_force_coeff(self.sail.mat.front, self.sail.back_optics, 1.0) / self.mass

    @property
    def sep_acceleration(self) -> float:
        return self.sep.thrust / self.mass

    def with_ac(self, ac: float) -> "Spacecraft":
        """Copy with the sail area resized (sail mass included) to hit characteristic acceleration `ac`."""
        sc = dataclasses.replace(self, sail=dataclasses.replace(self.sail))
        for _ in range(60):  # fixed-point on area since sail mass depends on area
            coeff = normal_force_coeff(sc.sail.mat.front, sc.sail.back_optics, 1.0)
            sc.sail.area = ac * sc.mass / (C.SOLAR_PRESSURE_1AU * coeff)
        if abs(sc.characteristic_acceleration - ac) > 1e-3 * ac:
            raise ValueError(f"{self.name}: a_c={ac*1e3:.2f} mm/s^2 unreachable (sail mass dominates)")
        return sc

    def summary(self) -> dict:
        d = dict(name=self.name, mass_kg=round(self.mass, 2), bus_kg=self.bus_mass,
                 ac_mm_s2=round(self.characteristic_acceleration * 1e3, 4),
                 sep_mm_s2=round(self.sep_acceleration * 1e3, 4))
        if self.sail:
            d.update(sail_area_m2=round(self.sail.area, 1), sail_side_m=round(self.sail.side, 1),
                     sail_mass_kg=round(self.sail.mass, 2), material=self.sail.mat.name,
                     double_sided=self.sail.double_sided, structure=self.sail.structure,
                     retractable=self.sail.retractable)
        if self.sep.enabled:
            d.update(sep_thrust_mN=self.sep.thrust * 1e3, sep_isp_s=self.sep.isp,
                     gimbal_deg=self.sep.gimbal_max_deg, propellant_kg=self.sep.propellant)
        return d


def normal_force_coeff(front: Optics, back: Optics, c: float) -> float:
    return ((1 + front.r * front.s) * c * c + front.B * (1 - front.s) * front.r * c
            + (1 - front.r) * (front.eps * front.B - back.eps * back.B) / (front.eps + back.eps) * c)


# ---------------------------------------------------------------------------
# Batched tensor representation
# ---------------------------------------------------------------------------
class Batch:
    """Per-sample spacecraft parameters as tensors (shape [B])."""

    FIELDS = ("pa_over_m_area", "mass0", "front", "back", "sep_thrust", "sep_mdot", "gimbal",
              "sep_axis", "spin", "retract", "bus_cdA", "sail_cdA", "prop0")

    def __init__(self, craft: list[Spacecraft]):
        t = backend.tensor
        self.craft = craft
        self.names = [c.name for c in craft]
        self.B = len(craft)
        area = [c.sail.area if c.sail else 0.0 for c in craft]
        self.area = t(area)
        self.mass0 = t([c.mass for c in craft])

        def opt(o: Optics, o_other: Optics):
            # [r, s, B_lit, B_other, eps_lit, eps_other]
            return [o.r, o.s, o.B, o_other.B, o.eps, o_other.eps]

        fr, bk = [], []
        for c in craft:
            if c.sail:
                f, b = c.sail.mat.front, c.sail.back_optics
            else:
                f = b = Optics(0, 0, 0, 1)
            fr.append(opt(f, b))
            bk.append(opt(b, f))
        self.front = t(fr)
        self.back = t(bk)
        self.sep_thrust = t([c.sep.thrust for c in craft])
        self.sep_mdot = t([c.sep.thrust / (C.G0 * c.sep.isp) if c.sep.enabled else 0.0 for c in craft])
        self.gimbal = t([math.radians(c.sep.gimbal_max_deg) for c in craft])
        self.sep_axis = t([c.sep.axis_sign for c in craft])
        self.spin = torch.tensor([bool(c.sail and c.sail.structure == "spin") for c in craft], device=backend.device())
        self.retract = torch.tensor([bool(c.sail and c.sail.retractable) for c in craft], device=backend.device())
        self.bus_cdA = t([c.cd * c.bus_drag_area for c in craft])
        self.sail_cdA = t([c.cd * a for c, a in zip(craft, area)])
        self.prop0 = t([c.sep.propellant for c in craft])
        self.dry_mass = self.mass0 - self.prop0

    def subset(self, idx):
        """Shallow copy restricted to batch indices `idx` (tensor)."""
        sub = object.__new__(Batch)
        for k, v in self.__dict__.items():
            if torch.is_tensor(v) and v.dim() >= 1 and v.shape[0] == self.B:
                sub.__dict__[k] = v[idx]
            else:
                sub.__dict__[k] = v
        il = idx.tolist()
        sub.craft = [self.craft[i] for i in il]
        sub.names = [self.names[i] for i in il]
        sub.B = len(il)
        return sub


def fibonacci_sphere(k: int) -> torch.Tensor:
    i = torch.arange(k, dtype=backend.dtype(), device=backend.device()) + 0.5
    phi = torch.acos(1 - 2 * i / k)
    theta = math.pi * (1 + 5 ** 0.5) * i
    return torch.stack((torch.cos(theta) * torch.sin(phi), torch.sin(theta) * torch.sin(phi), torch.cos(phi)), -1)


def _expand(x, like):
    """Reshape a per-sample [B] or [B, F] tensor to broadcast against `like` [B, ..., 3]."""
    extra = like.dim() - 2  # dims between batch and the trailing xyz axis
    if x.dim() == 1:
        return x.view(x.shape[0], *([1] * extra))
    return x.view(x.shape[0], *([1] * extra), x.shape[-1])


def sail_force_per_area(n, u, front, back):
    """Sail force divided by (P * A), shape [..., 3].

    n: attitude normal (body +Z) [B, ..., 3]; u: Sun->s/c unit vector broadcastable to n;
    front/back: [B, 6] optics tables.
    """
    c = (n * u).sum(-1)
    lit_back = c < 0
    nn = torch.where(lit_back[..., None], -n, n)
    c = c.abs()
    fo = _expand(front, n)
    bo = _expand(back, n)
    o = torch.where(lit_back[..., None], bo, fo)
    r, s, b_lit, b_oth, e_lit, e_oth = o.unbind(-1)
    fn = (1 + r * s) * c * c + b_lit * (1 - s) * r * c + (1 - r) * (e_lit * b_lit - e_oth * b_oth) / (e_lit + e_oth) * c
    tvec = u - c[..., None] * nn
    tnorm = tvec.norm(dim=-1, keepdim=True)
    tvec = tvec / tnorm.clamp_min(1e-12)
    ft = (1 - r * s) * c * (1 - c * c).clamp_min(0).sqrt()
    return fn[..., None] * nn + ft[..., None] * tvec


def sep_direction(axis, d, gimbal):
    """Best thrust direction within a cone of half-angle `gimbal` around `axis`, toward unit `d`."""
    cosang = (axis * d).sum(-1, keepdim=True).clamp(-1, 1)
    w = d - cosang * axis
    wn = w.norm(dim=-1, keepdim=True)
    w = torch.where(wn > 1e-9, w / wn.clamp_min(1e-12), torch.zeros_like(w))
    g = gimbal
    inside = torch.acos(cosang) <= g[..., None]
    rotated = torch.cos(g)[..., None] * axis + torch.sin(g)[..., None] * w
    return torch.where(inside, d, rotated)
