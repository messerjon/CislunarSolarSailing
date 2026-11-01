"""Low-precision analytic Sun and Moon ephemerides (Earth-centred, equatorial J2000-like).

Sun: mean circular orbit in the ecliptic (error < 2 deg in longitude).
Moon: circular orbit inclined 5.145 deg to the ecliptic with regressing node
(18.6 yr). This reproduces the Moon's 18.3-28.6 deg swing in inclination to the
equator, which matters for launch-inclination studies. Errors of a few degrees in
lunar longitude are irrelevant for transit-time trades.

All functions accept `t` (seconds since epoch) as a torch tensor of any shape and
`epoch_jd2000` (days since J2000.0) as float or tensor broadcastable with t.
"""
import math

import torch

from . import constants as C

_COS_OBL = math.cos(C.OBLIQUITY)
_SIN_OBL = math.sin(C.OBLIQUITY)


def ecliptic_to_equatorial(v):
    x, y, z = v.unbind(-1)
    return torch.stack((x, _COS_OBL * y - _SIN_OBL * z, _SIN_OBL * y + _COS_OBL * z), -1)


def sun_longitude(t, epoch_jd2000):
    d = epoch_jd2000 + t / C.DAY
    mean_lon = torch.deg2rad(torch.as_tensor(280.460, dtype=t.dtype, device=t.device) + 0.9856474 * d)
    g = torch.deg2rad(torch.as_tensor(357.528, dtype=t.dtype, device=t.device) + 0.9856003 * d)
    return mean_lon + torch.deg2rad(1.915 * torch.sin(g) + 0.020 * torch.sin(2 * g))


def sun_unit(t, epoch_jd2000):
    """Unit vector Earth -> Sun, equatorial frame."""
    lam = sun_longitude(t, epoch_jd2000)
    v = torch.stack((torch.cos(lam), torch.sin(lam), torch.zeros_like(lam)), -1)
    return ecliptic_to_equatorial(v)


def sun_position(t, epoch_jd2000):
    return C.AU * sun_unit(t, epoch_jd2000)


def moon_position(t, epoch_jd2000):
    """Moon position (m), equatorial frame."""
    d = epoch_jd2000 + t / C.DAY
    node = torch.deg2rad(125.045 - 0.0529539 * d)
    mean_lon = torch.deg2rad(218.316 + 13.176396 * d)
    u = mean_lon - node  # argument of latitude
    ci, si = math.cos(C.MOON_INC_ECLIPTIC), math.sin(C.MOON_INC_ECLIPTIC)
    cO, sO, cu, su = torch.cos(node), torch.sin(node), torch.cos(u), torch.sin(u)
    v = torch.stack((cO * cu - sO * su * ci, sO * cu + cO * su * ci, su * si), -1)
    return C.D_EARTH_MOON * ecliptic_to_equatorial(v)


def moon_inclination_to_equator(epoch_jd2000: float) -> float:
    """Inclination of the lunar orbit plane to Earth's equator (deg) at a date."""
    t = torch.zeros(2, dtype=torch.float64)
    t[1] = 3600.0
    r = moon_position(t, torch.tensor(epoch_jd2000, dtype=torch.float64))
    h = torch.linalg.cross(r[0], r[1])
    return math.degrees(math.acos(float(h[2] / h.norm())))


def jd2000_from_date(year: int, month: int, day: float) -> float:
    """Days since J2000.0 (2000-01-01 12:00 TT) for a calendar date (UTC ~ TT here)."""
    import datetime as _dt
    base = _dt.datetime(2000, 1, 1, 12)
    whole = int(day)
    frac = day - whole
    dt = _dt.datetime(year, month, whole) - base
    return dt.days + dt.seconds / 86400.0 + frac
