"""Batched cislunar transfers in the sail-augmented CR3BP.

Guidance: feedback tracking toward the *nearest* state on the target orbit
(phase-free), d = -(dr / tau^2 + 2 dv / tau), blended with a Jacobi-energy term
that drives C toward the target orbit's value. The candidate-attitude
controller then realises the best achievable acceleration along d.

Every departure phase x Sun phase x spacecraft x orbit pair is an independent
batch member, so thousands of transfers run as one tensor program and the
fastest successful one is reported. Times are therefore *achievable upper
bounds* from a feedback law, not optimal-control minima (typically within
10-30% of optimal for low-thrust problems of this kind).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch

from . import backend
from . import constants as C
from . import control, cr3bp
from .spacecraft import Batch


@dataclass
class TransferSetup:
    tau: float = 1.0            # guidance time constant (TU)
    w_jacobi: float = 1.0       # weight of Jacobi-energy shaping
    vel_weight: float = 0.5     # TU; distance metric |dr|^2 + (vel_weight*|dv|)^2
    tol_r_km: float = 2000.0
    tol_v_ms: float = 20.0
    dt_max: float = 4e-3
    dt_min: float = 2e-4
    k_candidates: int = 128


def _targets_tensor(orbits):
    M = max(len(o.states) for o in orbits)
    arr = np.zeros((len(orbits), M, 6))
    for i, o in enumerate(orbits):
        st = o.states
        reps = int(math.ceil(M / len(st)))
        arr[i] = np.tile(st, (reps, 1))[:M]
    return backend.tensor(arr), backend.tensor([o.jacobi for o in orbits])


def propagate(craft: Batch, state0, target_idx, orbits, sun_phase0, t_max_days, setup=TransferSetup(),
              record_every=20, progress=False):
    """Propagate B transfers. Returns dict with arrival time (days, nan if none), success, history."""
    dev, dt_ = backend.device(), backend.dtype()
    T_states, T_jac = _targets_tensor(orbits)
    B = state0.shape[0]
    tgt = T_states[target_idx]  # [B, M, 6]
    cj_t = T_jac[target_idx]
    s = state0.clone()
    m = craft.mass0.clone()
    t = torch.zeros(B, dtype=dt_, device=dev)
    t_max = t_max_days * C.DAY / C.TU
    arrived = torch.zeros(B, dtype=torch.bool, device=dev)
    crashed = torch.zeros_like(arrived)
    t_arr = torch.full((B,), float("nan"), dtype=dt_, device=dev)
    tol_r = setup.tol_r_km * 1e3 / C.LU
    tol_v = setup.tol_v_ms / C.VU
    hist_r, hist_t = [], []
    moon = torch.tensor([1 - cr3bp.MU, 0, 0], dtype=dt_, device=dev)
    earth = torch.tensor([-cr3bp.MU, 0, 0], dtype=dt_, device=dev)
    step = 0
    with torch.no_grad():
        while True:
            active = ~(arrived | crashed) & (t < t_max)
            if not active.any():
                break
            r, v = s[:, :3], s[:, 3:]
            # nearest target state
            dr_all = tgt[:, :, :3] - r[:, None]
            dv_all = tgt[:, :, 3:] - v[:, None]
            metric = (dr_all**2).sum(-1) + setup.vel_weight**2 * (dv_all**2).sum(-1)
            j = metric.argmin(-1)
            ts = tgt[torch.arange(B, device=dev), j]
            dr = r - ts[:, :3]
            dv = v - ts[:, 3:]
            err_r, err_v = dr.norm(dim=-1), dv.norm(dim=-1)
            newly = active & (err_r < tol_r) & (err_v < tol_v)
            t_arr = torch.where(newly, t, t_arr)
            arrived = arrived | newly
            # guidance direction
            d = -(dr / setup.tau**2 + 2 * dv / setup.tau)
            cj = cr3bp.jacobi(s)
            vhat = v / v.norm(dim=-1, keepdim=True).clamp_min(1e-9)
            dC = (cj_t - cj).clamp(-0.05, 0.05) / 0.05
            d = d + setup.w_jacobi * (-dC)[:, None] * vhat * d.norm(dim=-1, keepdim=True).clamp_min(1e-3)
            sun = cr3bp.sun_dir(t, sun_phase0)
            lit = cr3bp.sunlit(r, sun)
            ctx = control.ControlContext(craft, m, d[:, None], (-sun)[:, None], lit[:, None],
                                         sep_ok=(m - craft.dry_mass) > 1e-3)
            ch = control.choose(ctx, k=setup.k_candidates, refine=(5.0, 2.5))
            a_c = ch["accel"][:, 0] / C.AU_ACC
            mdot = ch["sep_on"][:, 0].to(dt_) * craft.sep_mdot * C.TU
            # adaptive step from distance to primaries
            r2 = (r - moon).norm(dim=-1)
            r1 = (r - earth).norm(dim=-1)
            dt = (0.02 * torch.minimum(r2, r1) ** 1.5).clamp(setup.dt_min, setup.dt_max)
            dt = torch.where(active, dt, torch.zeros_like(dt))

            def f(x):
                return torch.cat((x[:, 3:], cr3bp.accel_natural(x[:, :3], x[:, 3:]) + a_c), -1)
            k1 = f(s)
            k2 = f(s + 0.5 * dt[:, None] * k1)
            k3 = f(s + 0.5 * dt[:, None] * k2)
            k4 = f(s + dt[:, None] * k3)
            s = s + dt[:, None] / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            m = m - mdot * dt
            t = t + dt
            crashed = crashed | (active & (((s[:, :3] - moon).norm(dim=-1) < (C.R_MOON + 50e3) / C.LU)
                                           | ((s[:, :3] - earth).norm(dim=-1) < (C.R_EARTH + 300e3) / C.LU)))
            if step % record_every == 0:
                hist_r.append(s[:, :3].clone().cpu())
                hist_t.append(t.clone().cpu())
            if progress and step % 2000 == 0:
                print(f"    step {step}: t={float(t.max())*C.TU/C.DAY:6.1f} d arrived {int(arrived.sum())}/{B} crashed {int(crashed.sum())}")
            step += 1
    return dict(t_days=(t_arr * C.TU / C.DAY).cpu(), arrived=arrived.cpu(), crashed=crashed.cpu(),
                prop_used=(craft.mass0 - m).cpu(), hist_r=torch.stack(hist_r, 1), hist_t=torch.stack(hist_t, 1))


def departure_states(orbit, n_phase):
    idx = np.linspace(0, len(orbit.states), n_phase, endpoint=False).astype(int)
    return orbit.states[idx]
