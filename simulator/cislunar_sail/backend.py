"""Array backend abstraction: NumPy (default) or PyTorch (CPU or CUDA GPU).

All batched propagators and steering laws are written against the small API
below so that the same code runs vectorised on a CPU with NumPy or on GPUs
with PyTorch. Select with ``get_backend('torch')`` or the environment variable
``CISLUNAR_BACKEND=torch``. With torch the device defaults to CUDA when present.
"""
from __future__ import annotations

import os
import numpy as np


class NumpyBackend:
    name = "numpy"

    def __init__(self, dtype=np.float64):
        self.dtype = dtype
        self.device = "cpu"

    # creation / conversion
    def asarray(self, x):
        return np.asarray(x, dtype=self.dtype)

    def to_numpy(self, x):
        return np.asarray(x)

    def zeros(self, shape):
        return np.zeros(shape, dtype=self.dtype)

    def ones(self, shape):
        return np.ones(shape, dtype=self.dtype)

    def full(self, shape, val):
        return np.full(shape, val, dtype=self.dtype)

    def linspace(self, a, b, n):
        return np.linspace(a, b, n, dtype=self.dtype)

    def arange(self, n):
        return np.arange(n)

    def bool_ones(self, n):
        return np.ones(n, dtype=bool)

    # elementwise
    sqrt = staticmethod(np.sqrt)
    sin = staticmethod(np.sin)
    cos = staticmethod(np.cos)
    tan = staticmethod(np.tan)
    exp = staticmethod(np.exp)
    log = staticmethod(np.log)
    abs = staticmethod(np.abs)
    arctan2 = staticmethod(np.arctan2)
    floor = staticmethod(np.floor)
    sign = staticmethod(np.sign)

    def arccos(self, x):
        return np.arccos(np.clip(x, -1.0, 1.0))

    def where(self, c, a, b):
        return np.where(c, a, b)

    def clip(self, x, lo, hi):
        return np.clip(x, lo, hi)

    def maximum(self, a, b):
        return np.maximum(a, b)

    def minimum(self, a, b):
        return np.minimum(a, b)

    # reductions / shape
    def sum(self, x, axis=-1, keepdims=False):
        return np.sum(x, axis=axis, keepdims=keepdims)

    def norm(self, x, axis=-1, keepdims=False):
        return np.sqrt(np.sum(x * x, axis=axis, keepdims=keepdims))

    def dot(self, a, b, keepdims=False):
        return np.sum(a * b, axis=-1, keepdims=keepdims)

    def cross(self, a, b):
        return np.cross(a, b)

    def stack(self, xs, axis=-1):
        return np.stack(xs, axis=axis)

    def concat(self, xs, axis=-1):
        return np.concatenate(xs, axis=axis)

    def argmax(self, x, axis=-1):
        return np.argmax(x, axis=axis)

    def argmin(self, x, axis=-1):
        return np.argmin(x, axis=axis)

    def take_along(self, x, idx, axis=-1):
        return np.take_along_axis(x, idx, axis=axis)

    def any(self, x):
        return bool(np.any(x))

    def copy(self, x):
        return np.array(x, copy=True)

    def interp_uniform(self, x, x0, dx, table):
        """Linear interpolation in a uniformly spaced 1-D table (vectorised)."""
        u = np.clip((x - x0) / dx, 0.0, len(table) - 1.000001)
        i0 = np.floor(u).astype(np.int64)
        w = u - i0
        return table[i0] * (1 - w) + table[i0 + 1] * w


