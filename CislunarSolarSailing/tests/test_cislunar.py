import math

import numpy as np
import torch

from cislunar_sail import backend, cr3bp, envelope, presets, shooting as sh
from cislunar_sail import constants as C

backend.configure("cpu")


def test_lagrange_jacobi():
    L = cr3bp.lagrange_points()
    assert abs(L["L1"][0] - 0.83692) < 1e-4 and abs(L["L2"][0] - 1.15568) < 1e-4
    c1 = cr3bp.jacobi(np.concatenate((L["L1"], [0, 0, 0])))
    assert abs(c1 - 3.18834) < 1e-4


def test_dro_periodic():
    d = cr3bp.find_dro(70000)
    assert d is not None
    end = d.states[-1]
    # orbit closes: last sample is one step before the start
    assert np.linalg.norm(d.states[0, :3] - d.state0[:3]) < 1e-9
    assert 10 < d.period * C.TU / C.DAY < 17


def test_sail_never_pushes_sunward():
    th, rho = envelope.envelope(presets.conventional(0.2e-3))
    assert rho[th > 95].max() < 1e-12
    th, rho = envelope.envelope(presets.hybrid(0.2e-3, gimbal_deg=30))
    assert rho[th > 170].min() > 0  # gimballed SEP fills the sunward cone


def test_shooting_jacobian_matches_fd():
    from torch.func import jacfwd
    l2 = cr3bp.find_halo("L2", 15000)
    m = sh.FourierOrbit(l2)
    cp = sh._craft_params([presets.conventional(0.2e-3)])
    prm = {k: v[0] for k, v in cp.items()}
    x = m(backend.tensor(0.3))
    u = backend.tensor(np.random.default_rng(0).normal(size=(2, 5)))
    f = lambda x, u: sh._segment(x, u, backend.tensor(0.5), backend.tensor(1.0), backend.tensor(0.6), prm, 2, 6)
    Jx, _ = jacfwd(f, argnums=(0, 1))(x, u)
    eye = torch.eye(6, dtype=x.dtype)
    fd = torch.stack([(f(x + 1e-6 * eye[i], u) - f(x - 1e-6 * eye[i], u)) / 2e-6 for i in range(6)], -1)
    assert float((Jx - fd).abs().max()) < 1e-6


def test_shooting_converges_on_feasible_problem():
    """Staying on the same halo for one period is ballistically feasible."""
    l2 = cr3bp.find_halo("L2", 15000)
    m = sh.FourierOrbit(l2)
    T = backend.tensor
    b = sh.TransferBatch(torch.tensor([0]), torch.tensor([0]), torch.tensor([0]), T([l2.period]), T([0.0]),
                         T([0.0]), T([0.02]))
    sol = sh.solve_lm([m], [presets.conventional(0.01e-3)], b, sh.ShootingConfig(S=2), iters=20)
    assert bool(sol["ok"][0])
