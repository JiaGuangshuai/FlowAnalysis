from __future__ import annotations

import ast
import operator

import numpy as np
from scipy.linalg import lstsq

from .model import Sample


def compensate(events: np.ndarray, spill: np.ndarray) -> np.ndarray:
    """Rows of spill are source dyes, columns measured detectors: Y = X @ S."""
    y, s = np.asarray(events, float), np.asarray(spill, float)
    if s.ndim != 2 or s.shape[0] != s.shape[1] or y.shape[1] != s.shape[0]:
        raise ValueError("Compensation matrix shape mismatch")
    if not np.isfinite(y).all() or not np.isfinite(s).all() or np.any(np.diag(s) <= 0):
        raise ValueError("Compensation requires finite values and positive diagonal")
    if np.linalg.matrix_rank(s) != len(s) or np.linalg.cond(s) > 1e8:
        raise ValueError("Singular or ill-conditioned spillover matrix")
    return np.linalg.solve(s.T, y.T).T


def apply_compensation(sample: Sample, channels: list[str], matrix: np.ndarray):
    if sample.state not in {"raw-conventional", "unknown"}:
        raise ValueError("Compensation requires raw conventional data; restore raw data first")
    if len(set(channels)) != len(channels):
        raise ValueError("Duplicate matrix channels")
    indices = [sample.raw_channels.index(c) for c in channels]
    result = sample.raw.copy()
    result[:, indices] = compensate(result[:, indices], matrix)
    sample.replace_data(result, sample.raw_channels,
                        {"method": "linear_compensation", "channels": channels, "spill": matrix.tolist(),
                         "orientation": "source_rows_detector_columns", "unit": "fraction"}, "compensated")


def estimate_spill(positive: list[np.ndarray], negative: list[np.ndarray], primary: list[int]) -> np.ndarray:
    if not positive or len(positive) != len(negative) or len(primary) != len(positive):
        raise ValueError("One positive and negative population is required per dye")
    rows = []
    for pos, neg, detector in zip(positive, negative, primary):
        if len(pos) < 20 or len(neg) < 20:
            raise ValueError("Each positive and negative gate must contain at least 20 events")
        difference = np.median(pos, axis=0) - np.median(neg, axis=0)
        if not np.isfinite(difference).all() or difference[detector] <= 0:
            raise ValueError("Positive control has no positive primary-detector separation")
        rows.append(difference / difference[detector])
    result = np.array(rows)
    if result.shape[0] != result.shape[1]:
        raise ValueError("Conventional compensation requires a square matrix")
    return result


def reference_spectra(positive: list[np.ndarray], negative: list[np.ndarray]) -> np.ndarray:
    if not positive or len(positive) != len(negative):
        raise ValueError("Matched positive and negative populations are required")
    spectra = []
    for pos, neg in zip(positive, negative):
        if len(pos) < 20 or len(neg) < 20:
            raise ValueError("Reference gates need at least 20 events")
        spectrum = np.median(pos, axis=0) - np.median(neg, axis=0)
        scale = np.max(spectrum)
        if not np.isfinite(spectrum).all() or scale <= 0:
            raise ValueError("Reference spectrum lacks a positive signal")
        spectra.append(spectrum / scale)
    return np.column_stack(spectra)


def unmix(events: np.ndarray, spectra: np.ndarray, background=None) -> tuple[np.ndarray, dict]:
    """Y = A @ R.T + background. Unconstrained OLS retains negative values."""
    y, r = np.asarray(events, float), np.asarray(spectra, float)
    if y.ndim != 2 or r.ndim != 2 or y.shape[1] != r.shape[0] or r.shape[0] < r.shape[1]:
        raise ValueError("Spectral model must have detector rows and component columns; detectors >= components")
    b = np.zeros(r.shape[0]) if background is None else np.asarray(background, float)
    if b.shape != (r.shape[0],) or not all(np.isfinite(v).all() for v in [y, r, b]):
        raise ValueError("Non-finite values or invalid background vector")
    coefficients, _, rank, singular = lstsq(r, (y - b).T, lapack_driver="gelsd")
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")
    if rank < r.shape[1] or condition > 1e8:
        raise ValueError("Reference spectra are rank deficient or too ill-conditioned to resolve")
    result = coefficients.T
    residual = y - (result @ r.T + b)
    norms = np.linalg.norm(r, axis=0)
    similarity = (r.T @ r) / np.outer(norms, norms)
    return result, {"rank": int(rank), "condition_number": condition,
                    "rmse_per_detector": np.sqrt(np.mean(residual**2, axis=0)).tolist(),
                    "median_event_rmse": float(np.median(np.sqrt(np.mean(residual**2, axis=1)))),
                    "spectral_cosine_similarity": similarity.tolist(),
                    "negative_fraction": np.mean(result < 0, axis=0).tolist(),
                    "warning": "High spectral collinearity" if condition > 100 else ""}


def apply_unmixing(sample: Sample, detectors: list[str], components: list[str], spectra: np.ndarray,
                   background=None, provenance: dict | None = None):
    if sample.state not in {"raw-spectral", "unknown"}:
        raise ValueError("Unmixing requires raw detector data; restore raw data first")
    if len(set(detectors)) != len(detectors) or len(set(components)) != len(components):
        raise ValueError("Duplicate detector/component names")
    indices = [sample.raw_channels.index(c) for c in detectors]
    values, qc = unmix(sample.raw[:, indices], spectra, background)
    if values.shape[1] != len(components):
        raise ValueError("Component names and spectrum columns differ")
    keep = [i for i, c in enumerate(sample.raw_channels) if c not in detectors]
    channels = [sample.raw_channels[i] for i in keep] + components
    result = np.column_stack([sample.raw[:, keep], values])
    sample.replace_data(result, channels, {"method": "spectral_ols_svd", "detectors": detectors,
                        "components": components, "spectra": np.asarray(spectra).tolist(),
                        "background": None if background is None else np.asarray(background).tolist(),
                        "qc": qc, "provenance": provenance or {},
                        "negative_values": "retained"}, "unmixed")
    return qc


def derived_parameter(expression: str, columns: dict[str, np.ndarray]) -> np.ndarray:
    """Strict AST arithmetic with c0/c1 channel aliases; no Python eval or attribute access."""
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.Pow: operator.pow}
    funcs = {"log10": np.log10, "log2": np.log2, "sqrt": np.sqrt, "abs": np.abs,
             "arcsinh": np.arcsinh, "exp": np.exp, "minimum": np.minimum, "maximum": np.maximum}
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Expression is too complex")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in columns:
            return columns[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs and not node.keywords:
            return funcs[node.func.id](*[visit(arg) for arg in node.args])
        raise ValueError("Expression supports only channel aliases, numbers and approved arithmetic/functions")

    with np.errstate(all="ignore"):
        result = np.asarray(visit(tree), dtype=float)
    n = len(next(iter(columns.values())))
    result = np.broadcast_to(result, (n,)).copy()
    if not np.isfinite(result).all():
        raise ValueError("Derived values contain NaN/Infinity (check division by zero or logarithm domains)")
    return result
