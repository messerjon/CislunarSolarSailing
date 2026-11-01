"""Torch device / dtype selection.

Orbit propagation needs float64: a float32 position at lunar distance has ~25 m
resolution and long spirals accumulate error. CUDA and CPU support float64;
Apple MPS does not, so MPS runs in float32 and is only suitable for quick
exploratory sweeps.
"""
import os
import warnings

import torch

_DEVICE = None
_DTYPE = None


def configure(device: str | None = None):
    """Pick the compute device. `device` in {None/'auto','cpu','cuda','mps'}."""
    global _DEVICE, _DTYPE
    device = device or os.environ.get("SAIL_DEVICE", "auto")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "mps":
        warnings.warn("MPS has no float64; running in float32 (reduced accuracy).")
        _DTYPE = torch.float32
    else:
        _DTYPE = torch.float64
    _DEVICE = torch.device(device)
    return _DEVICE, _DTYPE


def device():
    if _DEVICE is None:
        configure()
    return _DEVICE


def dtype():
    if _DTYPE is None:
        configure()
    return _DTYPE


def tensor(x):
    return torch.as_tensor(x, dtype=dtype(), device=device())
