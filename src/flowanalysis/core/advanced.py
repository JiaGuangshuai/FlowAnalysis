from __future__ import annotations

from dataclasses import asdict

import numpy as np
from scipy.optimize import minimize
from scipy.special import ndtr, softmax

from .model import Transform


def feature_matrix(events, indices, transform: Transform, standardize=False):
    values = transform.apply(np.asarray(events, dtype=float)[:, indices])
    if not np.isfinite(values).all():
        raise ValueError("Selected features contain non-finite values after transformation")
    if len(values) < 10 or values.shape[1] < 2:
        raise ValueError("Select at least two channels and ten events")
    spread = np.std(values, axis=0)
    if np.any(spread < 1e-12):
        raise ValueError("Remove constant channels from the feature selection")
    if standardize:
        values = (values - values.mean(axis=0)) / spread
    return values


def embedding(events, indices, method="UMAP", seed=42, limit=30000, neighbors=15,
              min_dist=0.1, perplexity=30.0, iterations=1000, transform=None, standardize=False):
    transform = transform or Transform("arcsinh")
    values = feature_matrix(events, indices, transform, standardize)
    rng = np.random.default_rng(seed)
    selected = np.sort(rng.choice(len(values), min(len(values), limit), replace=False))
    values = values[selected]
    if len(values) < 10:
        raise ValueError("At least ten events are required")
    if method == "UMAP":
        from umap import UMAP

        if not 2 <= neighbors < len(values) or not 0 <= min_dist <= 1:
            raise ValueError("UMAP neighbors must be >=2 and < event count; min_dist must be in [0,1]")
        coords = UMAP(n_components=2, n_neighbors=neighbors, min_dist=min_dist,
                      random_state=seed, n_jobs=1).fit_transform(values)
        extra = {"neighbors": neighbors, "min_dist": min_dist}
    elif method == "t-SNE":
        from sklearn.manifold import TSNE

        if not 0 < perplexity < len(values) or iterations < 250:
            raise ValueError("t-SNE requires perplexity < event count and iterations >=250")
        model = TSNE(n_components=2, perplexity=perplexity, max_iter=iterations,
                     random_state=seed, init="pca", learning_rate="auto")
        coords = model.fit_transform(values)
        extra = {"perplexity": perplexity, "iterations": iterations,
                 "kl_divergence": float(model.kl_divergence_)}
    else:
        raise ValueError("Unknown dimension reduction method")
    return {"method": method, "coordinates": coords, "event_indices": selected,
            "parameters": {"seed": seed, "limit": limit, "transform": asdict(transform),
                           "standardize": standardize, "columns": indices, **extra}}


def flowsom_cluster(events, indices, n_clusters=8, grid=8, seed=42, transform=None,
                    standardize=False, train_limit=50000):
    from anndata import AnnData
    from flowsom import FlowSOM

    transform = transform or Transform("arcsinh")
    values = feature_matrix(events, indices, transform, standardize)
    if not 2 <= n_clusters <= grid * grid or not 2 <= grid <= 30:
        raise ValueError("Metaclusters must be between 2 and grid²; grid must be 2–30")
    rng = np.random.default_rng(seed)
    train_ids = np.sort(rng.choice(len(values), min(len(values), train_limit), replace=False))
    if len(train_ids) < grid * grid:
        raise ValueError("Training population must contain at least grid² events")
    model = FlowSOM(AnnData(values[train_ids]), n_clusters=n_clusters, xdim=grid, ydim=grid, seed=seed)
    mapped = model if len(train_ids) == len(values) else model.new_data(AnnData(values))
    labels = np.asarray(mapped.metacluster_labels, dtype=int)
    clusters = np.asarray(mapped.cluster_labels, dtype=int)
    unique = np.unique(labels)
    medians = np.vstack([np.median(values[labels == label], axis=0) for label in unique])
    return {"method": "FlowSOM", "labels": labels, "som_nodes": clusters,
            "metaclusters": unique, "medians": medians,
            "counts": np.array([(labels == label).sum() for label in unique]),
            "parameters": {"seed": seed, "grid": grid, "n_clusters": n_clusters,
                           "train_limit": train_limit, "training_indices": train_ids.tolist(),
                           "transform": asdict(transform), "standardize": standardize, "columns": indices}}


