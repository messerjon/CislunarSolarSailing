"""Earth-centred propagation of solar-sail and hybrid sail/SEP spirals.

``propagate_averaged`` integrates orbit-averaged Gauss equations in modified
equinoctial elements (MEE, non-singular for circular/equatorial orbits).  Each
derivative evaluation samples K points uniformly in eccentric anomaly, applies
the steering law, eclipse, J2, drag (NRLMSIS table) and SEP at every sample,
and time-averages the Gauss rates.  All cases are batched (NumPy or PyTorch).

``propagate_cowell`` is a direct (non-averaged) integrator including Sun and
Moon third-body gravity, used to validate the averaged model and to draw
trajectories.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
import numpy as np

from .backend import get_backend
from .constants import (MU_EARTH, R_EARTH, J2_EARTH, OMEGA_EARTH, G0, DAY_S, MU_SUN, MU_MOON,
                        AU_KM)
from . import sail as S
from .environment import (sun_vector_eci, moon_state_eci, density_table, density_lookup,
                          jd_from_iso)

MU = MU_EARTH


@dataclass
class Craft:
    """Spacecraft parameters for Earth-orbit spirals.

    a_c        characteristic acceleration of the sail [m/s^2] at initial mass
    sep_thrust SEP thrust [N] (0 -> pure sail); isp [s]
    gimbal_deg SEP thrust may point within this angle of +/- the sail normal
    area       sail area [m^2] (only needed for drag); derived from a_c, m0 if None
    """
    a_c: float = 1.2e-4
    m0: float = 100.0
    material: S.SailMaterial = S.AL_CP1
    area: float | None = None
    sep_thrust: float = 0.0
    isp: float = 1500.0
    m_dry: float | None = None
    gimbal_deg: float = 180.0
    sep_both_sides: bool = True
    sep_policy: str = "always"
    sep_in_shadow: bool = False
    cd: float = 2.5
    min_area_frac: float = 0.01
    sail_deployed: bool = True

    def sail_area(self):
        if self.area is not None:
            return self.area
        return self.a_c * self.m0 / (S.P_SRP_1AU * self.material.front.total)


# ---------------------------------------------------------------------------
# Element conversions (vectorised)
# ---------------------------------------------------------------------------
def coe_to_mee(a, e, i, raan, argp, nu=0.0):
    a, e, i, raan, argp, nu = map(np.asarray, (a, e, i, raan, argp, nu))
    p = a * (1 - e ** 2)
    f = e * np.cos(argp + raan)
    g = e * np.sin(argp + raan)
    h = np.tan(i / 2) * np.cos(raan)
    k = np.tan(i / 2) * np.sin(raan)
    L = raan + argp + nu
    return p, f, g, h, k, L


def mee_to_coe(B, p, f, g, h, k):
    e = B.sqrt(f * f + g * g)
    a = p / (1 - e * e)
    i = 2 * B.arctan2(B.sqrt(h * h + k * k), 1.0 + 0 * h)
    raan = B.arctan2(k, h)
    lonper = B.arctan2(g, f)
    return a, e, i, raan, lonper - raan


def mee_to_rv(B, p, f, g, h, k, L, mu=MU):
    cL, sL = B.cos(L), B.sin(L)
    al2 = h * h - k * k
    s2 = 1 + h * h + k * k
    w = 1 + f * cL + g * sL
    r = p / w
    rx = r / s2 * (cL + al2 * cL + 2 * h * k * sL)
    ry = r / s2 * (sL - al2 * sL + 2 * h * k * cL)
    rz = 2 * r / s2 * (h * sL - k * cL)
    sq = B.sqrt(mu / p)
    vx = -sq / s2 * (sL + al2 * sL - 2 * h * k * cL + g - 2 * f * h * k + al2 * g)
    vy = -sq / s2 * (-cL + al2 * cL + 2 * h * k * sL - f + 2 * g * h * k + al2 * f)
    vz = 2 * sq / s2 * (h * cL + k * sL + f * h + g * k)
    return B.stack([rx, ry, rz]), B.stack([vx, vy, vz]), w, s2, r


def rv_to_coe(r, v, mu=MU):
    r = np.asarray(r, float); v = np.asarray(v, float)
    h = np.cross(r, v); hn = np.linalg.norm(h, axis=-1)
    rn = np.linalg.norm(r, axis=-1); vn2 = np.sum(v * v, axis=-1)
    a = 1.0 / (2.0 / rn - vn2 / mu)
    ev = (np.cross(v, h) / mu) - r / rn[..., None]
    e = np.linalg.norm(ev, axis=-1)
    i = np.arccos(np.clip(h[..., 2] / hn, -1, 1))
    return a, e, i


# ---------------------------------------------------------------------------
# Steering objective gradients
# ---------------------------------------------------------------------------
def _gradients(B, a, e, p, r, nu, hmom, Rh, Th):
    sn, cn = B.sin(nu), B.cos(nu)
    da_R = 2 * a * a / hmom * e * sn
    da_T = 2 * a * a / hmom * p / r
    de_R = p * sn / hmom
    de_T = ((p + r) * cn + r * e) / hmom
    ra_R = (1 + e) * da_R + a * de_R
    ra_T = (1 + e) * da_T + a * de_T
    rp_R = (1 - e) * da_R - a * de_R
    rp_T = (1 - e) * da_T - a * de_T
    ga = ra_R[..., None] * Rh + ra_T[..., None] * Th
    gp = rp_R[..., None] * Rh + rp_T[..., None] * Th
    return ga, gp


def _unit(B, x):
    return x / B.maximum(B.norm(x, keepdims=True), 1e-30)


# ---------------------------------------------------------------------------
# Orbit-averaged derivative
# ---------------------------------------------------------------------------
def averaged_rates(B, y, jd, craft: Craft, objective="apogee", K=96, rp_safe=None,
                   rp_floor=None, inc_target=None, dens=None, diag=False, mu=MU, R_body=R_EARTH,
                   j2=J2_EARTH):
    """Orbit-averaged d/dt of y = [p, f, g, h, k, m] (km, kg) for N cases.
    ``mu``, ``R_body`` and ``j2`` select the central body (Earth default; Moon for
    low-lunar-orbit spirals, where drag is not used)."""
    N = y.shape[0]
    p, f, g, h, k, m = (y[:, j] for j in range(6))
    # guard intermediate RK stages of decaying/escaping cases (flagged after the step)
    p = B.maximum(p, 1000.0)
    m = B.maximum(m, 1e-3)
    ecc = B.sqrt(f * f + g * g)
    scl = B.where(ecc > 0.99, 0.99 / B.maximum(ecc, 1e-12), 1.0)
    f, g = f * scl, g * scl
    e = B.sqrt(f * f + g * g)
    lonper = B.arctan2(g, f)
    E = B.asarray((np.arange(K) + 0.5) * 2 * np.pi / K)[None, :]          # (1,K)
    ee = e[:, None]
    nu = 2 * B.arctan2(B.sqrt(1 + ee) * B.sin(E / 2), B.sqrt(B.maximum(1 - ee, 1e-12)) * B.cos(E / 2))
    L = nu + lonper[:, None]
    wts = (1 - ee * B.cos(E)) / K                                           # (N,K)
    P_, F_, G_, H_, K_ = (q[:, None] + 0 * L for q in (p, f, g, h, k))
    rv, vv, w, s2, rmag = mee_to_rv(B, P_, F_, G_, H_, K_, L, mu)
    a = p / (1 - e * e)
    hmom = B.sqrt(mu * p)
    Rh = rv / rmag[..., None]
    Nh = _unit(B, B.cross(rv, vv))
    Th = B.cross(Nh, Rh)
    vh = _unit(B, vv)

    # Sun geometry
    u_np, Rau = sun_vector_eci(np.asarray(B.to_numpy(jd)))
    u_sun = B.asarray(u_np)[:, None, :] + 0 * rv                            # (N,K,3)
    s_hat = -u_sun
    lit = (B.dot(rv, u_sun) >= 0) | (B.norm(rv - B.dot(rv, u_sun)[..., None] * u_sun) >= R_body)
    lit = B.where(lit, 1.0, 0.0)
    def per_case(v):            # scalar or (N,) parameter -> (N,1) array
        return B.asarray(np.broadcast_to(np.asarray(v, float), (N,)).copy())[:, None]
    m0c = per_case(craft.m0)
    mratio = m0c / m[:, None]
    flux = B.asarray(1.0 / Rau ** 2)[:, None]
    ac = per_case(craft.a_c) * 1e-3 * mratio * flux * (1.0 if craft.sail_deployed else 0.0)  # km/s^2
    # objective direction
    ga, gp = _gradients(B, a[:, None], ee, P_, rmag, nu, hmom[:, None], Rh, Th)
    if objective == "apogee":
        rp = (p / (1 + e))[:, None]
        lam = 0.0 * rp
        if rp_safe is not None:
            lam = B.clip((rp_safe - rp) / max(rp_safe - (rp_floor or R_body + 150.0), 1.0), 0.0, 1.0) * 4.0
        d = _unit(B, _unit(B, ga) + lam[..., None] * _unit(B, gp))
    elif objective == "energy":
        d = vh
    elif objective == "energy_down":
        d = -vh
    elif objective == "perigee":
        d = _unit(B, gp)
    elif objective == "inclination":
        inc = 2 * B.arctan2(B.sqrt(h * h + k * k), 1.0 + 0 * h)
        raan = B.arctan2(k, h)
        u_arg = L - raan[:, None]
        sgn = B.sign(B.asarray(inc_target) - inc)[:, None] if inc_target is not None else 1.0
        d = (sgn * B.cos(u_arg) * rmag / hmom[:, None])[..., None] * Nh
        d = _unit(B, d + 1e-12 * Th)
    else:
        raise ValueError(objective)

    alt = rmag - R_body
    use_drag = dens is not None
    sep_on = bool(np.any(np.asarray(craft.sep_thrust) > 0)) and craft.sep_policy != "off"
    thr = per_case(craft.sep_thrust)
    asep = thr / m[:, None] * 1e-3 + 0 * rmag if sep_on else 0.0 * rmag
    if sep_on:
        mdry = per_case(craft.m_dry if craft.m_dry is not None else 0.0)
        asep = B.where((m[:, None] > mdry + 1e-6) & (rmag > 0), asep, 0.0)
        if not craft.sep_in_shadow:
            asep = asep * lit
    drag_k = None
    if use_drag:
        lon_sc = B.arctan2(rv[..., 1], rv[..., 0])
        lon_sun = B.arctan2(u_sun[..., 1], u_sun[..., 0])
        lst = ((lon_sc - lon_sun) * 12 / math.pi + 12.0) % 24.0
        rho = density_lookup(B, alt, lst, dens)                              # kg/m^3
        vrel = vv - B.stack([-OMEGA_EARTH * rv[..., 1], OMEGA_EARTH * rv[..., 0], 0 * rv[..., 2]])
        vr = B.norm(vrel) * 1e3
        q = 0.5 * rho * vr * vr                                              # Pa
        A = per_case(craft.sail_area())
        drag_k = q * craft.cd * A / m[:, None] * 1e-3                        # km/s^2 per unit area frac
        vrh = vrel / B.norm(vrel, keepdims=True)
    face = craft.material.front
    if (not sep_on) and (not use_drag):
        n_hat, gcomp = S.optimal_normal(B, face, s_hat, d)
        a_sep_vec = 0 * rv
    else:
        res = S.best_hybrid(B, face, s_hat, d, ac, asep, gimbal_deg=craft.gimbal_deg,
                            both_sides=craft.sep_both_sides, sep_policy=craft.sep_policy if sep_on else "off",
                            drag_k=(drag_k if use_drag else None), v_hat=(vh if use_drag else None),
                            lit=lit, n_alpha=121)
        n_hat = res["n_hat"]
        if sep_on:
            a_sep_vec = res["comp_sep"][..., None] * d
            sep_mask = B.where(res["comp_sep"] > 1e-18, 1.0, 0.0)
        else:
            a_sep_vec = 0 * rv
    a_sail = S.sail_accel(B, face, craft.material.back, s_hat, n_hat, ac, lit=lit)
    if objective == "inclination":
        keep = B.where(B.abs(B.cos(u_arg)) > 0.3, 1.0, 0.0)
        a_sail = a_sail * keep[..., None]
        a_sep_vec = a_sep_vec * keep[..., None]
        if sep_on:
            sep_mask = sep_mask * keep
    acc = a_sail + a_sep_vec
    if use_drag:
        proj = B.abs(B.dot(n_hat, vrh)) * (1 - craft.min_area_frac) + craft.min_area_frac
        acc = acc - (drag_k * proj)[..., None] * vrh
    # J2
    z2 = (rv[..., 2] / rmag) ** 2
    cj = -1.5 * j2 * mu * R_body ** 2 / rmag ** 4
    aj2 = B.stack([cj * (1 - 5 * z2) * rv[..., 0] / rmag, cj * (1 - 5 * z2) * rv[..., 1] / rmag,
                   cj * (3 - 5 * z2) * rv[..., 2] / rmag])
    acc = acc + aj2
    Rc, Tc, Nc = B.dot(acc, Rh), B.dot(acc, Th), B.dot(acc, Nh)
    cL, sL = B.cos(L), B.sin(L)
    sqp = B.sqrt(P_ / mu)
    dp = 2 * P_ / w * sqp * Tc
    df = sqp * (Rc * sL + ((w + 1) * cL + F_) * Tc / w - (H_ * sL - K_ * cL) * G_ * Nc / w)
    dg = sqp * (-Rc * cL + ((w + 1) * sL + G_) * Tc / w + (H_ * sL - K_ * cL) * F_ * Nc / w)
    dh = sqp * s2 * Nc * cL / (2 * w)
    dk = sqp * s2 * Nc * sL / (2 * w)
    out = [B.sum(q * wts, axis=1) for q in (dp, df, dg, dh, dk)]
    if sep_on:
        sep_frac = B.sum(sep_mask * wts, axis=1)
        dm = -thr[:, 0] / (craft.isp * G0) * sep_frac
    else:
        dm = 0 * p
    out.append(dm)
    dy = B.stack(out, axis=1)
    if diag:
        useful = B.sum(B.dot(a_sail, d) * wts, axis=1) / B.maximum(ac[:, 0], 1e-30)
        return dy, {"lit_frac": B.sum(lit * wts, axis=1), "useful_frac": useful}
    return dy


def propagate_averaged(y0, jd0, craft: Craft, t_max_days=1500.0, dt_days=0.5, objective="apogee",
                       ra_target=326_000.0, rp_decay=R_EARTH + 140.0, K=96, rp_safe=None,
                       rp_floor=None, f107=None, inc_target=None, inc_tol_deg=0.25,
                       backend=None, record_every=10, stop_on_target=True, central="earth",
                       a_target=None):
    """Batched RK4 integration of orbit-averaged dynamics.

    y0  (N,6) MEE + mass; jd0 (N,) Julian dates.  Returns dict with arrival
    times (days; NaN if not reached), status codes and a thinned history.
    status: 0 running/timeout, 1 reached target, 2 decayed, 3 escaped/invalid.
    """
    B = get_backend(backend)
    y = B.asarray(y0)
    N = y.shape[0]
    jd0 = np.asarray(jd0, float) + np.zeros(N)
    dens = density_table(f107) if f107 is not None else None
    dt = dt_days * DAY_S
    nsteps = int(math.ceil(t_max_days / dt_days))
    t_arr = np.full(N, np.nan)
    status = np.zeros(N, int)
    active = np.ones(N, bool)
    hist_t, hist_y = [0.0], [B.to_numpy(y).copy()]
    kw = dict(craft=craft, objective=objective, K=K, rp_safe=rp_safe, rp_floor=rp_floor,
              inc_target=inc_target, dens=dens)
    if central == "moon":
        from .constants import MU_MOON, R_MOON
        kw.update(mu=MU_MOON, R_body=R_MOON, j2=0.0)
    for n in range(nsteps):
        t = n * dt
        jd = B.asarray(jd0 + t / DAY_S)
        jd_h = B.asarray(jd0 + (t + dt / 2) / DAY_S)
        jd_1 = B.asarray(jd0 + (t + dt) / DAY_S)
        k1 = averaged_rates(B, y, jd, **kw)
        k2 = averaged_rates(B, y + 0.5 * dt * k1, jd_h, **kw)
        k3 = averaged_rates(B, y + 0.5 * dt * k2, jd_h, **kw)
        k4 = averaged_rates(B, y + dt * k3, jd_1, **kw)
        ynew = y + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        act = B.asarray(active.astype(float))[:, None]
        y = ynew * act + y * (1 - act)
        yn = B.to_numpy(y)
        p, f, g = yn[:, 0], yn[:, 1], yn[:, 2]
        e = np.sqrt(f * f + g * g)
        bad = (~np.isfinite(yn).all(axis=1)) | (p <= 0) | (e >= 0.985)
        ra = np.where(e < 1, p / (1 - e), np.inf)
        rp = p / (1 + e)
        tdays = (n + 1) * dt_days
        newly = active & (ra >= ra_target) & ~bad
        if a_target is not None:          # lowering: stop when SMA <= a_target
            newly = active & (p / (1 - e * e) <= a_target) & ~bad
        if inc_target is not None:
            inc = 2 * np.arctan(np.sqrt(yn[:, 3] ** 2 + yn[:, 4] ** 2))
            newly = active & (np.abs(np.degrees(inc) - np.degrees(inc_target)) <= inc_tol_deg)
        decayed = active & (rp < rp_decay)
        t_arr[newly] = tdays
        status[newly] = 1
        status[decayed & ~newly] = 2
        status[bad & active & ~newly] = 3
        if stop_on_target:
            active &= ~(newly | decayed | bad)
        else:
            active &= ~(decayed | bad)
        if (n + 1) % record_every == 0:
            hist_t.append(tdays)
            hist_y.append(yn.copy())
        if not active.any():
            break
    hist_t.append((n + 1) * dt_days)
    hist_y.append(B.to_numpy(y).copy())
    return {"t_days": t_arr, "status": status, "hist_t": np.array(hist_t),
            "hist_y": np.array(hist_y), "y_final": B.to_numpy(y)}


def initial_state(a_km, e, inc_deg, raan_deg=0.0, argp_deg=0.0, m0=100.0, n=1):
    p, f, g, h, k, _ = coe_to_mee(a_km, e, np.radians(inc_deg), np.radians(raan_deg),
                                  np.radians(argp_deg))
    y = np.stack(np.broadcast_arrays(p, f, g, h, k, np.asarray(m0, float)), axis=-1).astype(float)
    return np.broadcast_to(y, (n, 6)).copy() if y.ndim == 1 else y


# ---------------------------------------------------------------------------
# Cowell propagation (validation / trajectory plots)
# ---------------------------------------------------------------------------
def propagate_cowell(r0, v0, jd0, craft: Craft, t_days, objective="apogee", f107=None,
                     third_body=True, rtol=1e-9, max_step_s=600.0, ra_stop=None, rp_safe=None):
    from scipy.integrate import solve_ivp
    B = get_backend("numpy")
    dens = density_table(f107) if f107 is not None else None
    face = craft.material.front

    def rhs(t, x):
        r, v, m = x[:3], x[3:6], x[6]
        jd = jd0 + t / DAY_S
        u, Rau = sun_vector_eci(jd)
        rn = np.linalg.norm(r)
        acc = -MU * r / rn ** 3
        z2 = (r[2] / rn) ** 2
        cj = -1.5 * J2_EARTH * MU * R_EARTH ** 2 / rn ** 4
        acc = acc + cj * np.array([(1 - 5 * z2) * r[0], (1 - 5 * z2) * r[1], (3 - 5 * z2) * r[2]]) / rn
        if third_body:
            rs = u * Rau * AU_KM
            d = rs - r
            acc = acc + MU_SUN * (d / np.linalg.norm(d) ** 3 - rs / np.linalg.norm(rs) ** 3)
            rm, _ = moon_state_eci(jd)
            d = rm - r
            acc = acc + MU_MOON * (d / np.linalg.norm(d) ** 3 - rm / np.linalg.norm(rm) ** 3)
        # osculating elements for steering
        hv = np.cross(r, v); hm = np.linalg.norm(hv)
        a = 1 / (2 / rn - v @ v / MU)
        ev = np.cross(v, hv) / MU - r / rn
        e = np.linalg.norm(ev)
        p = hm * hm / MU
        nu = math.atan2(np.dot(np.cross(ev, r), hv) / hm, np.dot(ev, r)) if e > 1e-8 else 0.0
        Rh = r / rn; Nh = hv / hm; Th = np.cross(Nh, Rh)
        ga, gp = _gradients(B, np.array(a), np.array(e), np.array(p), np.array(rn), np.array(nu),
                            np.array(hm), Rh, Th)
        if objective == "energy":
            d = v / np.linalg.norm(v)
        else:
            d = ga / np.linalg.norm(ga)
            if rp_safe is not None and a * (1 - e) < rp_safe:
                d = d + 2.0 * gp / np.linalg.norm(gp); d = d / np.linalg.norm(d)
        lit = float(np.dot(r, u) >= 0 or np.linalg.norm(r - np.dot(r, u) * u) >= R_EARTH)
        s_hat = -u[None, :]
        ac = craft.a_c * 1e-3 * craft.m0 / m / Rau ** 2
        if dens is None and craft.sep_thrust == 0:
            n_hat, _ = S.optimal_normal(B, face, s_hat, d[None, :])
            asep = np.zeros(3)
        else:
            vrel = v - np.array([-OMEGA_EARTH * r[1], OMEGA_EARTH * r[0], 0])
            dk = None
            if dens is not None:
                u2 = math.atan2(r[1], r[0]) - math.atan2(u[1], u[0])
                lst = ((u2 * 12 / math.pi) + 12) % 24
                rho = density_lookup(B, np.array([rn - R_EARTH]), np.array([lst]), dens)[0]
                q = 0.5 * rho * (np.linalg.norm(vrel) * 1e3) ** 2
                dk = np.array([q * craft.cd * craft.sail_area() / m * 1e-3])
            a_sep = craft.sep_thrust / m * 1e-3 * (lit if not craft.sep_in_shadow else 1.0)
            res = S.best_hybrid(B, face, s_hat, d[None, :], np.array([ac * lit]), np.array([a_sep]),
                                gimbal_deg=craft.gimbal_deg, sep_policy=craft.sep_policy if a_sep > 0 else "off",
                                drag_k=dk, v_hat=(vrel / np.linalg.norm(vrel))[None, :] if dk is not None else None)
            n_hat = res["n_hat"]
            asep = res["comp_sep"][0] * d if a_sep > 0 else np.zeros(3)
            if dk is not None:
                vrh = vrel / np.linalg.norm(vrel)
                proj = abs(np.dot(n_hat[0], vrh)) * (1 - craft.min_area_frac) + craft.min_area_frac
                acc = acc - dk[0] * proj * vrh
        acc = acc + S.sail_accel(B, face, craft.material.back, s_hat, n_hat, ac)[0] * lit + asep
        dm = -craft.sep_thrust / (craft.isp * G0) * (np.linalg.norm(asep) > 0) if craft.sep_thrust > 0 else 0.0
        return np.concatenate([v, acc, [dm]])

    events = []
    if ra_stop is not None:
        def ev_ra(t, x):
            r, v = x[:3], x[3:6]
            rn = np.linalg.norm(r); a = 1 / (2 / rn - v @ v / MU)
            hv = np.cross(r, v); e = np.linalg.norm(np.cross(v, hv) / MU - r / rn)
            return (a * (1 + e) if a > 0 else 1e12) - ra_stop
        ev_ra.terminal = True
        events.append(ev_ra)

    def ev_decay(t, x):
        return np.linalg.norm(x[:3]) - (R_EARTH + 100.0)
    ev_decay.terminal = True
    events.append(ev_decay)
    x0 = np.concatenate([r0, v0, [craft.m0]])
    sol = solve_ivp(rhs, (0, t_days * DAY_S), x0, method="DOP853", rtol=rtol, atol=1e-6,
                    max_step=max_step_s, events=events, dense_output=False)
    return sol
