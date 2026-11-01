"""Force-environment pieces shared by the propagators (all batched torch)."""
import math

import torch

from . import constants as C

# Approximate thermospheric density (kg/m^3) at solar minimum / moderate / maximum.
# Moderate column is Vallado's exponential reference; min/max are rounded from
# NRLMSISE-00 profiles (F10.7 ~ 70 / 150 / 250). Adequate for drag-vs-SRP
# crossover trades; replace with MSIS for detailed lifetime work.
_ATM_ALT_KM = [300, 400, 500, 600, 700, 800, 900, 1000, 1250, 1500]
_ATM = {
    "min":      [1.0e-11, 1.0e-12, 1.6e-13, 3.2e-14, 9.0e-15, 3.5e-15, 1.8e-15, 1.0e-15, 4.0e-16, 2.0e-16],
    "moderate": [2.4e-11, 3.7e-12, 7.0e-13, 1.5e-13, 3.6e-14, 1.2e-14, 5.2e-15, 3.0e-15, 1.0e-15, 4.0e-16],
    "max":      [5.5e-11, 1.1e-11, 3.0e-12, 9.0e-13, 3.0e-13, 1.1e-13, 4.5e-14, 2.0e-14, 5.0e-15, 1.5e-15],
}


def atmosphere_density(alt_m, level="moderate"):
    """Log-linear interpolation of the table; exponential extrapolation outside it."""
    alt_km = alt_m / 1e3
    xs = torch.tensor(_ATM_ALT_KM, dtype=alt_m.dtype, device=alt_m.device)
    ys = torch.log(torch.tensor(_ATM[level], dtype=alt_m.dtype, device=alt_m.device))
    idx = torch.searchsorted(xs, alt_km.clamp(xs[0], xs[-1]).contiguous()).clamp(1, len(xs) - 1)
    x0, x1, y0, y1 = xs[idx - 1], xs[idx], ys[idx - 1], ys[idx]
    slope = (y1 - y0) / (x1 - x0)
    return torch.exp(y0 + slope * (alt_km - x0))


def cylindrical_shadow(r_sc, r_body, radius, sun_unit):
    """1 if sunlit, 0 if inside the body's cylindrical shadow. sun_unit points toward the Sun."""
    rel = r_sc - r_body
    along = (rel * sun_unit).sum(-1)
    perp2 = (rel * rel).sum(-1) - along * along
    return ~((along < 0) & (perp2 < radius * radius))


def j2_accel(r, mu, radius, j2):
    """J2 acceleration with the body's pole along +z."""
    x, y, z = r.unbind(-1)
    r2 = (r * r).sum(-1)
    rn = r2.sqrt()
    k = 1.5 * j2 * mu * radius * radius / (r2 * r2 * rn)
    zr2 = 5 * z * z / r2
    return torch.stack((k * x * (zr2 - 1), k * y * (zr2 - 1), k * z * (zr2 - 3)), -1)


def third_body_accel(r, r_body, mu):
    """Third-body perturbation (indirect term included)."""
    d = r_body - r
    dn = d.norm(dim=-1, keepdim=True)
    bn = r_body.norm(dim=-1, keepdim=True)
    return mu * (d / dn**3 - r_body / bn**3)
