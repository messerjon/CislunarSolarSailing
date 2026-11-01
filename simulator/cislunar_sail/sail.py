"""Solar-sail optical force model, material catalogue and optimal steering.

Force model (McInnes 1999, Eq. 2.56; Rios-Reyes & Scheeres 2005 coefficients):

    F = P A cos(a) [ a3 s + (a1 cos(a) + a2) n ]

with s the unit vector of photon travel (Sun -> sail), n the sail normal on the
lit face (n . s = cos(a) >= 0) and

    a1 = 2 r s_p,  a2 = B_f (1 - s_p) r + (1 - r)(e_f B_f - e_b B_b)/(e_f + e_b),
    a3 = 1 - r s_p.

``r`` total reflectivity, ``s_p`` specular fraction, ``e`` emissivities, ``B``
non-Lambertian coefficients. An ideal sail has a1 = 2, a2 = a3 = 0.

Throughout the simulator the *characteristic acceleration* a_c is the actual
acceleration of the (non-ideal) sail at 1 AU when its lit face is normal to the
Sun, i.e. a_c = (P A / m)(a1 + a2 + a3). This matches how flight projects quote
it (e.g. ACS3 "effective a_c = 0.045 mm/s^2").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import numpy as np

from .constants import P_SRP_1AU, SIGMA_SB, SOLAR_FLUX_1AU


@dataclass(frozen=True)
class FaceOptics:
    r: float        # total reflectivity
    s: float        # specular fraction of reflected light
    eps_f: float    # emissivity of this (lit) face
    eps_b: float    # emissivity of the opposite face
    B_f: float = 2.0 / 3.0
    B_b: float = 2.0 / 3.0

    @property
    def a1(self):
        return 2.0 * self.r * self.s

    @property
    def a2(self):
        e = self.eps_f + self.eps_b
        therm = 0.0 if e <= 0 else (1 - self.r) * (self.eps_f * self.B_f - self.eps_b * self.B_b) / e
        return self.B_f * (1 - self.s) * self.r + therm

    @property
    def a3(self):
        return 1.0 - self.r * self.s

    @property
    def total(self):
        """Force coefficient at zero cone angle (2.0 for an ideal sail)."""
        return self.a1 + self.a2 + self.a3

    @property
    def efficiency(self):
        return self.total / 2.0

    def flipped(self):
        """Same face viewed with emissivity roles swapped (used for double-sided)."""
        return FaceOptics(self.r, self.s, self.eps_b, self.eps_f, self.B_b, self.B_f)


@dataclass(frozen=True)
class SailMaterial:
    name: str
    front: FaceOptics
    back: FaceOptics
    areal_density_gm2: float          # membrane incl. seams/rip-stops/coatings
    max_temp_K: float                 # sustained-use limit of the substrate
    double_sided: bool = False
    note: str = ""

    def coeffs(self, back=False):
        f = self.back if back else self.front
        return f.a1, f.a2, f.a3


# ---------------------------------------------------------------------------
# Material catalogue (values from the study references; see report Table 2)
# ---------------------------------------------------------------------------
IDEAL = SailMaterial(
    "Ideal (perfect specular)", FaceOptics(1.0, 1.0, 0.5, 0.5), FaceOptics(1.0, 1.0, 0.5, 0.5),
    0.0, 1e9, True, "Reference model (a1=2, a2=a3=0)")

AL_CP1 = SailMaterial(
    "Al/CP1 2.5 um (NEA Scout, Solar Cruiser)",
    FaceOptics(0.88, 0.94, 0.05, 0.55, 0.79, 0.55),        # McInnes Table 2.1 (JPL square sail)
    FaceOptics(0.43, 0.54, 0.55, 0.05, 0.55, 0.79),
    4.18, 523.0, False,
    "Solar Cruiser quadrant mass 6.91 kg / 1653 m^2 (Maddox 2023); optics McInnes Table 2.1")

AL_PEN_CR = SailMaterial(
    "Al/PEN/Cr 2.1 um (ACS3)",
    FaceOptics(0.90, 0.74 / 0.90, 0.03, 0.60),             # Wilkie 2023 appendix: Al face
    FaceOptics(0.43, 0.23 / 0.43, 0.60, 0.03),             # Cr face
    4.25, 423.0, False,
    "ACS3 quadrant 85 g / 20 m^2 incl. hardware (Wilkie 2023)")

AL_MYLAR = SailMaterial(
    "Al/Mylar 4.5 um (LightSail 2)",
    FaceOptics(0.88, 0.94, 0.05, 0.34, 0.79, 0.55),
    FaceOptics(0.88, 0.94, 0.34, 0.05, 0.55, 0.79),
    6.4, 423.0, False, "Aluminised Mylar, TRAC booms (Betts 2023)")

AL_AL_CP1 = SailMaterial(
    "Al/CP1/Al double-sided 2.5 um",
    FaceOptics(0.88, 0.94, 0.05, 0.05, 0.79, 0.79),
    FaceOptics(0.88, 0.94, 0.05, 0.05, 0.79, 0.79),
    4.45, 523.0, True, "Both faces aluminised: symmetric thrust, no flip manoeuvres, runs hotter")

CP1_THIN = SailMaterial(
    "Al/CP1 1 um (advanced)",
    FaceOptics(0.88, 0.94, 0.05, 0.55, 0.79, 0.55),
    FaceOptics(0.43, 0.54, 0.55, 0.05, 0.55, 0.79),
    1.80, 523.0, False, "Mid-term thin-film target (Advances in Solar Sailing)")

# Reflectivity-control (electrochromic / PDLC) panel states, after Heaton 2023 and IKAROS
RCD_ON = FaceOptics(0.75, 0.85, 0.40, 0.40)    # specular state
RCD_OFF = FaceOptics(0.60, 0.10, 0.40, 0.40)   # diffuse / transmissive state
RCD_AREAL_DENSITY_GM2 = 40.0

MATERIALS = {m.name: m for m in (IDEAL, AL_CP1, AL_PEN_CR, AL_MYLAR, AL_AL_CP1, CP1_THIN)}


# ---------------------------------------------------------------------------
# Force evaluation
# ---------------------------------------------------------------------------
def meridian(face: FaceOptics, n=721):
    """Force 'bubble' meridian: components (along s, perpendicular to s) per unit
    P A / m for cone angles 0..90 deg."""
    a = np.linspace(0.0, np.pi / 2, n)
    c = np.cos(a)
    fn = c * (face.a1 * c + face.a2)
    f_s = c * face.a3 + fn * c
    f_p = fn * np.sin(a)
    return a, f_s, f_p


def max_force_cone_angle_deg(face: FaceOptics):
    """Largest angle between the force vector and the Sun line (deg)."""
    a, fs, fp = meridian(face, 9001)
    ok = (fs ** 2 + fp ** 2) > 1e-10
    return float(np.degrees(np.max(np.arctan2(fp[ok], fs[ok]))))


@lru_cache(maxsize=32)
def steering_table(face: FaceOptics, n_theta=1801, n_alpha=1801):
    """Locally optimal cone angle that maximises the force component along a
    direction at angle theta from the Sun line.  Returns (theta, alpha*, g*)
    with g* normalised by the zero-cone-angle force (so g*(0)=1)."""
    th = np.linspace(0.0, np.pi, n_theta)[:, None]
    al = np.linspace(0.0, np.pi / 2, n_alpha)[None, :]
    c = np.cos(al)
    g = c * (face.a3 * np.cos(th) + (face.a1 * c + face.a2) * np.cos(th - al))
    k = np.argmax(g, axis=1)
    gmax = g[np.arange(n_theta), k] / face.total
    amax = al[0, k]
    neg = gmax <= 0.0          # feather (edge-on) when nothing positive is possible
    amax = np.where(neg, np.pi / 2, amax)
    gmax = np.where(neg, 0.0, gmax)
    return th[:, 0], amax, gmax


def sail_accel(B, face_front: FaceOptics, face_back: FaceOptics, s_hat, n_front, a_c, lit=None):
    """Vectorised sail acceleration.

    s_hat   (...,3) unit vector Sun -> spacecraft (photon direction)
    n_front (...,3) unit normal of the front (reflective) face
    a_c     characteristic acceleration (scalar or (...)) in output units
    lit     optional (...) boolean/float illumination factor (0 in shadow)
    """
    c = B.dot(s_hat, n_front)
    cf = B.maximum(c, 0.0)
    cb = B.maximum(-c, 0.0)
    kf = 1.0 / face_front.total
    Ff = cf[..., None] * (face_front.a3 * s_hat + (face_front.a1 * cf + face_front.a2)[..., None] * n_front)
    Fb = cb[..., None] * (face_back.a3 * s_hat + (face_back.a1 * cb + face_back.a2)[..., None] * (-n_front))
    F = (Ff + Fb) * kf
    scale = a_c if not hasattr(a_c, "shape") or len(getattr(a_c, "shape", ())) == 0 else a_c[..., None]
    F = F * scale
    if lit is not None:
        F = F * lit[..., None]
    return F


def _perp_basis(B, s_hat, d_hat):
    """In-plane basis (e1 = s, e2 = component of d normal to s) and angle theta."""
    cs = B.dot(s_hat, d_hat)
    e2 = d_hat - cs[..., None] * s_hat
    nrm = B.norm(e2)
    # fallback perpendicular when d is (anti)parallel to s
    ref = B.zeros(s_hat.shape) + B.asarray([0.0, 0.0, 1.0])
    alt = B.cross(s_hat, ref)
    alt_n = B.norm(alt)
    ref2 = B.zeros(s_hat.shape) + B.asarray([1.0, 0.0, 0.0])
    alt = B.where((alt_n < 1e-6)[..., None], B.cross(s_hat, ref2), alt)
    alt = alt / B.norm(alt, keepdims=True)
    small = (nrm < 1e-9)[..., None]
    e2 = B.where(small, alt, e2 / B.maximum(nrm, 1e-12)[..., None])
    theta = B.arctan2(B.abs(B.dot(d_hat, e2)), cs)   # in [0, pi] (d . e2 >= 0 by construction)
    return e2, theta


def optimal_normal(B, face: FaceOptics, s_hat, d_hat, g_min=0.0):
    """Locally optimal sail normal maximising the force component along d_hat.

    Returns (n_hat, g) with g the achieved component normalised by a_c.  When
    the best achievable component is <= g_min the sail is feathered edge-on
    (normal perpendicular to both s and d) and g = 0.
    """
    th_tab, a_tab, g_tab = steering_table(face)
    e2, theta = _perp_basis(B, s_hat, d_hat)
    dth = th_tab[1] - th_tab[0]
    alpha = B.interp_uniform(theta, 0.0, dth, B.asarray(a_tab))
    g = B.interp_uniform(theta, 0.0, dth, B.asarray(g_tab))
    n = B.cos(alpha)[..., None] * s_hat + B.sin(alpha)[..., None] * e2
    feather = g <= g_min
    nf = B.cross(s_hat, e2)
    n = B.where(feather[..., None], nf, n)
    g = B.where(feather, 0.0, g)
    return n, g


def best_hybrid(B, face: FaceOptics, s_hat, d_hat, a_c, a_sep, gimbal_deg=180.0,
                both_sides=True, sep_policy="always", n_alpha=181, drag_k=None, v_hat=None,
                lit=None):
    """Brute-force in-plane search for the sail normal (and SEP pointing) that
    maximises the total acceleration component along d_hat.

    a_c, a_sep   scalars or (...) arrays (same units)
    gimbal_deg   SEP thrust may deviate from +/- sail normal by this angle
                 (>= 90 deg means effectively free pointing)
    sep_policy   'always' (SEP adds whenever it helps), 'fill' (SEP only when the
                 sail alone delivers < 5 % of a_c), or 'off'
    drag_k       optional (...) drag acceleration per unit projected-area fraction
                 (q C_D A / m), applied along -v_hat with |n . v_hat|
    lit          optional illumination factor (...)
    Returns dict with n_hat, a_sail, a_sep_vec, comp (component along d_hat).
    """
    import math
    e2, theta = _perp_basis(B, s_hat, d_hat)
    al = B.linspace(-math.pi / 2, math.pi / 2, n_alpha)              # (A,)
    ca, sa = B.cos(al), B.sin(al)
    cth, sth = B.cos(theta)[..., None], B.sin(theta)[..., None]      # (...,1)
    # sail force (in-plane coords along e1=s and e2) for alpha >= 0 part and mirrored
    cpos = B.maximum(ca, 0.0)
    fn = cpos * (face.a1 * cpos + face.a2)
    Fs = (cpos * face.a3 + fn * ca) / face.total                    # (A,)
    Fp = (fn * sa) / face.total
    ac = a_c if not hasattr(a_c, "shape") or len(getattr(a_c, "shape", ())) == 0 else a_c[..., None]
    if lit is not None:
        ac = ac * lit[..., None]
    comp_sail = ac * (Fs * cth + Fp * sth)                           # (...,A)
    total = comp_sail
    # normal unit vector in-plane: (ca, sa); angle between normal and d: cos = ca cth + sa sth
    cos_nd = ca * cth + sa * sth
    sin_nd = B.sqrt(B.maximum(1 - cos_nd ** 2, 0.0))
    G = math.radians(min(gimbal_deg, 180.0))
    sep_on = sep_policy != "off"
    if sep_on:
        asep = a_sep if not hasattr(a_sep, "shape") or len(getattr(a_sep, "shape", ())) == 0 else a_sep[..., None]
        if gimbal_deg >= 90.0:
            comp_sep = asep + 0 * cos_nd
        else:
            cG, sG = math.cos(G), math.sin(G)
            # axis +n : phi = angle(n, d);  axis -n : phi' = pi - phi
            c_plus = B.where(cos_nd >= cG, 1.0 + 0 * cos_nd, cos_nd * cG + sin_nd * sG)
            c_minus = B.where(-cos_nd >= cG, 1.0 + 0 * cos_nd, -cos_nd * cG + sin_nd * sG)
            best = B.maximum(c_plus, c_minus) if both_sides else c_plus
            comp_sep = asep * B.maximum(best, 0.0)
        if sep_policy == "fill":
            # SEP only where the sail alone is effectively "in irons" (< 5 % of a_c)
            sail_best = B.take_along(comp_sail, B.argmax(comp_sail, axis=-1)[..., None], axis=-1)
            need = sail_best < 0.05 * ac
            comp_sep = comp_sep * need
        total = total + comp_sep
    if drag_k is not None:
        cnv_1 = B.dot(s_hat, v_hat)[..., None]
        cnv_2 = B.dot(e2, v_hat)[..., None]
        proj = B.abs(ca * cnv_1 + sa * cnv_2)
        dvd = B.dot(v_hat, d_hat)[..., None]
        total = total - drag_k[..., None] * proj * dvd
    k = B.argmax(total, axis=-1)
    kk = k[..., None]
    comp = B.take_along(total, kk, axis=-1)[..., 0]
    alpha = al[k]
    n_hat = B.cos(alpha)[..., None] * s_hat + B.sin(alpha)[..., None] * e2
    out = {"n_hat": n_hat, "comp": comp, "alpha": alpha}
    out["comp_sail"] = B.take_along(comp_sail, kk, axis=-1)[..., 0]
    if sep_on:
        out["comp_sep"] = B.take_along(comp_sep, kk, axis=-1)[..., 0]
    return out


def equilibrium_temperature_K(face: FaceOptics, cone_deg, r_au=1.0):
    """Radiative-equilibrium membrane temperature for the lit face."""
    c = np.cos(np.radians(cone_deg))
    w = SOLAR_FLUX_1AU / r_au ** 2
    return ((1 - face.r) * w * np.maximum(c, 0) / (SIGMA_SB * (face.eps_f + face.eps_b))) ** 0.25


def ideal_characteristic_acc(area_m2, mass_kg, r_au=1.0):
    return 2 * P_SRP_1AU * area_m2 / mass_kg / r_au ** 2


def characteristic_acc(material: SailMaterial, area_m2, mass_kg):
    """Non-ideal characteristic acceleration (m/s^2) of the front face."""
    return P_SRP_1AU * area_m2 / mass_kg * material.front.total
