"""Minimum-time cislunar transfers by batched, differentiable multiple shooting.

Feedback guidance cannot hold a low-thrust vehicle in the unstable L1/L2
region (instability e-folding ~1.7 d), so transfers are computed as optimal
control problems instead:

* The trajectory is split into K segments; interior node states are free
  variables, so gradients never pass through more than one segment (~3-4 days)
  and the chaotic dynamics stay well conditioned.
* Departure and arrival points slide continuously along the source/target
  periodic orbits (Fourier-series orbit models), so phasing is optimised too.
* Sail attitude (cone, clock) and, for hybrids, SEP gimbal angle/azimuth/throttle
  are piecewise constant on K*S sub-arcs, mapped through sigmoids so every
  control is physically admissible (the sail can never push sunward).
* All segments of all problems integrate simultaneously (one [B*K] batch) with
  RK4; autograd provides the gradients and Adam drives the continuity defects
  to zero.
* Time of flight is fixed per batch member; a TOF grid x Sun-phase x multi-start
  batch is solved at once and the shortest converged TOF is the transit time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch

from . import backend
from . import constants as C
from . import cr3bp
from .spacecraft import Spacecraft, normal_force_coeff


# ---------------------------------------------------------------------------
# Fourier model of a periodic orbit (differentiable evaluation at any phase)
# ---------------------------------------------------------------------------
class FourierOrbit:
    def __init__(self, orbit: cr3bp.PeriodicOrbit, harmonics=48):
        st = orbit.states
        n = len(st)
        c = np.fft.rfft(st, axis=0) / n
        H = min(harmonics, c.shape[0] - 1)
        self.name = orbit.name
        self.period = orbit.period
        self.a0 = backend.tensor(c[0].real)
        self.ak = backend.tensor(2 * c[1:H + 1].real)   # [H, 6]
        self.bk = backend.tensor(-2 * c[1:H + 1].imag)
        self.k = backend.tensor(np.arange(1, H + 1))

    def __call__(self, phase):
        """phase: [...] in revolutions -> state [..., 6]."""
        ang = 2 * math.pi * phase[..., None] * self.k
        return self.a0 + torch.cos(ang) @ self.ak + torch.sin(ang) @ self.bk

    def deriv(self, phase):
        """d state / d phase (per revolution)."""
        ang = 2 * math.pi * phase[..., None] * self.k
        w = 2 * math.pi * self.k
        return (-torch.sin(ang) * w) @ self.ak + (torch.cos(ang) * w) @ self.bk


def stacked_eval(models, idx, phase, deriv=False):
    """Evaluate orbit models[idx[b]] (or their phase derivative) at phase[b] for a mixed batch."""
    out = torch.zeros(*phase.shape, 6, dtype=phase.dtype, device=phase.device)
    for i, mdl in enumerate(models):
        mask = idx == i
        if mask.any():
            out[mask] = mdl.deriv(phase[mask]) if deriv else mdl(phase[mask])
    return out


# ---------------------------------------------------------------------------
# Problem definition
# ---------------------------------------------------------------------------
@dataclass
class ShootingConfig:
    K: int = 32                 # segments
    S: int = 4                  # control sub-arcs per segment
    steps_per_arc: int = 6      # RK4 steps per sub-arc
    iters: int = 1500
    lr: float = 3e-3
    lr_final: float = 2e-5
    sigma_r_km: float = 50.0    # loss scales for defects
    sigma_v_ms: float = 0.5
    tol_r_km: float = 200.0     # success: every defect below these
    tol_v_ms: float = 2.0
    throttle_weight: float = 1e-3


def _craft_params(craft: list[Spacecraft]):
    t = backend.tensor
    k_sail, fo = [], []
    for c in craft:
        if c.sail:
            f = c.sail.mat.front
            b = c.sail.back_optics
            k_sail.append(C.SOLAR_PRESSURE_1AU * c.sail.area / c.mass / C.AU_ACC)
            fo.append([f.r, f.s, f.B, b.B, f.eps, b.eps])
        else:
            k_sail.append(0.0)
            fo.append([0, 0, 0, 0, 1, 1])
    return dict(
        k_sail=t(k_sail), optics=t(fo),
        k_sep=t([c.sep.thrust / c.mass / C.AU_ACC for c in craft]),
        gimbal=t([math.radians(c.sep.gimbal_max_deg) for c in craft]),
        axis=t([c.sep.axis_sign for c in craft]),
        mdot=t([c.sep.thrust / (C.G0 * c.sep.isp) if c.sep.enabled else 0.0 for c in craft]),
    )


def control_accel(raw, sun_hat, p, lit):
    """raw [..., 5] -> acceleration [..., 3] (nondim) and throttle [...].

    raw = (cone, clock, gimbal, azimuth, throttle) unconstrained.
    p entries are pre-broadcast to raw[..., 0].shape.
    """
    us = -sun_hat  # Sun -> spacecraft
    z = torch.zeros_like(us) + torch.tensor([0.0, 0.0, 1.0], dtype=us.dtype, device=us.device)
    e2 = torch.linalg.cross(z, us)
    e2 = e2 / e2.norm(dim=-1, keepdim=True)
    e3 = torch.linalg.cross(us, e2)
    alpha = 0.5 * math.pi * torch.sigmoid(raw[..., 0])
    delta = raw[..., 1]
    w = torch.cos(delta)[..., None] * e2 + torch.sin(delta)[..., None] * e3
    ca, sa = torch.cos(alpha), torch.sin(alpha)
    n = ca[..., None] * us + sa[..., None] * w
    t = sa[..., None] * us - ca[..., None] * w
    r, s, bl, bo, el, eo = p["optics"].unbind(-1)
    fn = (1 + r * s) * ca * ca + bl * (1 - s) * r * ca + (1 - r) * (el * bl - eo * bo) / (el + eo) * ca
    ft = (1 - r * s) * ca * sa
    a = (p["k_sail"] * lit)[..., None] * (fn[..., None] * n + ft[..., None] * t)
    # SEP
    axis = p["axis"][..., None] * n
    ref = torch.where(((axis * e2).sum(-1, keepdim=True)).abs() > 0.9, e3, e2)
    w1 = torch.linalg.cross(axis, ref)
    w1 = w1 / w1.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    w2 = torch.linalg.cross(axis, w1)
    g = p["gimbal"] * torch.sigmoid(raw[..., 2])
    psi = raw[..., 3]
    sdir = torch.cos(g)[..., None] * axis + torch.sin(g)[..., None] * (torch.cos(psi)[..., None] * w1 + torch.sin(psi)[..., None] * w2)
    thr = torch.sigmoid(raw[..., 4]) * (p["k_sep"] > 0)
    a = a + (p["k_sep"] * thr * lit)[..., None] * sdir
    return a, thr


@dataclass
class TransferBatch:
    src_idx: torch.Tensor      # [B] index into orbit models
    dst_idx: torch.Tensor
    craft_idx: torch.Tensor    # [B] index into craft list
    tof: torch.Tensor          # [B] nondim
    sun0: torch.Tensor         # [B] Sun phase at departure (rad)
    phiA0: torch.Tensor        # [B] initial guess departure phase (rev)
    phiB0: torch.Tensor


def solve(models, craft, batch: TransferBatch, cfg=ShootingConfig(), progress=False, seed=0):
    torch.manual_seed(seed)
    dev, dt_ = backend.device(), backend.dtype()
    B, K, S, n_st = batch.tof.shape[0], cfg.K, cfg.S, cfg.steps_per_arc
    cp = _craft_params(craft)
    p = {k: v[batch.craft_idx] for k, v in cp.items()}
    p_arc = {k: v[:, None, None].expand(B, K, S) if v.dim() == 1 else v[:, None, None, :].expand(B, K, S, v.shape[-1])
             for k, v in p.items()}
    periodA = torch.tensor([models[i].period for i in batch.src_idx.tolist()], dtype=dt_, device=dev)
    periodB = torch.tensor([models[i].period for i in batch.dst_idx.tolist()], dtype=dt_, device=dev)

    h = batch.tof / K
    tk = torch.arange(K, dtype=dt_, device=dev)[None] * h[:, None]  # segment start times [B,K]
    # initial guess: blend of "still on A" and "already on B" along natural motion
    s_blend = torch.arange(1, K, dtype=dt_, device=dev)[None] / K
    w = 0.5 - 0.5 * torch.cos(math.pi * s_blend)
    tin = tk[:, 1:]
    XA = stacked_eval(models, batch.src_idx[:, None].expand(B, K - 1), batch.phiA0[:, None] + tin / periodA[:, None])
    XB = stacked_eval(models, batch.dst_idx[:, None].expand(B, K - 1),
                      batch.phiB0[:, None] - (batch.tof[:, None] - tin) / periodB[:, None])
    X_int = ((1 - w[..., None]) * XA + w[..., None] * XB).clone().requires_grad_(True)
    phiA = batch.phiA0.clone().requires_grad_(True)
    phiB = batch.phiB0.clone().requires_grad_(True)
    raw = torch.zeros(B, K, S, 5, dtype=dt_, device=dev)
    raw[..., 0] = 0.5
    raw[..., 1] = torch.rand(B, K, S, dtype=dt_, device=dev) * 2 * math.pi
    raw[..., 4] = -1.0
    raw.requires_grad_(True)

    opt = torch.optim.Adam([X_int, phiA, phiB, raw], lr=cfg.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, cfg.iters, eta_min=cfg.lr_final)
    sr = cfg.sigma_r_km * 1e3 / C.LU
    sv = cfg.sigma_v_ms / C.VU
    arc_dt = (h / (S * n_st))[:, None]  # [B,1]

    def forward():
        X0 = stacked_eval(models, batch.src_idx, phiA)
        XK = stacked_eval(models, batch.dst_idx, phiB + batch.tof / periodB)
        starts = torch.cat((X0[:, None], X_int), 1)          # [B,K,6]
        x = starts
        t = tk.clone()
        thr_sum = 0.0
        for j in range(S):
            sun = cr3bp.sun_dir(t, batch.sun0[:, None])
            lit = cr3bp.sunlit(x[..., :3], sun).to(dt_)
            a_c, thr = control_accel(raw[:, :, j], sun, {k: v[:, :, j] for k, v in p_arc.items()}, lit)
            thr_sum = thr_sum + thr
            for _ in range(n_st):
                def f(y):
                    return torch.cat((y[..., 3:], cr3bp.accel_natural(y[..., :3], y[..., 3:]) + a_c), -1)
                dt = arc_dt[..., None]
                k1 = f(x)
                k2 = f(x + 0.5 * dt * k1)
                k3 = f(x + 0.5 * dt * k2)
                k4 = f(x + dt * k3)
                x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            t = t + arc_dt * n_st
        targets = torch.cat((X_int, XK[:, None]), 1)
        defect = x - targets
        return defect, thr_sum / S, starts, XK

    best = None
    for it in range(cfg.iters):
        opt.zero_grad()
        defect, thr, _, _ = forward()
        dr = defect[..., :3] / sr
        dv = defect[..., 3:] / sv
        per = (dr**2).sum(-1) + (dv**2).sum(-1)          # [B,K]
        loss_b = per.mean(-1) + cfg.throttle_weight * thr.mean(-1)
        # log-barrier-like scaling keeps large-defect members from dominating gradients
        loss = torch.log1p(loss_b).sum()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([raw], 1e3)
        opt.step()
        sched.step()
        if progress and (it % 250 == 0 or it == cfg.iters - 1):
            with torch.no_grad():
                mr = defect[..., :3].norm(dim=-1).max(-1).values * C.LU / 1e3
                mv = defect[..., 3:].norm(dim=-1).max(-1).values * C.VU
                ok = (mr < cfg.tol_r_km) & (mv < cfg.tol_v_ms)
                print(f"    iter {it:5d} loss {float(loss):10.2f} median max-defect {float(mr.median()):9.1f} km "
                      f"{float(mv.median()):7.2f} m/s  converged {int(ok.sum())}/{B}")

    with torch.no_grad():
        defect, thr, starts, XK = forward()
        mr = defect[..., :3].norm(dim=-1).max(-1).values * C.LU / 1e3
        mv = defect[..., 3:].norm(dim=-1).max(-1).values * C.VU
        ok = (mr < cfg.tol_r_km) & (mv < cfg.tol_v_ms)
        prop = (thr * p["mdot"][:, None]).sum(-1) * h * C.TU * (p["k_sep"] > 0)
    return dict(ok=ok.cpu(), max_dr_km=mr.cpu(), max_dv_ms=mv.cpu(), tof_days=(batch.tof * C.TU / C.DAY).cpu(),
                prop_kg=prop.cpu(), nodes=torch.cat((starts, XK[:, None]), 1).detach().cpu(),
                raw=raw.detach().cpu(), phiA=phiA.detach().cpu(), phiB=phiB.detach().cpu())


def dense_trajectory(models, craft, batch: TransferBatch, sol, b, cfg=ShootingConfig(), substeps=4):
    """Re-integrate member b segment-by-segment (from its nodes) for plotting. Returns [N,6] numpy."""
    cp = _craft_params(craft)
    ci = int(batch.craft_idx[b])
    p = {k: v[ci] for k, v in cp.items()}
    nodes = sol["nodes"][b].to(backend.device(), backend.dtype())
    raw = sol["raw"][b].to(backend.device(), backend.dtype())
    tof = float(batch.tof[b])
    K, S, n = cfg.K, cfg.S, cfg.steps_per_arc * substeps
    h = tof / K
    dt = h / (S * n)
    out = []
    for k in range(K):
        x = nodes[k].clone()
        t = torch.tensor(k * h, dtype=x.dtype, device=x.device)
        for j in range(S):
            sun = cr3bp.sun_dir(t, batch.sun0[b])
            lit = cr3bp.sunlit(x[None, :3], sun[None])[0].to(x.dtype)
            a_c, _ = control_accel(raw[k, j], sun, p, lit)
            for _ in range(n):
                out.append(x.cpu().numpy().copy())
                def f(y):
                    return torch.cat((y[3:], cr3bp.accel_natural(y[None, :3], y[None, 3:])[0] + a_c))
                k1 = f(x); k2 = f(x + 0.5 * dt * k1); k3 = f(x + 0.5 * dt * k2); k4 = f(x + dt * k3)
                x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
                t = t + dt
    out.append(x.cpu().numpy())
    return np.array(out)


# ---------------------------------------------------------------------------
# Levenberg-Marquardt multiple shooting (default solver)
# ---------------------------------------------------------------------------
def _segment(x, u, t0, sun0, h, prm, S, n_st):
    """Propagate one segment (single member, unbatched -> vmapped). x[6], u[S,5]."""
    dt = h / (S * n_st)
    for j in range(S):
        t = t0 + j * h / S
        sun = cr3bp.sun_dir(t, sun0)
        lit = cr3bp.sunlit(x[:3], sun).to(x.dtype)
        a_c, _ = control_accel(u[j], sun, prm, lit)
        for _ in range(n_st):
            def f(y):
                return torch.cat((y[3:], cr3bp.accel_natural(y[:3], y[3:]) + a_c))
            k1 = f(x)
            k2 = f(x + 0.5 * dt * k1)
            k3 = f(x + 0.5 * dt * k2)
            k4 = f(x + dt * k3)
            x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return x


def solve_lm(models, craft, batch: TransferBatch, cfg=ShootingConfig(), iters=40, progress=False,
             seed=0, chunk=256, accel_scale=1.0, init=None):
    from torch.func import jacfwd, vmap
    torch.manual_seed(seed)
    dev, dt_ = backend.device(), backend.dtype()
    B, K, S, n_st = batch.tof.shape[0], cfg.K, cfg.S, cfg.steps_per_arc
    cp = _craft_params(craft)
    prm_b = {k: v[batch.craft_idx] for k, v in cp.items()}
    prm_b["k_sail"] = prm_b["k_sail"] * accel_scale
    prm_b["k_sep"] = prm_b["k_sep"] * accel_scale
    periodA = torch.tensor([models[i].period for i in batch.src_idx.tolist()], dtype=dt_, device=dev)
    periodB = torch.tensor([models[i].period for i in batch.dst_idx.tolist()], dtype=dt_, device=dev)
    h = batch.tof / K
    tk = torch.arange(K, dtype=dt_, device=dev)[None] * h[:, None]
    s_blend = torch.arange(1, K, dtype=dt_, device=dev)[None] / K
    w = (s_blend >= 0.5).to(dt_)  # piecewise guess: on source orbit, then on target orbit (all nodes physical)
    XA = stacked_eval(models, batch.src_idx[:, None].expand(B, K - 1), batch.phiA0[:, None] + tk[:, 1:] / periodA[:, None])
    XB = stacked_eval(models, batch.dst_idx[:, None].expand(B, K - 1),
                      batch.phiB0[:, None] - (batch.tof[:, None] - tk[:, 1:]) / periodB[:, None])
    X_int = (1 - w[..., None]) * XA + w[..., None] * XB
    phiA, phiB = batch.phiA0.clone(), batch.phiB0.clone()
    U = torch.zeros(B, K, S, 5, dtype=dt_, device=dev)
    U[..., 0] = 0.5
    U[..., 1] = torch.rand(B, K, S, dtype=dt_, device=dev) * 2 * math.pi
    U[..., 4] = -1.0
    if init is not None:
        phiA, phiB = init["phiA"].clone(), init["phiB"].clone()
        X_int, U = init["nodes"][:, 1:-1].clone(), init["raw"].clone()

    scale = torch.tensor([1 / (cfg.sigma_r_km * 1e3 / C.LU)] * 3 + [1 / (cfg.sigma_v_ms / C.VU)] * 3, dtype=dt_, device=dev)
    seg_v = vmap(lambda x, u, t0, s0, hh, prm: _segment(x, u, t0, s0, hh, prm, S, n_st))
    seg_j = vmap(jacfwd(lambda x, u, t0, s0, hh, prm: _segment(x, u, t0, s0, hh, prm, S, n_st), argnums=(0, 1)))

    def flat_args(Xs, Uu, idx):
        n = idx.shape[0]
        prm = {k: v[idx][:, None].expand(n, K, *v.shape[1:]).reshape(n * K, *v.shape[1:]) for k, v in prm_b.items()}
        return (Xs.reshape(n * K, 6), Uu.reshape(n * K, S, 5), tk[idx].reshape(-1),
                batch.sun0[idx][:, None].expand(n, K).reshape(-1), h[idx][:, None].expand(n, K).reshape(-1), prm)

    def endpoints(pA, pB, idx):
        X0 = stacked_eval(models, batch.src_idx[idx], pA)
        XK = stacked_eval(models, batch.dst_idx[idx], pB + batch.tof[idx] / periodB[idx])
        return X0, XK

    def residual(Xi, pA, pB, Uu, idx):
        X0, XK = endpoints(pA, pB, idx)
        starts = torch.cat((X0[:, None], Xi), 1)
        ends = seg_v(*flat_args(starts, Uu, idx)).reshape(len(idx), K, 6)
        tgt = torch.cat((Xi, XK[:, None]), 1)
        return (ends - tgt) * scale, starts

    lam = torch.full((B,), 1e-2, dtype=dt_, device=dev)
    nvar = 1 + (K - 1) * 6 + 1 + K * S * 5
    for it in range(iters):
        for c0 in range(0, B, chunk):
            idx = torch.arange(c0, min(B, c0 + chunk), device=dev)
            n = len(idx)
            r, starts = residual(X_int[idx], phiA[idx], phiB[idx], U[idx], idx)
            Jx, Ju = seg_j(*flat_args(starts, U[idx], idx))
            Jx = Jx.reshape(n, K, 6, 6) * scale[:, None]
            Ju = Ju.reshape(n, K, 6, S * 5) * scale[:, None]
            J = torch.zeros(n, K * 6, nvar, dtype=dt_, device=dev)
            dA = stacked_eval(models, batch.src_idx[idx], phiA[idx], deriv=True)
            dB = stacked_eval(models, batch.dst_idx[idx], phiB[idx] + batch.tof[idx] / periodB[idx], deriv=True)
            col_u = 2 + (K - 1) * 6
            for k in range(K):
                rows = slice(6 * k, 6 * k + 6)
                if k == 0:
                    J[:, rows, 0] = (Jx[:, 0] @ dA[..., None])[..., 0]
                else:
                    J[:, rows, 1 + 6 * (k - 1):1 + 6 * k] = Jx[:, k]
                if k < K - 1:
                    J[:, rows, 1 + 6 * k:1 + 6 * (k + 1)] = -torch.diag(scale)
                else:
                    J[:, rows, 1 + (K - 1) * 6] = -dB * scale
                J[:, rows, col_u + k * S * 5: col_u + (k + 1) * S * 5] = Ju[:, k]
            rv = r.reshape(n, -1)
            cost0 = (rv**2).sum(-1)
            JJt = J @ J.transpose(1, 2)
            accepted = torch.zeros(n, dtype=torch.bool, device=dev)
            for _try in range(4):
                A = JJt + lam[idx, None, None] * torch.eye(K * 6, dtype=dt_, device=dev)
                y = torch.linalg.solve(A, rv[..., None])
                dz = -(J.transpose(1, 2) @ y)[..., 0]
                # trust region on node states (~0.05 LU) and controls
                dz = dz / (dz.abs().max(-1, keepdim=True).values / 0.5).clamp_min(1.0)
                nA = phiA[idx] + dz[:, 0]
                nX = X_int[idx] + dz[:, 1:1 + (K - 1) * 6].reshape(n, K - 1, 6)
                nB = phiB[idx] + dz[:, 1 + (K - 1) * 6]
                nU = U[idx] + dz[:, col_u:].reshape(n, K, S, 5)
                r1, _ = residual(nX, nA, nB, nU, idx)
                cost1 = (r1.reshape(n, -1) ** 2).sum(-1)
                good = (cost1 < cost0) & torch.isfinite(cost1) & ~accepted
                sel = idx[good]
                phiA[sel], phiB[sel] = nA[good], nB[good]
                X_int[sel], U[sel] = nX[good], nU[good]
                lam[sel] = (lam[sel] / 3).clamp_min(1e-9)
                bad = idx[~good & ~accepted]
                lam[bad] = lam[bad] * 8
                accepted = accepted | good
                if accepted.all():
                    break
        if progress and (it % 5 == 0 or it == iters - 1):
            with torch.no_grad():
                r, _ = residual(X_int, phiA, phiB, U, torch.arange(B, device=dev))
                d = r / scale
                mr = d[..., :3].norm(dim=-1).max(-1).values * C.LU / 1e3
                mv = d[..., 3:].norm(dim=-1).max(-1).values * C.VU
                ok = (mr < cfg.tol_r_km) & (mv < cfg.tol_v_ms)
                print(f"    LM iter {it:3d}: median max-defect {float(mr.median()):9.2f} km {float(mv.median()):8.3f} m/s converged {int(ok.sum())}/{B}")

    idx = torch.arange(B, device=dev)
    r, starts = residual(X_int, phiA, phiB, U, idx)
    d = r / scale
    mr = d[..., :3].norm(dim=-1).max(-1).values * C.LU / 1e3
    mv = d[..., 3:].norm(dim=-1).max(-1).values * C.VU
    ok = (mr < cfg.tol_r_km) & (mv < cfg.tol_v_ms)
    thr = torch.sigmoid(U[..., 4]).mean(-1) * (prm_b["k_sep"][:, None] > 0)
    prop = (thr * prm_b["mdot"][:, None]).sum(-1) * h * C.TU
    X0, XK = endpoints(phiA, phiB, idx)
    nodes = torch.cat((starts, XK[:, None]), 1)
    # closest approach to the Moon along nodes (dense check done by caller via dense_trajectory)
    return dict(ok=ok, max_dr_km=mr, max_dv_ms=mv, tof_days=batch.tof * C.TU / C.DAY,
                prop_kg=prop, nodes=nodes, raw=U, phiA=phiA, phiB=phiB)


def solve_homotopy(models, craft, batch, cfg=ShootingConfig(), scales=(8, 4, 2.5, 1.6, 1.25, 1.0),
                   iters_per=12, final_iters=25, progress=False):
    """Continuation in thrust level: easy (high-acceleration) problem first, warm-start downward."""
    sol = None
    for i, sc in enumerate(scales):
        it = final_iters if i == len(scales) - 1 else iters_per
        sol = solve_lm(models, craft, batch, cfg, iters=it, accel_scale=sc, init=sol)
        if progress:
            print(f"  accel x{sc:<5}: converged {int(sol['ok'].sum())}/{len(sol['ok'])}, "
                  f"median max-defect {float(sol['max_dr_km'].median()):.1f} km")
    return {k: (v.cpu() if torch.is_tensor(v) else v) for k, v in sol.items()}
