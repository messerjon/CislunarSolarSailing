"""Earth-Moon circular restricted three-body problem (CR3BP) with solar-sail / SEP forcing.

Rotating barycentric frame, nondimensional units (LU = 384400 km, TU = 4.34 d).
The Sun direction rotates at the synodic rate in this frame (planar; the 5 deg
lunar inclination to the ecliptic is neglected). Earth and Moon cast cylindrical
shadows. Periodic orbits are generated with single-shooting differential
correction (numpy/scipy); batched trajectories are propagated with torch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from . import backend
from . import constants as C

MU = C.CR3BP_MU


# ---------------------------------------------------------------------------
# Basic geometry
# ---------------------------------------------------------------------------
def lagrange_points(mu=MU):
    def fx(x):
        r1 = x + mu
        r2 = x - 1 + mu
        return x - (1 - mu) * r1 / abs(r1) ** 3 - mu * r2 / abs(r2) ** 3
    l1 = brentq(fx, -mu + 0.5, 1 - mu - 1e-6)
    l2 = brentq(fx, 1 - mu + 1e-6, 1.5)
    l3 = brentq(fx, -1.5, -mu - 1e-6)
    return {
        "L1": np.array([l1, 0, 0]), "L2": np.array([l2, 0, 0]), "L3": np.array([l3, 0, 0]),
        "L4": np.array([0.5 - mu, math.sqrt(3) / 2, 0]), "L5": np.array([0.5 - mu, -math.sqrt(3) / 2, 0]),
    }


def jacobi(state, mu=MU):
    x, y, z, vx, vy, vz = (state[..., i] for i in range(6))
    lib = torch if torch.is_tensor(state) else np
    r1 = lib.sqrt((x + mu) ** 2 + y**2 + z**2)
    r2 = lib.sqrt((x - 1 + mu) ** 2 + y**2 + z**2)
    return x**2 + y**2 + 2 * (1 - mu) / r1 + 2 * mu / r2 - (vx**2 + vy**2 + vz**2)


def _eom_np(t, s, mu=MU):
    x, y, z, vx, vy, vz = s[:6]
    r1 = math.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = math.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    ax = 2 * vy + x - (1 - mu) * (x + mu) / r1**3 - mu * (x - 1 + mu) / r2**3
    ay = -2 * vx + y - (1 - mu) * y / r1**3 - mu * y / r2**3
    az = -(1 - mu) * z / r1**3 - mu * z / r2**3
    return np.array([vx, vy, vz, ax, ay, az])


def _eom_stm(t, s, mu=MU):
    x, y, z = s[:3]
    r1 = math.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = math.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    d = _eom_np(t, s, mu)
    # Hessian of the effective potential
    a1, a2 = (1 - mu) / r1**3, mu / r2**3
    b1, b2 = 3 * (1 - mu) / r1**5, 3 * mu / r2**5
    dx1, dx2 = x + mu, x - 1 + mu
    Uxx = 1 - a1 - a2 + b1 * dx1**2 + b2 * dx2**2
    Uyy = 1 - a1 - a2 + (b1 + b2) * y * y
    Uzz = -a1 - a2 + (b1 + b2) * z * z
    Uxy = (b1 * dx1 + b2 * dx2) * y
    Uxz = (b1 * dx1 + b2 * dx2) * z
    Uyz = (b1 + b2) * y * z
    A = np.zeros((6, 6))
    A[0:3, 3:6] = np.eye(3)
    A[3:6, 0:3] = [[Uxx, Uxy, Uxz], [Uxy, Uyy, Uyz], [Uxz, Uyz, Uzz]]
    A[3, 4], A[4, 3] = 2, -2
    phi = s[6:].reshape(6, 6)
    return np.concatenate((d, (A @ phi).ravel()))


def _cross_y(t, s, *a):
    return s[1]


def _half_period(state0, with_stm=True, t_max=10.0):
    ev = _cross_y
    ev.terminal = True
    ev.direction = 0
    s0 = np.concatenate((state0, np.eye(6).ravel())) if with_stm else state0
    f = _eom_stm if with_stm else _eom_np
    # skip the t=0 crossing by starting slightly later
    sol0 = solve_ivp(f, (0, 1e-3), s0, rtol=1e-11, atol=1e-12)
    sol = solve_ivp(f, (1e-3, t_max), sol0.y[:, -1], events=ev, rtol=1e-11, atol=1e-12)
    if not sol.t_events[0].size:
        return None, None
    return sol.t_events[0][0], sol.y_events[0][0]


def correct_planar(x0, vy0, iters=30):
    """Symmetric planar periodic orbit through (x0,0) with velocity (0,vy0): solve vx(T/2)=0 for vy0."""
    for _ in range(iters):
        th, s = _half_period(np.array([x0, 0, 0, 0, vy0, 0]))
        if th is None:
            return None
        phi = s[6:].reshape(6, 6)
        d = _eom_np(0, s[:6])
        vx, vy = s[3], s[4]
        # d vx_f / d vy0 including change of crossing time
        dvx = phi[3, 4] - d[3] / vy * phi[1, 4]
        step = -vx / dvx
        vy0 += np.clip(step, -0.05, 0.05)
        if abs(vx) < 1e-10:
            return np.array([x0, 0, 0, 0, vy0, 0]), 2 * th
    return None


def correct_halo(x0, z0, vy0, iters=40):
    """3-D symmetric orbit: fix z0, vary (x0, vy0) so vx = vz = 0 at the y=0 crossing."""
    for _ in range(iters):
        th, s = _half_period(np.array([x0, 0, z0, 0, vy0, 0]))
        if th is None:
            return None
        phi = s[6:].reshape(6, 6)
        d = _eom_np(0, s[:6])
        vy = s[4]
        cols = [0, 4]
        M = np.array([[phi[r, c] - d[r] / vy * phi[1, c] for c in cols] for r in (3, 5)])
        err = np.array([s[3], s[5]])
        if np.abs(err).max() < 1e-10:
            return np.array([x0, 0, z0, 0, vy0, 0]), 2 * th
        dx = np.linalg.solve(M, -err)
        dx = np.clip(dx, -0.02, 0.02)
        x0 += dx[0]
        vy0 += dx[1]
    return None


def sample_orbit(state0, period, n=400):
    t = np.linspace(0, period, n, endpoint=False)
    sol = solve_ivp(_eom_np, (0, period), state0, t_eval=t, rtol=1e-11, atol=1e-12)
    return sol.y.T


@dataclass
class PeriodicOrbit:
    name: str
    state0: np.ndarray
    period: float
    states: np.ndarray  # [n, 6]

    @property
    def jacobi(self):
        return float(jacobi(self.state0))


def find_dro(dist_km=70000.0):
    x0 = 1 - MU - dist_km * 1e3 / C.LU
    best = None
    for vy in np.linspace(0.2, 1.2, 41):
        out = correct_planar(x0, vy)
        if out is not None:
            s0, T = out
            if s0[4] > 0 and T < 8:  # retrograde about the Moon on the Earth side
                st = sample_orbit(s0, T)
                if (np.linalg.norm(st[:, :3] - [1 - MU, 0, 0], axis=1) > 0.01).all():
                    best = PeriodicOrbit(f"DRO {dist_km/1e3:.0f}k km", s0, T, st)
                    break
    return best


def find_halo(which="L2", az_km=15000.0, south=True):
    L = lagrange_points()[which][0]
    z0 = (-1 if south else 1) * az_km * 1e3 / C.LU
    cands = []
    for dx in np.linspace(-0.08, 0.08, 33):
        x0 = L + dx
        for vy in np.linspace(-0.6, 0.6, 49):
            th, s = _half_period(np.array([x0, 0, z0, 0, vy, 0]), with_stm=False, t_max=6)
            if th is None or th < 0.5:
                continue
            cands.append((abs(s[3]) + abs(s[5]), x0, vy))
    cands.sort()
    for _, x0, vy in cands[:25]:
        out = correct_halo(x0, z0, vy)
        if out is not None:
            s0, T = out
            if 1.0 < T < 5.0:
                return PeriodicOrbit(f"{which} halo Az {az_km/1e3:.0f}k km", s0, T, sample_orbit(s0, T))
    return None


def equilibrium_target(which="L4", n=8):
    p = lagrange_points()[which]
    st = np.tile(np.concatenate((p, np.zeros(3))), (n, 1))
    return PeriodicOrbit(which, st[0], 2 * math.pi, st)


# ---------------------------------------------------------------------------
# Batched torch propagation with sail/SEP guidance
# ---------------------------------------------------------------------------
def accel_natural(r, v, mu=MU):
    x, y, z = r.unbind(-1)
    vx, vy, _ = v.unbind(-1)
    r1 = torch.sqrt((x + mu) ** 2 + y * y + z * z)
    r2 = torch.sqrt((x - 1 + mu) ** 2 + y * y + z * z)
    k1 = (1 - mu) / r1**3
    k2 = mu / r2**3
    ax = 2 * vy + x - k1 * (x + mu) - k2 * (x - 1 + mu)
    ay = -2 * vx + y - k1 * y - k2 * y
    az = -k1 * z - k2 * z
    return torch.stack((ax, ay, az), -1)


def sun_dir(t, phase0):
    """Unit vector barycentre -> Sun in the rotating frame (t nondimensional)."""
    th = phase0 - C.OMEGA_SUN_SYNODIC * t
    return torch.stack((torch.cos(th), torch.sin(th), torch.zeros_like(th)), -1)


def sunlit(r, sun):
    from .environment import cylindrical_shadow
    earth = torch.tensor([-MU, 0, 0], dtype=r.dtype, device=r.device)
    moon = torch.tensor([1 - MU, 0, 0], dtype=r.dtype, device=r.device)
    return (cylindrical_shadow(r, earth, C.R_EARTH / C.LU, sun)
            & cylindrical_shadow(r, moon, C.R_MOON / C.LU, sun))
