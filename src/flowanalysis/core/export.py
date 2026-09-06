from __future__ import annotations

from pathlib import Path

import numpy as np

from .gating import masks, statistics
from .model import Project, Sample, Transform


def export_statistics(project: Project, path, channels=None):
    import pandas as pd

    rows = []
    for sample in project.samples:
        selected = sample.channels if channels is None else [c for c in channels if c in sample.channels]
        rows.extend(statistics(sample, selected))
    table = pd.DataFrame(rows)
    if Path(path).suffix.lower() == ".xlsx":
        table.to_excel(path, index=False)
    else:
        table.to_csv(path, index=False, encoding="utf-8-sig")


def configure_fonts():
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    candidates = ["Arial Unicode MS", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "SimHei"]
    matplotlib.rcParams["font.sans-serif"] = [f for f in candidates if f in available] + ["DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["svg.fonttype"] = "none"
    matplotlib.rcParams["pdf.fonttype"] = 42


def plot_on_axes(ax, sample: Sample, specification: dict):
    population = masks(sample)[specification.get("gate_id", "root")]
    xchannel, ychannel = specification["x"], specification.get("y", "")
    tx = Transform(**specification.get("tx", {}))
    ty = Transform(**specification.get("ty", {}))
    x = tx.apply(sample.column(xchannel)[population])
    mode = specification.get("mode", "density")
    if mode == "histogram":
        ax.hist(x[np.isfinite(x)], bins=128, histtype="step", color="#146f79")
        ax.set_ylabel("Events")
    else:
        y = ty.apply(sample.column(ychannel)[population])
        valid = np.isfinite(x) & np.isfinite(y)
        if mode == "scatter":
            ids = np.flatnonzero(valid)
            if len(ids) > 50000:
                ids = np.random.default_rng(42).choice(ids, 50000, replace=False)
            ax.scatter(x[ids], y[ids], s=.4, alpha=.4, rasterized=True, color="#146f79")
        elif mode == "contour" and valid.sum() > 20:
            from scipy.ndimage import gaussian_filter
            hist, xe, ye = np.histogram2d(x[valid], y[valid], bins=96)
            density = gaussian_filter(hist.T, 1.2)
            if density.max() > 0:
                ax.contour((xe[:-1]+xe[1:])/2, (ye[:-1]+ye[1:])/2, density, levels=7, cmap="viridis")
        elif valid.any():
            ax.hexbin(x[valid], y[valid], gridsize=100, bins="log", mincnt=1, cmap="viridis", rasterized=True)
        ax.set_ylabel(sample.label(ychannel) + f" [{ty.kind}]")
    ax.set_xlabel(sample.label(xchannel) + f" [{tx.kind}]")
    gate_name = next((g.name for g in sample.gates if g.id == specification.get("gate_id")), "All events")
    ax.set_title(specification.get("title") or f"{sample.name}\n{gate_name} · n={int(population.sum()):,}")
    ax.tick_params(labelsize=8)
    for gate in sample.gates:
        if gate.parent != specification.get("gate_id", "root"):
            continue
        if gate.axes != ([xchannel] if mode == "histogram" else [xchannel, ychannel]):
            continue
        transforms = [specification.get("tx", {})] if mode == "histogram" else [specification.get("tx", {}), specification.get("ty", {})]
        if [Transform(**t) for t in gate.transforms] != [Transform(**t) for t in transforms]:
            continue
        from matplotlib.patches import Ellipse, Polygon, Rectangle
        if gate.kind == "polygon":
            ax.add_patch(Polygon(gate.geometry["vertices"], fill=False, edgecolor="#c16b25"))
        elif gate.kind == "rectangle" and all(all(v is not None for v in b) for b in gate.geometry["bounds"]):
            (lo, hi), (bottom, top) = gate.geometry["bounds"]
            ax.add_patch(Rectangle((lo, bottom), hi-lo, top-bottom, fill=False, edgecolor="#c16b25"))
        elif gate.kind == "ellipse":
            rx, ry = gate.geometry["radii"]
            ax.add_patch(Ellipse(gate.geometry["center"], rx*2, ry*2,
                                angle=np.degrees(gate.geometry.get("angle", 0)), fill=False, edgecolor="#c16b25"))
        elif gate.kind == "range":
            for bound in gate.geometry["bounds"][0]:
                if bound is not None:
                    ax.axvline(bound, color="#c16b25")
        elif gate.kind == "quadrant":
            ax.axvline(gate.geometry["thresholds"][0], color="#c16b25")
            ax.axhline(gate.geometry["thresholds"][1], color="#c16b25")


def export_layout(project: Project, specifications: list[dict], path, columns=2, dpi=300):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    if not specifications:
        raise ValueError("Add at least one plot to the layout")
    configure_fonts()
    columns = min(columns, len(specifications))
    rows = (len(specifications) + columns - 1) // columns
    figure = Figure(figsize=(5 * columns, 4.5 * rows), layout="constrained")
    FigureCanvasAgg(figure)
    for index, spec in enumerate(specifications):
        ax = figure.add_subplot(rows, columns, index + 1)
        plot_on_axes(ax, project.sample(spec["sample_id"]), spec)
    figure.savefig(path, dpi=dpi)
    return figure
