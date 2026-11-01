"""Achievable-acceleration envelopes ("force bubbles") and the in-irons region.

For each architecture, sample every admissible control (sail normal over the
full sphere, SEP gimbal direction within its cone, SEP on/off, sail stowed if
retractable) and record the resulting acceleration vector. The envelope radius
rho(theta) is the largest acceleration achievable *exactly* along a direction
at angle theta from the anti-Sun line (axisymmetric about the Sun line).
"""
from __future__ import annotations

import math

import numpy as np
import torch

from . import backend
from . import constants as C
from .spacecraft import Batch, Spacecraft, fibonacci_sphere, sail_force_per_area


def control_samples(sc: Spacecraft, n_normals=6000, n_gimbal=48):
    b = Batch([sc])
    u = backend.tensor([1.0, 0.0, 0.0])  # Sun -> s/c (anti-Sun direction = +x)
    nrm = fibonacci_sphere(n_normals)
    out = []
    a_sail = torch.zeros_like(nrm)
    if sc.sail:
        f = sail_force_per_area(nrm[None], u, b.front, b.back)[0]
        a_sail = C.SOLAR_PRESSURE_1AU * sc.sail.area / sc.mass * f
    out.append(a_sail)
    if sc.sep.enabled:
        a_sep = sc.sep.thrust / sc.mass
        axis = sc.sep.axis_sign * nrm
        g = math.radians(sc.sep.gimbal_max_deg)
        dirs = [axis]
        if g > 0:
            ref = torch.where((axis[:, 2:3]).abs() < 0.9, backend.tensor([0.0, 0, 1]).expand_as(axis), backend.tensor([1.0, 0, 0]).expand_as(axis))
            w1 = torch.linalg.cross(axis, ref); w1 = w1 / w1.norm(dim=-1, keepdim=True)
            w2 = torch.linalg.cross(axis, w1)
            for gi in np.linspace(g / 3, g, 3):
                for ps in np.linspace(0, 2 * math.pi, n_gimbal // 3, endpoint=False):
                    dirs.append(math.cos(gi) * axis + math.sin(gi) * (math.cos(ps) * w1 + math.sin(ps) * w2))
        for d in dirs:
            out.append(a_sail + a_sep * d)
        if sc.sail and sc.sail.retractable:
            out.append(a_sep * fibonacci_sphere(n_normals))
    return torch.cat(out, 0)


def envelope(sc: Spacecraft, bins=181, tol_deg=1.5):
    """rho(theta) for theta in [0,180] deg from the anti-Sun direction."""
    a = control_samples(sc)
    mag = a.norm(dim=-1)
    theta = torch.rad2deg(torch.acos((a[:, 0] / mag.clamp_min(1e-30)).clamp(-1, 1)))
    grid = np.linspace(0, 180, bins)
    rho = np.zeros(bins)
    th, mg = theta.cpu().numpy(), mag.cpu().numpy()
    for i, g in enumerate(grid):
        m = np.abs(th - g) <= tol_deg
        rho[i] = mg[m].max() if m.any() else 0.0
    return grid, rho


def support(sc: Spacecraft, dirs):
    """max_u a(u).d for unit directions d [M,3] (best achievable component, any attitude)."""
    a = control_samples(sc)
    return (dirs @ a.T).max(-1).values
