from __future__ import annotations

from copy import deepcopy

import numpy as np

from .model import Gate, Sample, Transform, uid


def polygon_mask(points: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    """Even/odd rule with boundary points included (scale-relative 1e-12 tolerance)."""
    vertices = np.asarray(vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or len(vertices) < 3 or not np.isfinite(vertices).all():
        raise ValueError("A polygon requires at least three finite vertices")
    x, y = points.T
    inside = np.zeros(len(points), bool)
    boundary = np.zeros(len(points), bool)
    tolerance = max(1.0, float(np.ptp(vertices, axis=0).max())) * 1e-12
    for p, q in zip(vertices, np.roll(vertices, -1, axis=0)):
        dx, dy = q - p
        length = np.hypot(dx, dy)
        if length == 0:
            continue
        cross = (x - p[0]) * dy - (y - p[1]) * dx
        dot = (x - p[0]) * dx + (y - p[1]) * dy
        boundary |= (np.abs(cross) <= tolerance * length) & (dot >= -tolerance) & (dot <= length**2 + tolerance)
        if dy != 0:
            inside ^= ((p[1] > y) != (q[1] > y)) & (x < (q[0] - p[0]) * (y - p[1]) / dy + p[0])
    return (inside | boundary) & np.isfinite(points).all(axis=1)


def masks(sample: Sample) -> dict[str, np.ndarray]:
    gates = {g.id: g for g in sample.gates}
    if len(gates) != len(sample.gates) or "root" in gates:
        raise ValueError("Duplicate or reserved gate ID")
    results = {"root": np.ones(len(sample.data), bool)}
    visiting = set()

    def resolve(gid):
        if gid in results:
            return results[gid]
        if gid in visiting or gid not in gates:
            raise ValueError("Gate dependency cycle or missing gate")
        visiting.add(gid)
        gate = gates[gid]
        parent = resolve(gate.parent)
        if gate.kind == "boolean":
            refs = gate.geometry.get("refs", [])
            if not refs:
                raise ValueError("Boolean gate requires references")
            operands = [resolve(ref) for ref in refs]
            op = gate.geometry.get("op", "AND")
            if op == "AND":
                chosen = np.logical_and.reduce(operands)
            elif op == "OR":
                chosen = np.logical_or.reduce(operands)
            elif op == "NOT" and len(operands) == 1:
                chosen = ~operands[0]
            else:
                raise ValueError("Invalid Boolean operation")
        elif gate.kind == "indices":
            chosen = np.zeros(len(sample.data), bool)
            indices = np.asarray(gate.geometry["indices"], dtype=int)
            if (indices < 0).any() or (indices >= len(chosen)).any():
                raise ValueError("Event indices out of bounds")
            chosen[indices] = True
        else:
            if len(gate.axes) != len(gate.transforms) or not gate.axes:
                raise ValueError("Gate transform definition is incomplete")
            coords = [Transform(**tr).apply(sample.column(axis)) for axis, tr in zip(gate.axes, gate.transforms)]
            chosen = np.logical_and.reduce([np.isfinite(v) for v in coords])
            if gate.kind in ("rectangle", "range"):
                for values, limits in zip(coords, gate.geometry["bounds"], strict=True):
                    lo, hi = limits
                    if lo is not None:
                        chosen &= values >= lo
                    if hi is not None:
                        chosen &= values <= hi if gate.geometry.get("max_inclusive", True) else values < hi
            elif gate.kind == "polygon":
                chosen &= polygon_mask(np.column_stack(coords), gate.geometry["vertices"])
            elif gate.kind == "ellipse":
                center = np.asarray(gate.geometry["center"])
                radii = np.asarray(gate.geometry["radii"])
                if len(coords) != 2 or (radii <= 0).any():
                    raise ValueError("Ellipse radii must be positive")
                xy = np.column_stack(coords) - center
                angle = float(gate.geometry.get("angle", 0))
                c, s = np.cos(angle), np.sin(angle)
                rotated = xy @ np.array([[c, -s], [s, c]])
                chosen &= ((rotated / radii)**2).sum(axis=1) <= 1 + 1e-12
            elif gate.kind == "quadrant":
                for values, threshold, positive in zip(coords, gate.geometry["thresholds"], gate.geometry["positive"], strict=True):
                    chosen &= values >= threshold if positive else values < threshold
            else:
                raise ValueError(f"Unsupported gate: {gate.kind}")
        results[gid] = chosen & parent
        visiting.remove(gid)
        return results[gid]

    for gid in gates:
        resolve(gid)
    return results


def statistics(sample: Sample, channels: list[str] | None = None) -> list[dict]:
    membership = masks(sample)
    total = len(sample.data)
    rows = []
    for gate in [Gate("All events", "root", id="root"), *sample.gates]:
        mask = membership[gate.id]
        count = int(mask.sum())
        denominator = total if gate.id == "root" else int(membership[gate.parent].sum())
        row = {"sample": sample.name, "sample_id": sample.id, "group": sample.group, "plate": sample.plate,
               "well": sample.well, "gate": gate.name, "gate_id": gate.id, "parent_id": gate.parent,
               "events": count, "parent_events": denominator,
               "percent_parent": count / denominator * 100 if denominator else None,
               "percent_total": count / total * 100 if total else None,
               "data_state": sample.state, "intensity_space": "processed_linear"}
        for channel in channels or []:
            values = sample.column(channel)[mask]
            values = values[np.isfinite(values)]
            row[f"{channel}:median"] = float(np.median(values)) if len(values) else None
            row[f"{channel}:mean"] = float(np.mean(values)) if len(values) else None
            row[f"{channel}:std"] = float(np.std(values, ddof=1)) if len(values) > 1 else None
        rows.append(row)
    return rows


def copy_strategy(source: Sample, destination: Sample):
    if any(g.kind == "indices" for g in source.gates):
        raise ValueError("Event-index gates cannot be transferred between samples")
    needed = {axis for gate in source.gates for axis in gate.axes}
    missing = needed - set(destination.channels)
    if missing:
        raise ValueError(f"Missing channels in {destination.name}: {', '.join(sorted(missing))}")
    mapping = {g.id: uid() for g in source.gates} | {"root": "root"}
    copied = deepcopy(source.gates)
    for gate in copied:
        gate.id = mapping[gate.id]
        gate.parent = mapping[gate.parent]
        if gate.kind == "boolean":
            gate.geometry["refs"] = [mapping[r] for r in gate.geometry["refs"]]
    destination.gates = copied
    destination.results = []
    destination.revision += 1
