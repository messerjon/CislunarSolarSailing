"""Locally-optimal attitude selection by batched candidate search.

Given a desired acceleration direction `d` (from any guidance law), every
spacecraft/node evaluates K candidate sail normals on a Fibonacci sphere, plus
a "feather" attitude (edge-on to both Sun and airflow) and, for retractable
sails, a "stowed" state. Each candidate's total controllable acceleration
(sail SRP + attitude-dependent sail drag + SEP gimballed toward d) is scored by
its projection on d; the best is refined by coordinate ascent. The search is
model-agnostic (optical sail, single/double-sided, drag, SEP gimbal) and maps
naturally onto a GPU: it is one big [B, N, K, 3] tensor operation.
"""
from __future__ import annotations

import math

import torch

from . import constants as C
from .spacecraft import Batch, fibonacci_sphere, sail_force_per_area, sep_direction

_FIB = {}
# Residual projected-area fraction of a "feathered" sail (booms, wrinkles, ~2 deg pointing error).
EDGE_DRAG_FLOOR = 0.035


def candidates(k=256):
    key = (k, str(torch.get_default_dtype()))
    if key not in _FIB:
        _FIB[key] = fibonacci_sphere(k)
    return _FIB[key]


def _unit(x, eps=1e-15):
    return x / x.norm(dim=-1, keepdim=True).clamp_min(eps)


class ControlContext:
    """Per-node environment for candidate evaluation. Shapes: [B, N, 3] / [B, N]."""

    def __init__(self, craft: Batch, mass, d, u, lit, pressure=None, rho=None, v_rel=None, sep_ok=None):
        self.craft = craft
        B, N = d.shape[:2]
        self.d = d
        self.dhat = _unit(d)
        self.u = u
        self.lit = lit.to(d.dtype)
        p = C.SOLAR_PRESSURE_1AU if pressure is None else pressure
        # sail acceleration scale P*A/m  [B, N]
        self.k_sail = (p * craft.area / mass)[:, None] * self.lit
        self.rho = rho
        if rho is not None:
            vn = v_rel.norm(dim=-1)
            self.vhat = v_rel / vn[..., None].clamp_min(1e-9)
            # drag acceleration magnitude per unit projected sail area fraction [B, N]
            self.k_drag = 0.5 * rho * vn * vn * (craft.sail_cdA / mass)[:, None]
        else:
            self.vhat = None
        sep_mag = (craft.sep_thrust / mass)[:, None] * self.lit  # solar-powered: off in eclipse
        if sep_ok is not None:
            sep_mag = sep_mag * sep_ok[:, None].to(d.dtype)
        self.sep_mag = sep_mag
        self.gimbal = craft.gimbal
        self.axis_sign = craft.sep_axis

    def evaluate(self, n):
        """n: [B, N, M, 3] candidate normals -> score [B,N,M], accel [B,N,M,3], sep_on [B,N,M]."""
        u = self.u[:, :, None, :]
        f = sail_force_per_area(n, u, self.craft.front, self.craft.back)
        a = self.k_sail[..., None, None] * f
        if self.vhat is not None:
            proj = (n * self.vhat[:, :, None, :]).sum(-1).abs().clamp_min(EDGE_DRAG_FLOOR)
            a = a - (self.k_drag[..., None] * proj)[..., None] * self.vhat[:, :, None, :]
        axis = self.axis_sign.view(-1, 1, 1, 1) * n
        dh = self.dhat[:, :, None, :].expand_as(n)
        sdir = sep_direction(axis, dh, self.gimbal.view(-1, 1, 1).expand(n.shape[:3]))
        gain = (sdir * dh).sum(-1)
        sep_on = (gain > 0.05) & (self.sep_mag[..., None] > 0)
        a = a + torch.where(sep_on, self.sep_mag[..., None], torch.zeros_like(gain))[..., None] * sdir
        score = (a * self.d[:, :, None, :]).sum(-1)
        return score, a, sep_on

    def stowed(self):
        """Retracted sail: no SRP, no sail drag, SEP free to point along d."""
        a = self.sep_mag[..., None] * self.dhat
        score = (a * self.d).sum(-1)
        on = self.sep_mag > 0
        return score, a, on