def _fit_histogram(values, bins):
    x = np.asarray(values, float)
    finite = x[np.isfinite(x)]
    if len(finite) < 200 or np.ptp(finite) == 0:
        raise ValueError("Model fitting requires at least 200 finite nonconstant events")
    counts, edges = np.histogram(finite, bins=bins)
    return counts, edges, (edges[:-1] + edges[1:]) / 2


def cell_cycle(values, g1_peak: float, cv=0.06, bins=180, low=None, high=None):
    """Explicit exploratory DNA model: G1/G2 Gaussians + Gaussian-broadened uniform S.

    This is an independent model, not Watson Pragmatic or Dean–Jett–Fox.
    Fit linear DNA signal from singlets; sub-G1/debris/polyploid components are absent.
    """
    original = np.asarray(values, float)
    if g1_peak <= 0 or not 0.01 <= cv <= 0.2:
        raise ValueError("Specify a positive G1 peak and CV in [0.01, 0.2]")
    low = 0.5 * g1_peak if low is None else float(low)
    high = 2.6 * g1_peak if high is None else float(high)
    if not 0 <= low < g1_peak < 2 * g1_peak < high:
        raise ValueError("Fit interval must include positive G1 and G2 peaks")
    filtered = original[np.isfinite(original) & (original >= low) & (original <= high)]
    counts, edges, centers = _fit_histogram(filtered, np.linspace(low, high, bins + 1))
    n = counts.sum()
    from scipy.special import ndtr as cdf

    def distribution(parameters):
        # Optimize a dimensionless peak ratio: raw intensity (often 1e5) and
        # fractional CV have incompatible scales for finite-difference gradients.
        mu, width = parameters[0] * g1_peak, parameters[1]
        sigma = mu * width
        g1 = np.diff(cdf((edges - mu) / sigma))
        g2 = np.diff(cdf((edges - 2 * mu) / (sigma * np.sqrt(2))))
        # Integral of convolution(uniform(mu,2mu), normal(0,sigma)).
        def h(z):
            return z * cdf(z) + np.exp(-z**2 / 2) / np.sqrt(2 * np.pi)
        scdf = sigma / mu * (h((edges - mu) / sigma) - h((edges - 2 * mu) / sigma))
        sphase = np.maximum(np.diff(scdf), 0)
        components = np.column_stack([g1, sphase, g2])
        components /= components.sum(axis=0)
        weights = softmax([parameters[2], parameters[3], 0])
        return components * weights * n

    def objective(p):
        expected = np.maximum(distribution(p).sum(axis=1), 1e-12)
        return float(np.sum(expected - counts * np.log(expected)))

    fit = minimize(objective, [1.0, cv, 1.0, 0.0], method="L-BFGS-B",
                   bounds=[(.85, 1.15), (.01, .20), (-12, 12), (-12, 12)])
    if not fit.success or not np.isfinite(fit.fun):
        raise ValueError(f"Cell-cycle fit did not converge: {fit.message}")
    components = distribution(fit.x)
    expected = components.sum(axis=1)
    fractions = components.sum(axis=0) / n
    return {"method": "DNA_Gaussian_uniformS_v1", "x": centers, "observed": counts,
            "expected": expected, "components": components, "component_names": ["G1", "S", "G2/M"],
            "summary": {"G1_percent": fractions[0] * 100, "S_percent": fractions[1] * 100,
                        "G2M_percent": fractions[2] * 100, "G1_peak": fit.x[0] * g1_peak, "G1_CV": fit.x[1],
                        "fitted_events": int(n), "excluded_events": len(original) - int(n),
                        "reduced_Pearson": float(np.sum((counts - expected)**2 / np.maximum(expected, 1)) / max(1, bins - 5))},
            "parameters": {"initial_G1": g1_peak, "initial_cv": cv, "bins": bins, "low": low, "high": high},
            "limitations": "Exploratory Gaussian/uniform-S model; no debris, aneuploidy or doublet component. Review residuals."}


def proliferation_metrics(counts):
    counts = np.asarray(counts, float)
    if np.any(counts < 0) or not np.isfinite(counts).all() or counts.sum() <= 0:
        raise ValueError("Generation counts must be finite, nonnegative and have positive total")
    generations = np.arange(len(counts))
    precursors = counts / 2.0**generations
    responding = precursors[1:].sum()
    divisions = (precursors * generations).sum()
    return {"percent_divided": responding / precursors.sum() * 100,
            "division_index": divisions / precursors.sum(),
            "proliferation_index": divisions / responding if responding > 1e-12 else None,
            "expansion_index": counts.sum() / precursors.sum(),
            "replication_index": counts[1:].sum() / responding if responding > 1e-12 else None}


