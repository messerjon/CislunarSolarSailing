"""Environment models: Sun & Moon ephemerides, eclipses, thermosphere density.

* Sun: Astronomical Almanac low-precision series (~0.01 deg).
* Moon: circular orbit (384 400 km) inclined 5.145 deg to the ecliptic with the
  18.6-yr regression of the node -- adequate for mission-level transit studies.
* Density: NRLMSIS 2.x via ``pymsis`` tabulated vs altitude and local solar
  time for chosen F10.7 levels (falls back to Harris-Priester if pymsis absent).
"""
from __future__ import annotations

import os
from functools import lru_cache
import numpy as np

from .constants import (AU_KM, D_EARTH_MOON, MOON_INC_ECL_DEG, R_EARTH, DAY_S)

J2000_JD = 2451545.0
_DATA = os.path.join(os.path.dirname(__file__), "data")


def jd_from_iso(iso: str) -> float:
    t = np.datetime64(iso, "s")
    return J2000_JD + (t - np.datetime64("2000-01-01T12:00:00", "s")).astype(float) / DAY_S


def sun_vector_eci(jd):
    """Unit vector Earth->Sun (equatorial J2000-like frame) and distance [AU]."""
    n = np.asarray(jd) - J2000_JD
    L = np.radians(280.460 + 0.9856474 * n)
    g = np.radians(357.528 + 0.9856003 * n)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 4e-7 * n)
    R = 1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)
    u = np.stack([np.cos(lam), np.cos(eps) * np.sin(lam), np.sin(eps) * np.sin(lam)], axis=-1)
    return u, R


def moon_elements(jd):
    n = np.asarray(jd) - J2000_JD
    Lm = np.radians(218.316 + 13.176396 * n)
    Om = np.radians(125.045 - 0.0529538 * n)
    return Lm, Om


def moon_state_eci(jd):
    """Moon position [km] and velocity [km/s] (circular inclined model)."""
    Lm, Om = moon_elements(jd)
    i = np.radians(MOON_INC_ECL_DEG)
    u = Lm - Om
    eps = np.radians(23.4393)
    nM = np.radians(13.176396) / DAY_S
    cO, sO, cu, su, ci, si = np.cos(Om), np.sin(Om), np.cos(u), np.sin(u), np.cos(i), np.sin(i)
    x = cO * cu - sO * su * ci
    y = sO * cu + cO * su * ci
    z = su * si
    vx = (-cO * su - sO * cu * ci) * nM
    vy = (-sO * su + cO * cu * ci) * nM
    vz = cu * si * nM
    ce, se = np.cos(eps), np.sin(eps)
    r = np.stack([x, ce * y - se * z, se * y + ce * z], axis=-1) * D_EARTH_MOON
    v = np.stack([vx, ce * vy - se * vz, se * vy + ce * vz], axis=-1) * D_EARTH_MOON
    return r, v


def moon_orbit_inclination_to_equator_deg(jd):
    """Inclination of the lunar orbit plane to Earth's equator (18.3-28.6 deg)."""
    _, Om = moon_elements(jd)
    i, eps = np.radians(MOON_INC_ECL_DEG), np.radians(23.4393)
    return np.degrees(np.arccos(np.cos(eps) * np.cos(i) - np.sin(eps) * np.sin(i) * np.cos(Om)))


