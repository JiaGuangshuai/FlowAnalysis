from copy import deepcopy

import numpy as np

from .advanced import cell_cycle, embedding, flowsom_cluster, kinetics, proliferation
from .gating import masks
from .io import read_fcs
from .model import Transform
from .processing import apply_compensation, apply_unmixing
from .provenance import software_versions


def import_files(paths):
    samples, errors = [], []
    for path in paths:
        try:
            samples.append(read_fcs(path))
        except Exception as error:
            errors.append({"path": path, "error": str(error)})
    return samples, errors


def process_sample(sample, mode, channels, matrix, components=None, background=None, provenance=None):
    before = deepcopy(sample.gates)
    if mode == "spectral":
        apply_unmixing(sample, channels, components, matrix, background, provenance)
    else:
        apply_compensation(sample, channels, matrix)
        sample.processing[-1]["provenance"] = provenance or {}
    invalid = {g.id for g in sample.gates if set(g.axes) - set(sample.channels) or g.kind == "indices"}
    changed = True
    while changed:
        old = len(invalid)
        invalid |= {g.id for g in sample.gates if g.parent in invalid or set(g.geometry.get("refs", [])) & invalid}
        changed = old != len(invalid)
    sample.gates = [g for g in sample.gates if g.id not in invalid]
    if invalid:
        sample.processing[-1]["archived_gates"] = [g.to_dict() for g in before if g.id in invalid]
    masks(sample)
    return sample


def advanced_analysis(sample, gate_id, method, channels, parameters):
    membership = masks(sample)[gate_id]
    ids = np.flatnonzero(membership)
    values = sample.data[membership]
    indices = [sample.channels.index(c) for c in channels]
    p = dict(parameters)
    if method in {"UMAP", "t-SNE", "FlowSOM"}:
        transform = Transform(kind=p["transform"], cofactor=p["cofactor"])
        if method == "FlowSOM":
            result = flowsom_cluster(values, indices, p["clusters"], p["grid"], p["seed"],
                                     transform, p["standardize"], p["limit"])
            result["event_indices"] = ids
        else:
            result = embedding(values, indices, method, p["seed"], p["limit"], p["neighbors"],
                               p["min_dist"], p["perplexity"], p["iterations"], transform, p["standardize"])
            result["event_indices"] = ids[result["event_indices"]]
    elif method == "cell_cycle":
        result = cell_cycle(values[:, indices[0]], p["g1"], p["cv"])
    elif method == "proliferation":
        result = proliferation(values[:, indices[0]], p["peak"], p["generations"], p["background"])
    elif method == "kinetics":
        result = kinetics(values[:, sample.channels.index(p["time_channel"])] * p.get("time_scale", 1),
                          values[:, indices[0]], p["bin_width"],
                          p["baseline_end"] if p["baseline"] else None)
    else:
        raise ValueError("Unknown analysis method")
    result["sample_id"] = sample.id
    result["sample_revision"] = sample.revision
    result["gate_id"] = gate_id
    result["gate_name"] = next((g.name for g in sample.gates if g.id == gate_id), "All events")
    result["channels"] = channels
    result["population_events"] = len(ids)
    result["processing"] = sample.processing
    result["software_versions"] = software_versions()
    return result
