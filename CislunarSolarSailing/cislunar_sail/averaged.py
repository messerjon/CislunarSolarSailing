"""Orbit-averaged low-thrust propagation in modified equinoctial elements (MEE).

Long sail spirals (thousands of revolutions from LEO) are impractical to
integrate step-by-step for large trade sweeps. Instead the Gauss variational
equations are averaged numerically over one revolution: N quadrature nodes
equally spaced in eccentric anomaly, each with its own position, Sun/Moon
geometry, eclipse state, drag and locally-optimal attitude. The slow elements
(p, f, g, h, k) and mass are then integrated with steps of hours to days.

Every operation is batched over B independent spacecraft/scenarios so a whole
trade study is one tensor program (GPU-friendly).

MEE (Walker 1985):  p = a(1-e^2), f = e cos(w+O), g = e sin(w+O),
h = tan(i/2) cos O, k = tan(i/2) sin O, L = O + w + nu.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import torch
import torch.nn.functional as F

from . import backend
from . import constants as C
from . import control, environment as env, ephemeris
from .spacecraft import Batch


# ---------------------------------------------------------------------------
# Element conversions
# ---------------------------------------------------------------------------
def mee_to_rv(p, f, g, h, k, L, mu):
    cl, sl = torch.cos(L), torch.sin(L)
    a2 = h * h - k * k
    s2 = 1 + h * h + k * k
    w = 1 + f * cl + g * sl
    r = p / w
    sqmp = torch.sqrt(mu / p)
    rv = torch.stack(((r / s2) * (cl + a2 * cl + 2 * h * k * sl),
                      (r / s2) * (sl - a2 * sl + 2 * h * k * cl),
                      (2 * r / s2) * (h * sl - k * cl)), -1)
    vv = torch.stack((-(sqmp / s2) * (sl + a2 * sl - 2 * h * k * cl + g - 2 * f * h * k + a2 * g),
                      -(sqmp / s2) * (-cl + a2 * cl + 2 * h * k * sl - f + 2 * g * h * k + a2 * f),
                      (2 * sqmp / s2) * (h * cl + k * sl + f * h + g * k)), -1)
    return rv, vv


def rv_to_mee(r, v, mu):
    rn = r.norm(dim=-1)
    hv = torch.linalg.cross(r, v)
    hn = hv.norm(dim=-1)
    p = hn * hn / mu
    hx, hy, hz = hv.unbind(-1)
    denom = hn + hz
    h = -hy / denom
    k = hx / denom
    # equinoctial frame
    s2 = 1 + h * h + k * k
    fx = torch.stack((1 - k * k + h * h, 2 * h * k, -2 * k), -1) / s2[..., None]
    gx = torch.stack((2 * h * k, 1 + k * k - h * h, 2 * h), -1) / s2[..., None]
    ecc = torch.linalg.cross(v, hv) / mu - r / rn[..., None]
    f = (ecc * fx).sum(-1)
    g = (ecc * gx).sum(-1)
    L = torch.atan2((r * gx).sum(-1), (r * fx).sum(-1))
    return p, f, g, h, k, L


def classical(p, f, g, h, k):
    e = torch.sqrt(f * f + g * g)
    a = p / (1 - e * e)
    inc = 2 * torch.atan(torch.sqrt(h * h + k * k))
    return a, e, inc


def mee_from_classical(a, e, inc, raan, argp):
    p = a * (1 - e * e)
    return (p, e * math.cos(argp + raan), e * math.sin(argp + raan),
            math.tan(inc / 2) * math.cos(raan), math.tan(inc / 2) * math.sin(raan))


def gauss_matrix(p, f, g, h, k, L, mu):
    """d(p,f,g,h,k)/dt = G @ [a_r, a_t, a_n].  Returns [..., 5, 3]."""
    cl, sl = torch.cos(L), torch.sin(L)
    w = 1 + f * cl + g * sl
    s2 = 1 + h * h + k * k
    q = torch.sqrt(p / mu)
    z = torch.zeros_like(w)
    hk = h * sl - k * cl
    rows = [
        torch.stack((z, 2 * p / w * q, z), -1),
        torch.stack((q * sl, q * ((w + 1) * cl + f) / w, -q * hk * g / w), -1),
        torch.stack((-q * cl, q * ((w + 1) * sl + g) / w, q * hk * f / w), -1),
        torch.stack((z, z, q * s2 * cl / (2 * w)), -1),
        torch.stack((z, z, q * s2 * sl / (2 * w)), -1),
    ]
    return torch.stack(rows, -2)


# ---------------------------------------------------------------------------
# Central-body environments
# ---------------------------------------------------------------------------
@dataclass
class EarthEnv:
    epoch_jd2000: float = 9800.0
    atmosphere: str | None = "moderate"
    moon: bool = True
    sun_third_body: bool = True
    mu: float = C.MU_EARTH
    radius: float = C.R_EARTH
    j2: float = C.J2_EARTH
    min_perigee_alt: float = 150e3

    def sun_unit(self, t):
        return ephemeris.sun_unit(t, self.epoch_jd2000)

    def perturbers(self, t):
        out = []
        if self.moon:
            out.append((C.MU_MOON, ephemeris.moon_position(t, self.epoch_jd2000)))
        if self.sun_third_body:
            out.append((C.MU_SUN, ephemeris.sun_position(t, self.epoch_jd2000)))
        return out

    def shadow_bodies(self, t):
        bodies = [(torch.zeros(3, dtype=t.dtype, device=t.device), self.radius)]
        if self.moon:
            bodies.append((ephemeris.moon_position(t, self.epoch_jd2000), C.R_MOON))
        return bodies

    def atmosphere_velocity(self, r):
        w = torch.tensor([0.0, 0.0, C.OMEGA_EARTH], dtype=r.dtype, device=r.device)
        return torch.linalg.cross(w.expand_as(r), r)


@dataclass
class MoonEnv:
    """Moon-centred inertial frame aligned with the lunar orbit plane (z = orbit normal).
    The lunar equator is within 6.7 deg of this plane; 'polar' targets refer to this frame."""
    sun_phase0: float = 0.0
    earth_phase0: float = math.pi
    atmosphere: str | None = None
    mu: float = C.MU_MOON
    radius: float = C.R_MOON
    j2: float = C.J2_MOON
    min_perigee_alt: float = 15e3

    def sun_unit(self, t):
        lam = self.sun_phase0 + C.N_SUN * t
        return torch.stack((torch.cos(lam), torch.sin(lam), torch.zeros_like(lam)), -1)

    def earth_position(self, t):
        th = self.earth_phase0 + C.N_MOON * t
        return C.D_EARTH_MOON * torch.stack((torch.cos(th), torch.sin(th), torch.zeros_like(th)), -1)

    def perturbers(self, t):
        return [(C.MU_EARTH, self.earth_position(t)), (C.MU_SUN, C.AU * self.sun_unit(t))]

    def shadow_bodies(self, t):
        return [(torch.zeros(3, dtype=t.dtype, device=t.device), self.radius), (self.earth_position(t), C.R_EARTH)]


# ---------------------------------------------------------------------------
# Guidance objectives  J(p,f,g,h,k) -> [B]  (to be maximised)
# ---------------------------------------------------------------------------
def objective_energy(rp_min):
    """Raise orbital energy (semi-major axis) while guarding perigee >= rp_min [B]."""
    def J(oe, idx=None):
        rpm = _sel(rp_min, idx)
        p, f, g, h, k = oe.unbind(-1)
        e = torch.sqrt(f * f + g * g + 1e-14)
        a = p / (1 - e * e)
        rp = p / (1 + e)
        # perigee guard: a 10 km dip below rp_min must outweigh the energy gradient, otherwise
        # energy-greedy steering pumps eccentricity and drags perigee into the atmosphere
        guard = F.relu((rpm - rp) / rpm * 200.0) ** 2
        return torch.log(a) - guard
    return J


def objective_target(a_t, e_t, i_t, w_a=1.0, w_e=1.0, w_i=1.0, rp_min=None, a_metric="l2"):
    """Lyapunov-type element targeting: maximise -[w_a ln(a/a*)^2 + w_e (e-e*)^2 + w_i (i-i*)^2]."""
    def J(oe, idx=None):
        at, et, it = _sel(a_t, idx), _sel(e_t, idx), _sel(i_t, idx)
        wa, we, wi = _sel(w_a, idx), _sel(w_e, idx), _sel(w_i, idx)
        p, f, g, h, k = oe.unbind(-1)
        e = torch.sqrt(f * f + g * g + 1e-14)
        a = p / (1 - e * e)
        inc = 2 * torch.atan(torch.sqrt(h * h + k * k + 1e-14))
        la = torch.log(a / at)
        a_term = la**2 if a_metric == "l2" else torch.sqrt(la**2 + 1e-8)  # l1: bounded gradient far from target
        val = wa * a_term + we * (e - et) ** 2 + wi * (inc - it) ** 2
        if rp_min is not None:
            rpm = _sel(rp_min, idx)
            rp = p / (1 + e)
            val = val + F.relu((rpm - rp) / rpm * 20.0) ** 2
        return -val
    return J


def _sel(x, idx):
    return x[idx] if (idx is not None and torch.is_tensor(x) and x.dim() > 0) else x


def _grad_J(J, oe, idx=None):
    with torch.enable_grad():
        x = oe.detach().clone().requires_grad_(True)
        (gr,) = torch.autograd.grad(J(x, idx).sum(), x)
    return gr


# ---------------------------------------------------------------------------
# Averaged rates
# ---------------------------------------------------------------------------
@dataclass
class AveragedModel:
    craft: Batch
    env: object
    objective: Callable
    nodes: int = 36
    k_candidates: int = 192

    def __post_init__(self):
        E = (torch.arange(self.nodes, dtype=backend.dtype(), device=backend.device()) + 0.5) * (2 * math.pi / self.nodes)
        self.E = E

    def rates(self, state, t, diagnostics=False, idx=None):
        craft = self.craft if idx is None else self.craft.subset(idx)
        B = state.shape[0]
        p, f, g, h, k, m = state.unbind(-1)
        mu = self.env.mu
        e = torch.sqrt(f * f + g * g).clamp_max(0.999)
        a = p / (1 - e * e)
        n_mean = torch.sqrt(mu / a**3)
        varpi = torch.atan2(g, f)
        E = self.E[None, :]
        ee = e[:, None]
        nu = 2 * torch.atan2(torch.sqrt(1 + ee) * torch.sin(E / 2), torch.sqrt(1 - ee) * torch.cos(E / 2))
        L = varpi[:, None] + nu
        M = E - ee * torch.sin(E)
        tj = t[:, None] + M / n_mean[:, None]
        w = (1 - ee * torch.cos(E)) / self.nodes  # time weights, sum to 1

        P = [x[:, None].expand(B, self.nodes) for x in (p, f, g, h, k)]
        r, v = mee_to_rv(*P, L, mu)
        rn = r.norm(dim=-1, keepdim=True)
        rhat = r / rn
        hvec = torch.linalg.cross(r, v)
        nhat = hvec / hvec.norm(dim=-1, keepdim=True)
        that = torch.linalg.cross(nhat, rhat)

        # natural accelerations
        a_nat = env.j2_accel(r, mu, self.env.radius, self.env.j2)
        for mu_b, rb in self.env.perturbers(tj):
            a_nat = a_nat + env.third_body_accel(r, rb, mu_b)
        sun = self.env.sun_unit(tj)
        lit = torch.ones(B, self.nodes, dtype=torch.bool, device=r.device)
        for rb, rad in self.env.shadow_bodies(tj):
            lit = lit & env.cylindrical_shadow(r, rb, rad, sun)

        rho = v_rel = None
        if getattr(self.env, "atmosphere", None):
            alt = rn[..., 0] - self.env.radius
            rho = env.atmosphere_density(alt, self.env.atmosphere)
            v_rel = v - self.env.atmosphere_velocity(r)
            vrn = v_rel.norm(dim=-1, keepdim=True)
            a_nat = a_nat - (0.5 * rho[..., None] * vrn * v_rel) * (craft.bus_cdA / m)[:, None, None]

        # guidance direction
        G = gauss_matrix(*P, L, mu)  # [B,N,5,3]
        c = _grad_J(self.objective, state[:, :5], idx)  # [B,5]
        d_rtn = torch.einsum("bnij,bi->bnj", G, c)
        d = d_rtn[..., 0:1] * rhat + d_rtn[..., 1:2] * that + d_rtn[..., 2:3] * nhat

        sep_ok = (m - craft.dry_mass) > 1e-3
        ctx = control.ControlContext(craft, m, d, -sun, lit, rho=rho, v_rel=v_rel, sep_ok=sep_ok)
        ch = control.choose(ctx, weights=w, k=self.k_candidates)
        a_tot = a_nat + ch["accel"]
        a_rtn = torch.stack(((a_tot * rhat).sum(-1), (a_tot * that).sum(-1), (a_tot * nhat).sum(-1)), -1)
        doe = torch.einsum("bnij,bnj->bni", G, a_rtn)
        doe = (doe * w[..., None]).sum(1)
        sep_duty = (ch["sep_on"].to(w.dtype) * w).sum(1)
        dm = -sep_duty * craft.sep_mdot
        rates = torch.cat((doe, dm[:, None]), -1)
        if not diagnostics:
            return rates
        ctrl_rtn = torch.stack(((ch["accel"] * rhat).sum(-1), (ch["accel"] * that).sum(-1), (ch["accel"] * nhat).sum(-1)), -1)
        cone = torch.rad2deg(torch.acos((ch["normal"] * -sun).sum(-1).abs().clamp(max=1)))
        diag = dict(
            eclipse_frac=((~lit).to(w.dtype) * w).sum(1),
            sep_duty=sep_duty,
            stowed_frac=(ch["stowed"].to(w.dtype) * w).sum(1),
            mean_ctrl_t=(ctrl_rtn[..., 1] * w).sum(1),
            mean_ctrl_mag=(ch["accel"].norm(dim=-1) * w).sum(1),
            mean_cone_deg=(cone * w * lit).sum(1) / (w * lit).sum(1).clamp_min(1e-9),
        )
        return rates, diag


# ---------------------------------------------------------------------------
# Integrator
# ---------------------------------------------------------------------------
@dataclass
class Result:
    t: torch.Tensor            # [B] final time (s) or time at completion
    state: torch.Tensor        # [B, 6]
    done: torch.Tensor         # [B] reached target
    failed: torch.Tensor       # [B] decayed / impacted / out of propellant with no sail
    history: dict = field(default_factory=dict)  # lists of [B] tensors per recorded step
    stalled: torch.Tensor | None = None


def propagate(model: AveragedModel, state0, done_fn, t_max, dt_max=1.5 * C.DAY, dt_min=600.0,
              frac=0.03, record_every=1, progress=False, stall_window=365 * C.DAY, stall_gain=0.01):
    """Midpoint-rule integration of the averaged equations with per-sample adaptive steps."""
    state = state0.clone()
    B = state.shape[0]
    t = torch.zeros(B, dtype=state.dtype, device=state.device)
    done = torch.zeros(B, dtype=torch.bool, device=state.device)
    failed = torch.zeros_like(done)
    t_done = torch.full_like(t, float("nan"))
    hist = {k: [] for k in ("t", "a", "e", "i", "rp", "ra", "m", "eclipse_frac", "sep_duty",
                            "stowed_frac", "mean_ctrl_t", "mean_cone_deg", "state")}
    step = 0
    diag = {k: torch.zeros(B, dtype=state.dtype, device=state.device)
            for k in ("eclipse_frac", "sep_duty", "stowed_frac", "mean_ctrl_t", "mean_ctrl_mag", "mean_cone_deg")}
    a_ref = classical(*state[:, :5].unbind(-1))[0]
    t_ref = torch.zeros_like(t)
    stalled = torch.zeros_like(done)
    with torch.no_grad():
        while True:
            active = ~(done | failed) & (t < t_max)
            if not active.any():
                break
            idx = active.nonzero().squeeze(1)
            st, tt = state[idx], t[idx]
            k1, dg = model.rates(st, tt, diagnostics=True, idx=idx)
            for key, val in dg.items():
                diag[key][idx] = val
            p = st[:, 0]
            lim = torch.stack((frac * p / k1[:, 0].abs().clamp_min(1e-30),
                               frac / k1[:, 1].abs().clamp_min(1e-30),
                               frac / k1[:, 2].abs().clamp_min(1e-30),
                               frac / k1[:, 3].abs().clamp_min(1e-30),
                               frac / k1[:, 4].abs().clamp_min(1e-30)), -1).min(-1).values
            dt = lim.clamp(dt_min, dt_max)
            dt = torch.minimum(dt, (t_max - tt).clamp_min(0))
            mid = st + 0.5 * dt[:, None] * k1
            k2 = model.rates(mid, tt + 0.5 * dt, idx=idx)
            state[idx] = st + dt[:, None] * k2
            t[idx] = tt + dt

            a, e, inc = classical(*state[:, :5].unbind(-1))
            rp = state[:, 0] / (1 + e)
            ra = state[:, 0] / (1 - e).clamp_min(1e-9)
            newly = done_fn(state, t) & active
            t_done = torch.where(newly, t, t_done)
            done = done | newly
            check = active & ~done & (t - t_ref > stall_window)
            stall_now = check & ((a - a_ref).abs() < stall_gain * a_ref)  # no progress either way
            stalled = stalled | stall_now
            a_ref = torch.where(check, a, a_ref)
            t_ref = torch.where(check, t, t_ref)
            failed = failed | stall_now | ((rp < model.env.radius + model.env.min_perigee_alt) & active & ~done) | (e >= 0.99) & active
            if step % record_every == 0:
                for key, val in (("t", t), ("a", a), ("e", e), ("i", inc), ("rp", rp), ("ra", ra), ("m", state[:, 5]),
                                 ("state", state)):
                    hist[key].append(val.clone())
                for key in ("eclipse_frac", "sep_duty", "stowed_frac", "mean_ctrl_t", "mean_cone_deg"):
                    hist[key].append(diag[key].clone())
            if progress and step % 200 == 0:
                print(f"  step {step}: t_max={float(t.max())/C.DAY:7.1f} d  done={int(done.sum())}/{B} failed={int(failed.sum())}")
            step += 1
    hist = {k: torch.stack(v, 0).cpu() for k, v in hist.items()}
    return Result(t=torch.where(done, t_done, t), state=state, done=done, failed=failed, history=hist,
                  stalled=stalled)
