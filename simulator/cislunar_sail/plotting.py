"""Shared figure style for report (PDF) and slides (PPTX).

Palette and chart chrome follow the validated reference palette of the
data-visualisation guideline: fixed-order categorical hues, one-hue sequential
ramp, blue/red diverging pair with a grey midpoint, hairline solid grids.
Figures are 16:9 (10 x 5.625 in) so they drop straight into slides and scale
legibly to page width in the report.
"""
from __future__ import annotations

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, ListedColormap

FIG_DIR = os.environ.get("CISLUNAR_FIG_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "figures"))

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = SERIES
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SEQ_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
            "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
DIVERGING = ["#1c5cab", "#3987e5", "#86b6ef", "#cde2fb", "#f0efec", "#f9c9c9", "#ef9a9a", "#e66767", "#c43a3a"]

CMAP_SEQ = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
CMAP_SEQ_R = LinearSegmentedColormap.from_list("seq_blue_r", SEQ_BLUE[::-1])
CMAP_DIV = LinearSegmentedColormap.from_list("div_br", DIVERGING)

FIGSIZE = (10, 5.625)


def _font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Inter", "DejaVu Sans", "Liberation Sans"):
        if cand in names:
            return cand
    return "sans-serif"


def setup():
    plt.rcParams.update({
        "font.family": _font(),
        "font.size": 12,
        "axes.titlesize": 14,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.labelsize": 12,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK2,
        "ytick.labelcolor": INK2,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.frameon": False,
        "legend.fontsize": 11,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.markersize": 7,
        "axes.prop_cycle": matplotlib.cycler(color=SERIES),
        "text.color": INK,
        "figure.dpi": 100,
        "savefig.dpi": 200,
        "mathtext.fontset": "dejavusans",
    })


def fig(nrows=1, ncols=1, size=FIGSIZE, **kw):
    setup()
    return plt.subplots(nrows, ncols, figsize=size, **kw)


def fig3d(size=FIGSIZE):
    setup()
    f = plt.figure(figsize=size)
    ax = f.add_subplot(111, projection="3d")
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        a.pane.set_facecolor(SURFACE)
        a.pane.set_edgecolor(GRID)
        a._axinfo["grid"]["color"] = GRID
        a._axinfo["grid"]["linewidth"] = 0.6
    ax.set_facecolor(SURFACE)
    return f, ax


def title(ax, text, sub=None):
    ax.set_title(text, loc="left", color=INK, pad=22 if sub else 10)
    if sub:
        ax.text(0.0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=11, va="bottom")


def save(f, name, tight=True):
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    if tight:
        f.savefig(path, bbox_inches="tight", pad_inches=0.15)
    else:
        f.savefig(path)
    plt.close(f)
    return path


def label_end(ax, x, y, text, color=INK2, dx=4, dy=0, ha="left", fontsize=10.5):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=color,
                fontsize=fontsize, va="center", ha=ha)


def set_equal_3d(ax, X, Y, Z):
    import numpy as np
    xr = np.ptp(X); yr = np.ptp(Y); zr = np.ptp(Z)
    r = max(xr, yr, zr) / 2
    xm, ym, zm = (np.max(X) + np.min(X)) / 2, (np.max(Y) + np.min(Y)) / 2, (np.max(Z) + np.min(Z)) / 2
    ax.set_xlim(xm - r, xm + r); ax.set_ylim(ym - r, ym + r); ax.set_zlim(zm - r, zm + r)
    try:
        ax.set_box_aspect((1, 1, 1))
    except Exception:
        pass