def choose(ctx: ControlContext, weights=None, k=256, refine=(6.0, 3.0, 1.5)):
    """Pick the best attitude per node (3-axis) or per sample (spin, using node `weights`).

    Returns dict(accel [B,N,3], normal [B,N,3], sep_on [B,N] bool, stowed [B,N] bool, score [B,N]).
    """
    B, N = ctx.d.shape[:2]
    fib = candidates(k)
    cand = fib.view(1, 1, k, 3).expand(B, N, k, 3)
    if ctx.vhat is not None:
        feather = torch.linalg.cross(ctx.u, ctx.vhat)
    else:
        feather = torch.linalg.cross(ctx.u, ctx.dhat)
    fn = feather.norm(dim=-1, keepdim=True)
    alt = torch.linalg.cross(ctx.u, torch.tensor([0.0, 0.0, 1.0], dtype=ctx.u.dtype, device=ctx.u.device).expand_as(ctx.u))
    feather = torch.where(fn > 1e-6, feather / fn.clamp_min(1e-12), _unit(alt))
    cand = torch.cat((cand, feather[:, :, None, :]), 2)
    score, accel, sep_on = ctx.evaluate(cand)

    best = score.argmax(-1)  # [B, N]
    spin = ctx.craft.spin
    if spin.any():
        w = torch.ones(B, N, dtype=score.dtype, device=score.device) if weights is None else weights
        orbit_score = (score[..., :k] * w[..., None]).sum(1)  # [B, k] inertially fixed normal
        best_spin = orbit_score.argmax(-1)
        best = torch.where(spin[:, None], best_spin[:, None].expand(B, N), best)

    idx = best[..., None, None].expand(B, N, 1, 3)
    n_best = cand.gather(2, idx)[:, :, 0]
    s_best = score.gather(2, best[..., None])[..., 0]
    a_best = accel.gather(2, idx)[:, :, 0]
    on_best = sep_on.gather(2, best[..., None])[..., 0]

    # coordinate-ascent refinement for 3-axis craft
    three_axis = ~spin[:, None].expand(B, N)
    for deg in refine:
        h = math.radians(deg)
        e1 = _unit(torch.linalg.cross(n_best, torch.where(n_best[..., 2:3].abs() < 0.9,
                                                          torch.tensor([0.0, 0, 1], dtype=n_best.dtype, device=n_best.device),
                                                          torch.tensor([1.0, 0, 0], dtype=n_best.dtype, device=n_best.device)).expand_as(n_best)))
        e2 = torch.linalg.cross(n_best, e1)
        trial = torch.stack([_unit(n_best + math.tan(h) * s * e) for e in (e1, e2) for s in (1, -1)], 2)
        ts, ta, ton = ctx.evaluate(trial)
        tb = ts.argmax(-1)
        tsb = ts.gather(2, tb[..., None])[..., 0]
        better = (tsb > s_best) & three_axis
        ti = tb[..., None, None].expand(B, N, 1, 3)
        n_best = torch.where(better[..., None], trial.gather(2, ti)[:, :, 0], n_best)
        a_best = torch.where(better[..., None], ta.gather(2, ti)[:, :, 0], a_best)
        on_best = torch.where(better, ton.gather(2, tb[..., None])[..., 0], on_best)
        s_best = torch.where(better, tsb, s_best)

    stowed = torch.zeros(B, N, dtype=torch.bool, device=score.device)
    if ctx.craft.retract.any():
        ss, sa, son = ctx.stowed()
        stowed = (ss > s_best) & ctx.craft.retract[:, None]
        a_best = torch.where(stowed[..., None], sa, a_best)
        on_best = torch.where(stowed, son, on_best)
        s_best = torch.where(stowed, ss, s_best)

    return dict(accel=a_best, normal=n_best, sep_on=on_best, stowed=stowed, score=s_best)
