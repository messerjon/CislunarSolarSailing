"""Presentation-ready figure helpers (PowerPoint 16:9).

Every figure is saved as PNG (200 dpi, 13.33 x 7.5 in = full-bleed 16:9 slide)
and SVG. 3-D trajectories are also exported as interactive Plotly HTML.

Colour follows the validated reference palette: a fixed categorical order
assigned per architecture (never by rank), a single-hue blue ramp for
magnitudes, and a blue/red diverging pair around a neutral grey.
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

OUT = Path(os.environ.get("SAIL_FIG_DIR", "figures"))

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
       "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
CMAP_SEQ = LinearSegmentedColormap.from_list("seq_blue", SEQ)
CMAP_SEQ_R = LinearSegmentedColormap.from_list("seq_blue_r", SEQ[::-1])
CMAP_DIV = LinearSegmentedColormap.from_list("div", ["#0d366b", "#3987e5", "#f0efec", "#e66767", "#a61f1f"])

# Fixed identity colours for architectures and bodies
ARCH_COLOR = {
    "Conventional sail": SERIES[0],
    "Hybrid (gimballed SEP)": SERIES[1],
    "Hybrid (fixed SEP)": SERIES[2],
    "Spin-stabilised sail": SERIES[3],
    "Double-sided sail": SERIES[6],
    "Retractable hybrid": SERIES[4],
    "SEP only": MUTED,
}
EARTH_C, MOON_C, SUN_C = "#2a78d6", "#898781", "#eda100"


def style():
    plt.rcParams.update({
        "figure.figsize": (13.333, 7.5), "figure.dpi": 100, "savefig.dpi": 200,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 17,
        "axes.titlesize": 22, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 38,
        "axes.labelsize": 18, "axes.labelcolor": INK2, "axes.edgecolor": AXIS, "axes.linewidth": 1.0,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 15, "ytick.labelsize": 15,
        "text.color": INK, "legend.frameon": False, "legend.fontsize": 15,
        "lines.linewidth": 2.4, "lines.markersize": 8,
    })


style()


def fig(nrows=1, ncols=1, **kw):
    f, ax = plt.subplots(nrows, ncols, constrained_layout=True, **kw)
    return f, ax


def fig3d():
    f = plt.figure(constrained_layout=True)
    ax = f.add_subplot(111, projection="3d")
    ax.set_facecolor(SURFACE)
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        a.pane.set_facecolor(SURFACE)
        a.pane.set_edgecolor(GRID)
        a._axinfo["grid"]["color"] = GRID
    return f, ax


def subtitle(ax, text):
    ax.annotate(text, xy=(0, 1), xycoords="axes fraction", xytext=(0, 8), textcoords="offset points",
                fontsize=14, color=INK2, va="bottom", ha="left")


def plain_log(ax, axis="both"):
    from matplotlib.ticker import FuncFormatter, LogLocator
    fmt = FuncFormatter(lambda v, _: f"{v:g}")
    for a in ([ax.xaxis, ax.yaxis] if axis == "both" else [getattr(ax, axis + "axis")]):
        if a.get_scale() == "log":
            a.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
            a.set_major_formatter(fmt)
            a.set_minor_formatter(FuncFormatter(lambda v, _: ""))


def save(f, name, sub=""):
    if f._suptitle is not None:  # panel titles sit under a figure title: tighten their padding
        for ax in f.axes:
            if ax.get_title():
                ax.set_title(ax.get_title(), pad=10, fontsize=ax.title.get_fontsize())
    d = OUT / sub if sub else OUT
    d.mkdir(parents=True, exist_ok=True)
    f.savefig(d / f"{name}.png")
    f.savefig(d / f"{name}.svg")
    plt.close(f)
    return d / f"{name}.png"


def set_equal_3d(ax, pts):
    pts = np.asarray(pts)
    c = (pts.max(0) + pts.min(0)) / 2
    r = (pts.max(0) - pts.min(0)).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))


def sphere(ax, center, radius, color, alpha=0.9, n=24):
    u, v = np.mgrid[0:2 * np.pi:n * 1j, 0:np.pi:n // 2 * 1j]
    ax.plot_surface(center[0] + radius * np.cos(u) * np.sin(v), center[1] + radius * np.sin(u) * np.sin(v),
                    center[2] + radius * np.cos(v), color=color, alpha=alpha, linewidth=0, shade=True)


def plotly_html(traces, name, title, sub="", scene=None):
    """Write an interactive 3-D Plotly figure. traces: list of dicts(x,y,z,name,color,width,mode)."""
    import plotly.graph_objects as go
    data = []
    for t in traces:
        if t.get("kind") == "marker":
            data.append(go.Scatter3d(x=t["x"], y=t["y"], z=t["z"], mode="markers+text", name=t["name"],
                                     text=[t["name"]], marker=dict(size=t.get("size", 6), color=t["color"])))
        else:
            data.append(go.Scatter3d(x=t["x"], y=t["y"], z=t["z"], mode="lines", name=t["name"],
                                     line=dict(color=t["color"], width=t.get("width", 4))))
    layout = go.Layout(title=title, paper_bgcolor=SURFACE, font=dict(family="Helvetica Neue, Arial", size=14),
                       scene=scene or dict(aspectmode="data"), legend=dict(itemsizing="constant"))
    d = OUT / sub if sub else OUT
    d.mkdir(parents=True, exist_ok=True)
    go.Figure(data=data, layout=layout).write_html(d / f"{name}.html", include_plotlyjs="cdn")