class TorchBackend(NumpyBackend):
    name = "torch"

    def __init__(self, device=None, dtype=None):
        import torch
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = dtype or torch.float64

    def asarray(self, x):
        t = self.torch
        if isinstance(x, t.Tensor):
            return x.to(device=self.device, dtype=self.dtype)
        return t.as_tensor(np.asarray(x, dtype=np.float64), dtype=self.dtype, device=self.device)

    def to_numpy(self, x):
        if isinstance(x, self.torch.Tensor):
            return x.detach().cpu().numpy()
        return np.asarray(x)

    def zeros(self, shape):
        return self.torch.zeros(shape, dtype=self.dtype, device=self.device)

    def ones(self, shape):
        return self.torch.ones(shape, dtype=self.dtype, device=self.device)

    def full(self, shape, val):
        return self.torch.full(shape if isinstance(shape, tuple) else (shape,), float(val),
                               dtype=self.dtype, device=self.device)

    def linspace(self, a, b, n):
        return self.torch.linspace(a, b, n, dtype=self.dtype, device=self.device)

    def arange(self, n):
        return self.torch.arange(n, device=self.device)

    def bool_ones(self, n):
        return self.torch.ones(n, dtype=self.torch.bool, device=self.device)

    def _w(name):
        def f(self, *a):
            return getattr(self.torch, name)(*a)
        return f

    sqrt = _w("sqrt"); sin = _w("sin"); cos = _w("cos"); tan = _w("tan")
    exp = _w("exp"); log = _w("log"); abs = _w("abs"); arctan2 = _w("atan2")
    floor = _w("floor"); sign = _w("sign")

    def arccos(self, x):
        return self.torch.arccos(self.torch.clamp(x, -1.0, 1.0))

    def where(self, c, a, b):
        t = self.torch
        a = a if isinstance(a, t.Tensor) else t.as_tensor(a, dtype=self.dtype, device=self.device)
        b = b if isinstance(b, t.Tensor) else t.as_tensor(b, dtype=self.dtype, device=self.device)
        return t.where(c, a, b)

    def clip(self, x, lo, hi):
        return self.torch.clamp(x, lo, hi)

    def maximum(self, a, b):
        t = self.torch
        if not isinstance(b, t.Tensor):
            return t.clamp(a, min=b)
        return t.maximum(a, b)

    def minimum(self, a, b):
        t = self.torch
        if not isinstance(b, t.Tensor):
            return t.clamp(a, max=b)
        return t.minimum(a, b)

    def sum(self, x, axis=-1, keepdims=False):
        return self.torch.sum(x, dim=axis, keepdim=keepdims)

    def norm(self, x, axis=-1, keepdims=False):
        return self.torch.sqrt(self.torch.sum(x * x, dim=axis, keepdim=keepdims))

    def dot(self, a, b, keepdims=False):
        return self.torch.sum(a * b, dim=-1, keepdim=keepdims)

    def cross(self, a, b):
        return self.torch.linalg.cross(a, b, dim=-1)

    def stack(self, xs, axis=-1):
        return self.torch.stack(xs, dim=axis)

    def concat(self, xs, axis=-1):
        return self.torch.cat(xs, dim=axis)

    def argmax(self, x, axis=-1):
        return self.torch.argmax(x, dim=axis)

    def argmin(self, x, axis=-1):
        return self.torch.argmin(x, dim=axis)

    def take_along(self, x, idx, axis=-1):
        return self.torch.take_along_dim(x, idx, dim=axis)

    def any(self, x):
        return bool(self.torch.any(x))

    def copy(self, x):
        return x.clone()

    def interp_uniform(self, x, x0, dx, table):
        t = self.torch
        table = table if isinstance(table, t.Tensor) else self.asarray(table)
        u = t.clamp((x - x0) / dx, 0.0, table.shape[0] - 1.000001)
        i0 = t.floor(u).long()
        w = u - i0
        return table[i0] * (1 - w) + table[i0 + 1] * w


_DEFAULT = None


def get_backend(name: str | None = None):
    """Return a backend instance. ``name`` in {'numpy', 'torch'}."""
    global _DEFAULT
    name = (name or os.environ.get("CISLUNAR_BACKEND", "numpy")).lower()
    if name == "torch":
        try:
            return TorchBackend()
        except ImportError:  # pragma: no cover - torch optional
            return NumpyBackend()
    if _DEFAULT is None:
        _DEFAULT = NumpyBackend()
    return _DEFAULT