def proliferation(values, undivided_peak: float, generations=6, background=0.0, bins=180):
    """Fixed twofold peak spacing in log2, optimized shared width and mixture weights."""
    if undivided_peak <= background or not 1 <= generations <= 12:
        raise ValueError("Undivided peak must exceed background; divisions must be 1–12")
    original = np.asarray(values, float)
    corrected = original - background
    valid = np.isfinite(corrected) & (corrected > 0)
    transformed = np.log2(corrected[valid])
    centers0 = np.log2(undivided_peak - background) - np.arange(generations + 1)
    low, high = centers0[-1] - 1, centers0[0] + 1
    included = transformed[(transformed >= low) & (transformed <= high)]
    counts, edges, centers = _fit_histogram(included, np.linspace(low, high, bins + 1))
    n = counts.sum()

    def components(p):
        probs = np.diff(ndtr((edges[:, None] - centers0[None, :]) / p[0]), axis=0)
        probs /= probs.sum(axis=0)
        return probs * softmax(np.r_[p[1:], 0]) * n

    def objective(p):
        expected = np.maximum(components(p).sum(axis=1), 1e-12)
        return float(np.sum(expected - counts * np.log(expected)))

    fit = minimize(objective, np.r_[.18, np.zeros(generations)], method="L-BFGS-B",
                   bounds=[(.035, .6)] + [(-18, 18)] * generations)
    if not fit.success:
        raise ValueError(f"Proliferation fit did not converge: {fit.message}")
    fitted = components(fit.x)
    generation_counts = fitted.sum(axis=0)
    expected = fitted.sum(axis=1)
    return {"method": "dye_dilution_log2_mixture_v1", "x": centers, "observed": counts,
            "expected": expected, "components": fitted,
            "component_names": [f"G{i}" for i in range(generations + 1)],
            "generation_counts": generation_counts,
            "summary": {**proliferation_metrics(generation_counts), "sigma_log2": fit.x[0],
                        "fitted_events": int(n), "excluded_events": len(original) - int(n),
                        "reduced_Pearson": float(np.sum((counts - expected)**2 / np.maximum(expected, 1)) / max(1, bins - generations - 2))},
            "parameters": {"undivided_peak": undivided_peak, "generations": generations,
                           "background": background, "bins": bins},
            "limitations": "Requires an undivided control peak; fixed twofold dilution, no dye-loss model. Indices depend on included generations."}


def kinetics(time, signal, bin_width=5.0, baseline_end=None):
    t, y = np.asarray(time, float), np.asarray(signal, float)
    if t.shape != y.shape or bin_width <= 0:
        raise ValueError("Time/signal lengths must agree and bin width must be positive")
    valid = np.isfinite(t) & np.isfinite(y)
    t, y = t[valid], y[valid]
    if not len(t) or np.ptp(t) == 0:
        raise ValueError("No finite time series with positive duration")
    start, end = float(t.min()), float(t.max())
    n_bins = int(np.ceil((end - start) / bin_width))
    if n_bins > 100000:
        raise ValueError("Too many time bins; increase bin width")
    edges = start + np.arange(n_bins + 1) * bin_width
    assignment = np.minimum(np.searchsorted(edges, t, side="right") - 1, n_bins - 1)
    baseline = None
    if baseline_end is not None:
        baseline_values = y[t <= baseline_end]
        if not len(baseline_values):
            raise ValueError("Baseline interval contains no events")
        baseline = float(np.median(baseline_values))
        if baseline == 0:
            raise ValueError("Cannot normalize to a zero baseline")
    rows = []
    for i in range(n_bins):
        values = y[assignment == i]
        median = float(np.median(values)) if len(values) else None
        rows.append({"time_start": edges[i], "time_end": edges[i+1], "time_mid": (edges[i]+edges[i+1])/2,
                     "events": len(values), "median": median,
                     "q25": float(np.quantile(values, .25)) if len(values) else None,
                     "q75": float(np.quantile(values, .75)) if len(values) else None,
                     "fold_baseline": median / baseline if median is not None and baseline is not None else None})
    return {"method": "kinetics_binned_median", "rows": rows,
            "parameters": {"bin_width_seconds": bin_width, "baseline_end": baseline_end, "baseline": baseline},
            "excluded_events": int((~valid).sum())}
