import math

import torch

from cislunar_sail import averaged as av
from cislunar_sail import backend, constants as C, control, ephemeris, presets
from cislunar_sail.spacecraft import Batch, sail_force_per_area

backend.configure("cpu")
T = backend.tensor


def test_mee_roundtrip():
    oe = av.mee_from_classical(30000e3, 0.4, math.radians(28.5), 1.1, 0.7)
    p, f, g, h, k = (T([x]) for x in oe)
    L = T([2.3])
    r, v = av.mee_to_rv(p, f, g, h, k, L, C.MU_EARTH)
    back = av.rv_to_mee(r, v, C.MU_EARTH)
    for x, y in zip((p, f, g, h, k, L), back):
        assert torch.allclose(x, y, rtol=1e-9, atol=1e-9)
    # energy check
    a = 30000e3
    eps = 0.5 * (v * v).sum() - C.MU_EARTH / r.norm()
    assert abs(float(eps) + C.MU_EARTH / (2 * a)) / (C.MU_EARTH / (2 * a)) < 1e-10


def test_ideal_sail_force():
    craft = Batch([presets.conventional(0.2e-3)])
    n = T([[[1.0, 0, 0]]])
    u = T([[[1.0, 0, 0]]])
    f = sail_force_per_area(n, u, craft.front, craft.back)
    # optical model normal-incidence coefficient ~1.8 (ideal 2.0)
    assert 1.75 < float(f[0, 0, 0]) < 1.85
    # back-lit single-sided sail is much weaker
    fb = sail_force_per_area(-n, u, craft.front, craft.back)
    assert float(fb[0, 0, 0]) < 0.9 * float(f[0, 0, 0])


def test_moon_inclination_range():
    incs = [ephemeris.moon_inclination_to_equator(ephemeris.jd2000_from_date(2015 + y, 1, 1)) for y in range(0, 19, 3)]
    assert 18.0 < min(incs) < 20.5 and 26.5 < max(incs) < 28.8


def test_j2_nodal_rate():
    """Averaged J2 nodal regression matches the analytic formula."""
    sc = presets.conventional(1e-9)
    craft = Batch([sc])
    a, i = C.R_EARTH + 800e3, math.radians(51.6)
    oe = av.mee_from_classical(a, 0.001, i, 0.3, 0.0)
    state = T([[*oe, sc.mass]])
    envr = av.EarthEnv(atmosphere=None, moon=False, sun_third_body=False)
    model = av.AveragedModel(craft, envr, av.objective_energy(T([C.R_EARTH])), nodes=48)
    rates = model.rates(state, T([0.0]))
    p, f, g, h, k = state[0, :5]
    raan_dot = float((h * rates[0, 4] - k * rates[0, 3]) / (h * h + k * k))
    n = math.sqrt(C.MU_EARTH / a**3)
    expected = -1.5 * n * C.J2_EARTH * (C.R_EARTH / a) ** 2 * math.cos(i)
    assert abs(raan_dot - expected) / abs(expected) < 0.02


def test_sail_raising_rate_bounds():
    """GEO sail energy gain sits between 0 and the tangential-thrust upper bound."""
    sc = presets.conventional(0.2e-3)
    craft = Batch([sc])
    a = 42164e3
    state = T([[*av.mee_from_classical(a, 0.0, 0.01, 0.0, 0.0), sc.mass]])
    envr = av.EarthEnv(atmosphere=None, moon=False, sun_third_body=False)
    model = av.AveragedModel(craft, envr, av.objective_energy(T([C.R_EARTH])))
    rates = model.rates(state, T([0.0]))
    v = math.sqrt(C.MU_EARTH / a)
    upper = 2 * a * a * v * 0.2e-3 / C.MU_EARTH
    dadt = float(rates[0, 0])  # e~0, so dp/dt ~ da/dt
    assert 0.2 * upper < dadt < upper
