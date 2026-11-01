"""Earth-Moon circular restricted three-body problem with solar-sail SRP.

Rotating barycentric frame, non-dimensional units (length = Earth-Moon
distance, time = 1/n).  Earth at (-mu, 0, 0), Moon at (1-mu, 0, 0).

    r'' + 2 w x r' = g(r) + a_sail + a_sep [+ a_sun]

g(r) = -grad U is gravity plus centrifugal acceleration.  The Sun direction
rotates clockwise at the synodic rate w_S = 0.9253, which makes the sail
dynamics non-autonomous (Heiligers et al. 2015).  The optional ``a_sun`` term
adds solar tidal gravity (bicircular restricted four-body problem, BCR4BP).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .backend import get_backend
from .constants import (MU_EM, L_EM_KM, T_EM_S, R_EARTH, R_MOON, OMEGA_SUN_SYNODIC, MASS_SUN_ND,
                        A_SUN_ND, DAY_S, A_EM_MMS2)
from . import sail as S

MU = MU_EM
RE_ND = R_EARTH / L_EM_KM
RM_ND = R_MOON / L_EM_KM


# ---------------------------------------------------------------------------
# Basic functions
# ---------------------------------------------------------------------------
def lagrange_points(mu=MU):
    def fx(x):
        r1 = abs(x + mu); r2 = abs(x - 1 + mu)
        return x - (1 - mu) * (x + mu) / r1 ** 3 - mu * (x - 1 + mu) / r2 ** 3
    L1 = brentq(fx, -mu + 0.5, 1 - mu - 1e-6)
    L2 = brentq(fx, 1 - mu + 1e-6, 2.0)
    L3 = brentq(fx, -2.0, -mu - 1e-6)
    L4 = (0.5 - mu, math.sqrt(3) / 2)
    L5 = (0.5 - mu, -math.sqrt(3) / 2)
    return {"L1": np.array([L1, 0, 0]), "L2": np.array([L2, 0, 0]), "L3": np.array([L3, 0, 0]),
            "L4": np.array([L4[0], L4[1], 0]), "L5": np.array([L5[0], L5[1], 0])}


def jacobi(x, mu=MU):
    x = np.asarray(x, float)
    r1 = np.sqrt((x[..., 0] + mu) ** 2 + x[..., 1] ** 2 + x[..., 2] ** 2)
    r2 = np.sqrt((x[..., 0] - 1 + mu) ** 2 + x[..., 1] ** 2 + x[..., 2] ** 2)
    Om = 0.5 * (x[..., 0] ** 2 + x[..., 1] ** 2) + (1 - mu) / r1 + mu / r2
    v2 = np.sum(x[..., 3:6] ** 2, axis=-1)
    return 2 * Om - v2


def accel_gc(B, r, mu=MU):
    """Gravity + centrifugal acceleration (= -grad U) for (...,3) positions."""
    x, y, z = r[..., 0], r[..., 1], r[..., 2]
    r1 = B.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = B.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    a1 = (1 - mu) / r1 ** 3
    a2 = mu / r2 ** 3
    ax = x - a1 * (x + mu) - a2 * (x - 1 + mu)
    ay = y - a1 * y - a2 * y
    az = -a1 * z - a2 * z
    return B.stack([ax, ay, az])


def eom(t, s, mu=MU):
    x, y, z, vx, vy, vz = s
    r1 = math.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = math.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    a1 = (1 - mu) / r1 ** 3; a2 = mu / r2 ** 3
    return [vx, vy, vz,
            2 * vy + x - a1 * (x + mu) - a2 * (x - 1 + mu),
            -2 * vx + y - a1 * y - a2 * y,
            -a1 * z - a2 * z]


def _jac(x, y, z, mu=MU):
    r1 = math.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = math.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    m1, m2 = 1 - mu, mu
    dx1, dx2 = x + mu, x - 1 + mu
    Uxx = 1 - m1 / r1 ** 3 - m2 / r2 ** 3 + 3 * m1 * dx1 ** 2 / r1 ** 5 + 3 * m2 * dx2 ** 2 / r2 ** 5
    Uyy = 1 - m1 / r1 ** 3 - m2 / r2 ** 3 + 3 * m1 * y * y / r1 ** 5 + 3 * m2 * y * y / r2 ** 5
    Uzz = -m1 / r1 ** 3 - m2 / r2 ** 3 + 3 * m1 * z * z / r1 ** 5 + 3 * m2 * z * z / r2 ** 5
    Uxy = 3 * m1 * dx1 * y / r1 ** 5 + 3 * m2 * dx2 * y / r2 ** 5
    Uxz = 3 * m1 * dx1 * z / r1 ** 5 + 3 * m2 * dx2 * z / r2 ** 5
    Uyz = 3 * m1 * y * z / r1 ** 5 + 3 * m2 * y * z / r2 ** 5
    A = np.zeros((6, 6))
    A[0:3, 3:6] = np.eye(3)
    A[3:6, 0:3] = [[Uxx, Uxy, Uxz], [Uxy, Uyy, Uyz], [Uxz, Uyz, Uzz]]
    A[3, 4] = 2.0
    A[4, 3] = -2.0
    return A


def eom_stm(t, X, mu=MU):
    s = X[:6]
    Phi = X[6:].reshape(6, 6)
    ds = eom(t, s, mu)
    dPhi = _jac(s[0], s[1], s[2], mu) @ Phi
    return np.concatenate([ds, dPhi.ravel()])


def propagate(s0, t, mu=MU, stm=False, rtol=1e-12, atol=1e-12, dense=True, t_eval=None, events=None):
    if stm:
        X0 = np.concatenate([s0, np.eye(6).ravel()])
        return solve_ivp(eom_stm, (0, t), X0, method="DOP853", rtol=rtol, atol=atol, args=(mu,),
                         dense_output=dense, t_eval=t_eval, events=events)
    return solve_ivp(eom, (0, t), s0, method="DOP853", rtol=rtol, atol=atol, args=(mu,),
                     dense_output=dense, t_eval=t_eval, events=events)


# ---------------------------------------------------------------------------
# Symmetric periodic orbits (perpendicular x-z plane crossings)
# ---------------------------------------------------------------------------
def _half_period(s0, mu=MU, tmax=20.0):
    def ev(t, X, *args):
        return X[1]
    ev.terminal = True
    ev.direction = -np.sign(s0[4]) if s0[4] != 0 else 0
    sol = solve_ivp(eom_stm, (0, tmax), np.concatenate([s0, np.eye(6).ravel()]), method="DOP853",
                    rtol=1e-12, atol=1e-12, args=(mu,), events=ev)
    # skip the trivial event at t=0
    if sol.t_events[0].size == 0:
        raise RuntimeError("no y=0 crossing")
    te = sol.t_events[0][0]
    Xe = sol.y_events[0][0]
    return te, Xe


def correct_symmetric(s0, fix="z", mu=MU, tol=1e-11, maxit=40, planar=False):
    """Differential correction of a symmetric periodic orbit.
    s0 = [x0, 0, z0, 0, vy0, 0].  fix='z' varies (x0, vy0); fix='x' varies (z0, vy0);
    planar=True varies vy0 only (Lyapunov / DRO)."""
    s = np.array(s0, float)
    for it in range(maxit):
        te, Xe = _half_period(s, mu)
        se = Xe[:6]
        Phi = Xe[6:].reshape(6, 6)
        f = np.array(eom(0, se, mu))
        err = np.array([se[3], se[5]])
        if np.max(np.abs(err)) < tol:
            return s, 2 * te
        if planar:
            d = Phi[3, 4] - f[3] * Phi[1, 4] / se[4]
            s[4] -= float(np.clip(se[3] / d, -0.05, 0.05))
            continue
        cols = (0, 4) if fix == "z" else (2, 4)
        M = np.zeros((2, 2))
        for j, c in enumerate(cols):
            M[0, j] = Phi[3, c] - f[3] * Phi[1, c] / se[4]
            M[1, j] = Phi[5, c] - f[5] * Phi[1, c] / se[4]
        dx = np.linalg.solve(M, -err)
        dx = np.clip(dx, -0.05, 0.05)
        s[cols[0]] += dx[0]
        s[cols[1]] += dx[1]
    raise RuntimeError("differential correction did not converge")


def richardson_halo(Az_km, Lpt=1, northern=True, mu=MU):
    """Richardson (1980) third-order halo approximation -> initial state, period."""
    xL = lagrange_points(mu)[f"L{Lpt}"][0]
    gam = abs(xL - (1 - mu))
    sgn = 1 if Lpt == 1 else -1
    def c(n):
        if Lpt == 1:
            return (mu + (-1) ** n * (1 - mu) * gam ** (n + 1) / (1 - gam) ** (n + 1)) / gam ** 3
        return ((-1) ** n * mu + (-1) ** n * (1 - mu) * gam ** (n + 1) / (1 + gam) ** (n + 1)) / gam ** 3
    c2, c3, c4 = c(2), c(3), c(4)
    lam = math.sqrt((2 - c2 + math.sqrt((c2 - 2) ** 2 + 4 * (c2 - 1) * (1 + 2 * c2))) / 2)
    k = (lam ** 2 + 1 + 2 * c2) / (2 * lam)
    d1 = 3 * lam ** 2 / k * (k * (6 * lam ** 2 - 1) - 2 * lam)
    d2 = 8 * lam ** 2 / k * (k * (11 * lam ** 2 - 1) - 2 * lam)
    a21 = 3 * c3 * (k ** 2 - 2) / (4 * (1 + 2 * c2))
    a22 = 3 * c3 / (4 * (1 + 2 * c2))
    a23 = -3 * c3 * lam / (4 * k * d1) * (3 * k ** 3 * lam - 6 * k * (k - lam) + 4)
    a24 = -3 * c3 * lam / (4 * k * d1) * (2 + 3 * k * lam)
    b21 = -3 * c3 * lam / (2 * d1) * (3 * k * lam - 4)
    b22 = 3 * c3 * lam / d1
    d21 = -c3 / (2 * lam ** 2)
    a31 = (-9 * lam / (4 * d2) * (4 * c3 * (k * a23 - b21) + k * c4 * (4 + k ** 2))
           + (9 * lam ** 2 + 1 - c2) / (2 * d2) * (3 * c3 * (2 * a23 - k * b21) + c4 * (2 + 3 * k ** 2)))
    a32 = -1 / d2 * (9 * lam / 4 * (4 * c3 * (k * a24 - b22) + k * c4)
                     + 1.5 * (9 * lam ** 2 + 1 - c2) * (c3 * (k * b22 + d21 - 2 * a24) - c4))
    b31 = 3 / (8 * d2) * (8 * lam * (3 * c3 * (k * b21 - 2 * a23) - c4 * (2 + 3 * k ** 2))
                          + (9 * lam ** 2 + 1 + 2 * c2) * (4 * c3 * (k * a23 - b21) + k * c4 * (4 + k ** 2)))
    b32 = 1 / d2 * (9 * lam * (c3 * (k * b22 + d21 - 2 * a24) - c4)
                    + 3 / 8 * (9 * lam ** 2 + 1 + 2 * c2) * (4 * c3 * (k * a24 - b22) + k * c4))
    d31 = 3 / (64 * lam ** 2) * (4 * c3 * a24 + c4)
    d32 = 3 / (64 * lam ** 2) * (4 * c3 * (a23 - d21) + c4 * (4 + k ** 2))
    s1 = (1 / (2 * lam * (lam * (1 + k ** 2) - 2 * k))) * (
        1.5 * c3 * (2 * a21 * (k ** 2 - 2) - a23 * (k ** 2 + 2) - 2 * k * b21)
        - 3 / 8 * c4 * (3 * k ** 4 - 8 * k ** 2 + 8))
    s2 = (1 / (2 * lam * (lam * (1 + k ** 2) - 2 * k))) * (
        1.5 * c3 * (2 * a22 * (k ** 2 - 2) + a24 * (k ** 2 + 2) + 2 * k * b22 + 5 * d21)
        + 3 / 8 * c4 * (12 - k ** 2))
    a1 = -1.5 * c3 * (2 * a21 + a23 + 5 * d21) - 3 / 8 * c4 * (12 - k ** 2)
    a2 = 1.5 * c3 * (a24 - 2 * a22) + 9 / 8 * c4
    l1 = a1 + 2 * lam ** 2 * s1
    l2 = a2 + 2 * lam ** 2 * s2
    Delta = lam ** 2 - c2
    Az = Az_km / L_EM_KM / gam
    Ax = math.sqrt(max(-(l2 * Az ** 2 + Delta) / l1, 0.0))
    om = 1 + s1 * Ax ** 2 + s2 * Az ** 2
    dm = 1 if northern else -1
    tau = 0.0
    t1 = lam * tau
    x = a21 * Ax ** 2 + a22 * Az ** 2 - Ax * math.cos(t1) + (a23 * Ax ** 2 - a24 * Az ** 2) * math.cos(2 * t1) \
        + (a31 * Ax ** 3 - a32 * Ax * Az ** 2) * math.cos(3 * t1)
    z = dm * Az * math.cos(t1) + dm * d21 * Ax * Az * (math.cos(2 * t1) - 3) + dm * (d32 * Az * Ax ** 2 - d31 * Az ** 3) * math.cos(3 * t1)
    vy = (k * Ax * math.cos(t1) + 2 * (b21 * Ax ** 2 - b22 * Az ** 2) * math.cos(2 * t1)
          + 3 * (b31 * Ax ** 3 - b32 * Ax * Az ** 2) * math.cos(3 * t1)) * lam * om
    T = 2 * math.pi / (lam * om)
    guesses = []
    for orient in (+1, -1):
        guesses.append(np.array([xL + orient * gam * x, 0.0, gam * z, 0.0, orient * gam * vy, 0.0]))
    return guesses, T


@dataclass
class PeriodicOrbit:
    name: str
    s0: np.ndarray
    period: float
    family: str = ""

    @property
    def C(self):
        return float(jacobi(self.s0))

    def sample(self, n=400):
        sol = propagate(self.s0, self.period, dense=True)
        t = np.linspace(0, self.period, n)
        return t, sol.sol(t).T

    def monodromy(self):
        sol = propagate(self.s0, self.period, stm=True, dense=False)
        return sol.y[6:, -1].reshape(6, 6)

    def stability_index(self):
        lam = np.linalg.eigvals(self.monodromy())
        lmax = np.max(np.abs(lam))
        return 0.5 * (lmax + 1 / lmax)

    def period_days(self):
        return self.period * T_EM_S / DAY_S


def halo(Az_km, Lpt=2, northern=False, mu=MU, name=None):
    guesses, T = richardson_halo(Az_km, Lpt, northern, mu)
    last = None
    for g in guesses:
        try:
            s, P = correct_symmetric(g, fix="z", mu=mu)
            if abs(P - T) / T < 0.5 and abs(s[2]) > 0.3 * Az_km / L_EM_KM:
                return PeriodicOrbit(name or f"L{Lpt} {'N' if northern else 'S'} halo Az={Az_km:.0f} km",
                                     s, P, f"L{Lpt}halo")
        except Exception as exc:  # try other orientation
            last = exc
    raise RuntimeError(f"halo correction failed: {last}")


def continue_halo(orbit: PeriodicOrbit, target, key="period", step=0.002, fix="z", maxn=4000):
    """Natural-parameter continuation of a halo family in z0 (or x0) until
    key ('period' in TU, or 'rp' perilune radius in km) crosses target."""
    s = orbit.s0.copy()
    P = orbit.period
    fam = [(s.copy(), P)]
    idx = 2 if fix == "z" else 0
    def metric(s, P):
        if key == "period":
            return P
        t, X = PeriodicOrbit("", s, P).sample(800)
        return np.min(np.linalg.norm(X[:, :3] - [1 - MU, 0, 0], axis=1)) * L_EM_KM
    m0 = metric(s, P)
    sign_needed = np.sign(target - m0)
    for n in range(maxn):
        trial = s.copy()
        trial[idx] += step
        try:
            s_new, P_new = correct_symmetric(trial, fix=fix)
        except Exception:
            step /= 2
            if abs(step) < 1e-6:
                break
            continue
        s, P = s_new, P_new
        fam.append((s.copy(), P))
        m = metric(s, P)
        if np.sign(target - m) != sign_needed:
            break
    return PeriodicOrbit(orbit.name, s, P, orbit.family), fam


def lyapunov(Ax_km, Lpt=1, mu=MU, step_km=500.0):
    """Planar Lyapunov orbit with x-amplitude ~Ax_km (continuation from 500 km)."""
    xL = lagrange_points(mu)[f"L{Lpt}"][0]
    mub = mu / abs(xL - 1 + mu) ** 3 + (1 - mu) / abs(xL + mu) ** 3
    nu = math.sqrt((-(mub - 2) + math.sqrt(9 * mub ** 2 - 8 * mub)) / 2)
    A = min(500.0, Ax_km)
    s = np.array([xL - A / L_EM_KM, 0, 0, 0, (A / L_EM_KM) * (nu ** 2 + 2 * mub + 1) / 2, 0])
    s, P = correct_symmetric(s, planar=True, mu=mu)
    prev = None
    while A < Ax_km - 1e-6:
        An = min(A + step_km, Ax_km)
        trial = s.copy()
        trial[0] = xL - An / L_EM_KM
        if prev is not None:   # linear extrapolation of vy0
            trial[4] = s[4] + (s[4] - prev[4]) * (An - A) / step_km
        else:                  # linear regime: vy0 scales with amplitude
            trial[4] = s[4] * An / A
        s_new, P_new = correct_symmetric(trial, planar=True, mu=mu)
        prev, s, P, A = s.copy(), s_new, P_new, An
    return PeriodicOrbit(f"L{Lpt} Lyapunov Ax={Ax_km:.0f} km", s, P, f"L{Lpt}lyap")


def nrho(period_days=6.562, mu=MU, step=0.0025, southern=True):
    """L2 near-rectilinear halo orbit: continuation of the L2 halo family from
    the apolune-side x-z crossing (increasing |z_apolune|) until the period
    reaches ``period_days`` (6.56 d = 9:2 synodic resonance, Gateway reference).
    The returned state is at apolune; ``southern`` mirrors it below the plane."""
    o = halo(8000, 2, northern=False)
    te, Xe = _half_period(o.s0, mu)
    sa = Xe[:6].copy()
    if abs(sa[2]) < abs(o.s0[2]):
        sa = o.s0.copy()
    sa[1] = 0.0; sa[3] = 0.0; sa[5] = 0.0
    sgn = np.sign(sa[2])
    s, P = correct_symmetric(sa, fix="z", mu=mu)
    target = period_days * DAY_S / T_EM_S
    prev = None
    mode, idx, dstep = "z", 2, sgn * step
    while P > target:
        trial = s.copy()
        trial[idx] += dstep
        if prev is not None:
            for j in (0, 2, 4):
                if j != idx:
                    trial[j] = s[j] + (s[j] - prev[j])
        try:
            s_new, P_new = correct_symmetric(trial, fix=mode, mu=mu)
            if P_new > P + 1e-9:          # moved the wrong way along the family
                raise RuntimeError
        except Exception:
            prev = None
            if mode == "z":                # passed the |z| turning point -> continue in x
                mode, idx, dstep = "x", 0, -0.002
            else:
                dstep /= 2
                if abs(dstep) < 1e-7:
                    break
            continue
        if P_new < target and P - P_new > 1e-12:
            frac = (P - target) / (P - P_new)
            trial = s + frac * (s_new - s)
            s, P = correct_symmetric(trial, fix=mode, mu=mu)
            break
        prev, s, P = s.copy(), s_new, P_new
    if southern and s[2] > 0 or (not southern and s[2] < 0):
        s = s.copy(); s[2] = -s[2]
    return PeriodicOrbit(f"L2 {'S' if southern else 'N'} NRHO P={P*T_EM_S/DAY_S:.2f} d", s, P, "NRHO")


def dro(d_km, mu=MU, step_km=1500.0):
    """Distant retrograde orbit crossing the x-axis d_km from the Moon on the
    Earth-facing side, by continuation from a small near-Keplerian DRO."""
    d = 8000.0
    s = np.array([1 - mu - d / L_EM_KM, 0, 0, 0, math.sqrt(mu / (d / L_EM_KM)) + d / L_EM_KM, 0])
    s, P = correct_symmetric(s, planar=True, mu=mu)
    while d < d_km - 1e-6:
        dn = min(d + step_km, d_km)
        trial = s.copy()
        trial[0] = 1 - mu - dn / L_EM_KM
        # extrapolate velocity linearly
        s_new, P_new = correct_symmetric(trial, planar=True, mu=mu)
        s, P, d = s_new, P_new, dn
    return PeriodicOrbit(f"DRO {d_km/1000:.0f}k km", s, P, "DRO")


# ---------------------------------------------------------------------------
# Batched propagation with sail / hybrid steering
# ---------------------------------------------------------------------------
@dataclass
class SailCraftND:
    a_c_mm: float = 0.12               # characteristic acceleration, mm/s^2
    material: S.SailMaterial = S.AL_CP1
    a_sep_mm: float = 0.0              # SEP acceleration magnitude, mm/s^2
    gimbal_deg: float = 180.0
    sep_both_sides: bool = True
    sep_policy: str = "always"
    sun_tilt_deg: float = 0.0          # inclination of Sun line out of the Earth-Moon plane

    @property
    def ac(self):
        return self.a_c_mm / A_EM_MMS2

    @property
    def asep(self):
        return self.a_sep_mm / A_EM_MMS2


def sun_direction(B, t, theta0, tilt_deg=0.0):
    """Unit vector barycentre -> Sun in the rotating frame (N,3)."""
    th = theta0 - OMEGA_SUN_SYNODIC * t
    # The Sun's elevation above the lunar orbit plane (|beta| <= 5.1 deg) changes
    # over the 346.6-day eclipse year, i.e. it is ~constant within one month.
    ct = math.cos(math.radians(tilt_deg)); st = math.sin(math.radians(tilt_deg))
    return B.stack([B.cos(th) * ct, B.sin(th) * ct, B.sin(th) * 0 + st])


def shadow_factor(B, r, u_sun, mu=MU):
    rE = r - B.asarray([-mu, 0.0, 0.0])
    rM = r - B.asarray([1 - mu, 0.0, 0.0])
    from .environment import cylindrical_shadow
    return cylindrical_shadow(B, rE, u_sun, RE_ND) * cylindrical_shadow(B, rM, u_sun, RM_ND)


def solar_tidal(B, r, u_sun):
    rs = A_SUN_ND * u_sun
    d = rs - r
    dn = B.norm(d, keepdims=True)
    return MASS_SUN_ND * (d / dn ** 3 - rs / A_SUN_ND ** 3)


def propagate_batch(X0, t_end, craft: SailCraftND, law="jacobi", law_sign=+1.0, theta0=0.0,
                    h=2e-3, solar_gravity=False, backend=None, C_target=None, record_every=50,
                    control_fn=None, stop_r_far=3.0):
    """RK4 propagation of N states with a steering law.

    law 'jacobi'  : maximise +/- dC/dt (law_sign=+1 pushes along velocity, lowering C)
    law 'feather' : sail edge-on (natural motion + residual)
    law 'custom'  : control_fn(B, t, X, u_sun, lit) -> (N,3) acceleration
    Returns dict with event times (C reached), histories, final states.
    """
    B = get_backend(backend)
    X = B.asarray(X0)
    N = X.shape[0]
    th0 = B.asarray(np.broadcast_to(np.asarray(theta0, float), (N,)).copy())
    face = craft.material.front
    t = 0.0
    nsteps = int(math.ceil(t_end / h))
    t_hit = np.full(N, np.nan)
    status = np.zeros(N, int)
    active = np.ones(N, bool)
    hist = [B.to_numpy(X).copy()]
    hist_t = [0.0]

    def acc_ctrl(tt, Xs):
        r, v = Xs[:, :3], Xs[:, 3:]
        u = sun_direction(B, tt, th0, craft.sun_tilt_deg)
        lit = shadow_factor(B, r, u)
        s_hat = -u
        if law == "custom":
            a = control_fn(B, tt, Xs, u, lit)
        elif law == "feather":
            a = 0 * r
        else:
            d = law_sign * v / B.maximum(B.norm(v, keepdims=True), 1e-12)
            if craft.a_sep_mm > 0:
                res = S.best_hybrid(B, face, s_hat, d, craft.ac * lit, craft.asep, gimbal_deg=craft.gimbal_deg,
                                    both_sides=craft.sep_both_sides, sep_policy=craft.sep_policy, n_alpha=91)
                n = res["n_hat"]
                a = S.sail_accel(B, face, craft.material.back, s_hat, n, craft.ac, lit=lit) + res["comp_sep"][..., None] * d
            else:
                n, _ = S.optimal_normal(B, face, s_hat, d)
                a = S.sail_accel(B, face, craft.material.back, s_hat, n, craft.ac, lit=lit)
        if solar_gravity:
            a = a + solar_tidal(B, r, u)
        return a

    def f(tt, Xs):
        r, v = Xs[:, :3], Xs[:, 3:]
        a = accel_gc(B, r) + acc_ctrl(tt, Xs)
        ax = a[:, 0] + 2 * v[:, 1]
        ay = a[:, 1] - 2 * v[:, 0]
        return B.stack([v[:, 0], v[:, 1], v[:, 2], ax, ay, a[:, 2]], axis=1)

    for n in range(nsteps):
        k1 = f(t, X)
        k2 = f(t + h / 2, X + h / 2 * k1)
        k3 = f(t + h / 2, X + h / 2 * k2)
        k4 = f(t + h, X + h * k3)
        Xn = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        act = B.asarray(active.astype(float))[:, None]
        X = Xn * act + X * (1 - act)
        t += h
        Xnp = B.to_numpy(X)
        r2 = np.linalg.norm(Xnp[:, :3] - [1 - MU, 0, 0], axis=1)
        r1 = np.linalg.norm(Xnp[:, :3] - [-MU, 0, 0], axis=1)
        crash = active & ((r2 < RM_ND) | (r1 < RE_ND))
        far = active & (np.linalg.norm(Xnp[:, :3], axis=1) > stop_r_far)
        if C_target is not None:
            C = jacobi(Xnp)
            hit = active & ((C - C_target) * (-law_sign) >= 0) if np.ndim(C_target) == 0 else active & ((C - np.asarray(C_target)) * (-law_sign) >= 0)
            t_hit[hit] = t
            status[hit] = 1
            active &= ~hit
        status[crash] = 2
        status[far] = 3
        active &= ~(crash | far)
        if (n + 1) % record_every == 0:
            hist.append(Xnp.copy()); hist_t.append(t)
        if not active.any():
            break
    hist.append(B.to_numpy(X).copy()); hist_t.append(t)
    return {"t_hit": t_hit, "status": status, "hist": np.array(hist), "hist_t": np.array(hist_t),
            "X": B.to_numpy(X)}


def to_days(t_nd):
    return np.asarray(t_nd) * T_EM_S / DAY_S


def to_km(r_nd):
    return np.asarray(r_nd) * L_EM_KM