def cylindrical_shadow(B, r, u_sun, R_body):
    """1.0 if lit, 0.0 inside the cylindrical shadow of a body at the origin.
    r: (...,3) position relative to body; u_sun: (...,3) unit vector body->Sun."""
    proj = B.dot(r, u_sun)
    perp = B.norm(r - proj[..., None] * u_sun)
    shade = (proj < 0) & (perp < R_body)
    return B.where(shade, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Thermosphere
# ---------------------------------------------------------------------------
F107_LEVELS = {"low": 70.0, "moderate": 150.0, "high": 230.0}

# Harris-Priester (mean solar activity), Montenbruck & Gill Table 3.8; g/km^3
_HP_H = np.array([100, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250,
                  260, 270, 280, 290, 300, 320, 340, 360, 380, 400, 420, 440, 460, 480, 500,
                  520, 540, 560, 580, 600, 620, 640, 660, 680, 700, 720, 740, 760, 780, 800,
                  840, 880, 920, 960, 1000], float)
_HP_MIN = np.array([497400, 24900, 8377, 3899, 2122, 1263, 800.8, 528.3, 361.7, 255.7, 183.9,
                    134.1, 99.49, 74.88, 57.09, 44.03, 34.30, 26.97, 21.39, 17.08, 10.99, 7.214,
                    4.824, 3.274, 2.249, 1.558, 1.091, 0.7701, 0.5474, 0.3916, 0.2819, 0.2042,
                    0.1488, 0.1092, 0.08070, 0.06012, 0.04519, 0.03430, 0.02632, 0.02043, 0.01607,
                    0.01281, 0.01036, 0.008496, 0.007069, 0.004680, 0.003200, 0.002210, 0.001560,
                    0.001150])
_HP_MAX = np.array([497400, 24900, 8710, 4059, 2215, 1344, 875.8, 601.0, 429.7, 316.2, 239.6,
                    185.3, 145.5, 115.7, 93.08, 75.55, 61.82, 50.95, 42.26, 35.26, 25.11, 18.19,
                    13.37, 9.955, 7.492, 5.684, 4.355, 3.362, 2.612, 2.042, 1.605, 1.267, 1.005,
                    0.7997, 0.6390, 0.5123, 0.4121, 0.3325, 0.2691, 0.2185, 0.1779, 0.1452, 0.1190,
                    0.09776, 0.08059, 0.05741, 0.04210, 0.03130, 0.02360, 0.01810])


@lru_cache(maxsize=8)
def density_table(f107: float = 150.0, ap: float = 15.0):
    """Density [kg/m^3] on a grid altitude (km) x local solar time (h).
    Returns (h_grid, lst_grid, rho[h, lst])."""
    h = np.arange(100.0, 2001.0, 10.0)
    lst = np.arange(0.0, 24.01, 1.0)
    cache = os.path.join(_DATA, f"msis_f{int(f107)}_ap{int(ap)}.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        return z["h"], z["lst"], z["rho"]
    try:
        import pymsis
        date = np.datetime64("2028-03-20T12:00")
        # equator; longitude chosen so that local solar time = lst at 12 UT
        lons = (lst - 12.0) * 15.0
        rho = np.zeros((h.size, lst.size))
        for j, lon in enumerate(lons):
            d = pymsis.calculate(date, lon, 0.0, h, f107s=f107, f107as=f107, aps=[[ap] * 7])
            rho[:, j] = np.squeeze(d[..., pymsis.Variable.MASS_DENSITY])
    except Exception:  # pragma: no cover
        hp_lo = np.interp(h, _HP_H, np.log(_HP_MIN * 1e-12))
        hp_hi = np.interp(h, _HP_H, np.log(_HP_MAX * 1e-12))
        bulge = 0.5 * (1 + np.cos(np.radians((lst - 14.0) * 15.0)))
        rho = np.exp(hp_lo[:, None] + (hp_hi - hp_lo)[:, None] * bulge[None, :])
        rho *= (f107 / 150.0) ** 2
    os.makedirs(_DATA, exist_ok=True)
    np.savez(cache, h=h, lst=lst, rho=rho)
    return h, lst, rho


def density_lookup(B, alt_km, lst_h, table):
    """Bilinear log-density lookup, vectorised for numpy/torch."""
    h, lst, rho = table
    lr = np.log(rho)
    if B.name == "torch":
        alt_km = B.torch.nan_to_num(alt_km, nan=5000.0); lst_h = B.torch.nan_to_num(lst_h, nan=0.0)
    else:
        alt_km = np.nan_to_num(alt_km, nan=5000.0); lst_h = np.nan_to_num(lst_h, nan=0.0)
    hh = B.clip((alt_km - h[0]) / (h[1] - h[0]), 0.0, len(h) - 1.000001)
    ll = B.clip(lst_h / (lst[1] - lst[0]), 0.0, len(lst) - 1.000001)
    i0 = B.floor(hh)
    j0 = B.floor(ll)
    wi, wj = hh - i0, ll - j0
    LR = B.asarray(lr)
    if B.name == "torch":
        i0, j0 = i0.long(), j0.long()
    else:
        i0, j0 = i0.astype(np.int64), j0.astype(np.int64)
    v = (LR[i0, j0] * (1 - wi) * (1 - wj) + LR[i0 + 1, j0] * wi * (1 - wj)
         + LR[i0, j0 + 1] * (1 - wi) * wj + LR[i0 + 1, j0 + 1] * wi * wj)
    out = B.exp(v)
    return B.where(alt_km > 2000.0, 0.0, out)


def orbit_mean_density(alt_km, f107=150.0):
    h, lst, rho = density_table(f107)
    return np.interp(alt_km, h, rho.mean(axis=1))
