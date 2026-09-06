from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from flowanalysis import __version__
from .model import Gate, Project, Sample


def read_fcs(path: str | Path) -> Sample:
    import flowio

    path = Path(path)
    fd = flowio.FlowData(str(path))
    if fd.text.get("nextdata", "0") not in ("0", "0.0"):
        raise ValueError("Multi-dataset FCS: export each dataset separately before importing")
    raw = fd.as_array(preprocess=True).astype(np.float64)
    meta = dict(fd.text)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    meta["source_sha256"] = digest.hexdigest()
    meta["loader"] = "FlowIO: linearized gain/log/time preprocessing"
    state = meta.get("flowanalysis_state", "unknown")
    if state not in {"unknown", "raw-conventional", "raw-spectral", "compensated", "unmixed"}:
        state = "unknown"
    return Sample(path.stem, raw, list(fd.pnn_labels), list(fd.pns_labels), meta, str(path), state=state)


def write_fcs(path: str | Path, sample: Sample, mask: np.ndarray | None = None):
    import flowio

    values = sample.data if mask is None else sample.data[mask]
    if not len(values):
        raise ValueError("Cannot export an empty FCS population")
    if not np.isfinite(values).all():
        raise ValueError("FCS export requires finite event values")
    metadata = {"flowanalysis_state": sample.state, "flowanalysis_version": __version__,
                "flowanalysis_sample_id": sample.id, "timestep": "1"}
    # Data are already linearized. Never carry forward original gain, spillover,
    # or amplifier metadata that would apply preprocessing a second time.
    for index in range(1, len(sample.channels) + 1):
        metadata[f"p{index}g"] = "1"
        metadata[f"p{index}e"] = "0,0"
    with Path(path).open("wb") as handle:
        flowio.create_fcs(handle, values.ravel().tolist(), sample.channels,
                          opt_channel_names=sample.markers, metadata_dict=metadata)


def json_clean(value):
    if isinstance(value, np.ndarray):
        return json_clean(value.tolist())
    if isinstance(value, np.generic):
        return json_clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): json_clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_clean(v) for v in value]
    return value


def save_project(project: Project, path: str | Path):
    """Atomic portable ZIP: JSON plus non-pickled arrays. No source-path dependency."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "software": __version__, "id": project.id, "name": project.name,
                "layouts": project.layouts, "history": project.history, "samples": []}
    descriptor, temporary = tempfile.mkstemp(prefix=".flowanalysis-", dir=path.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for sample in project.samples:
                fields = {k: v for k, v in vars(sample).items() if k not in {"raw", "data", "gates"}}
                fields["gates"] = [g.to_dict() for g in sample.gates]
                fields["data_is_raw"] = sample.data is sample.raw
                manifest["samples"].append(fields)
                for key in ("raw", "data"):
                    if key == "data" and fields["data_is_raw"]:
                        continue
                    with archive.open(f"arrays/{sample.id}/{key}.npy", "w", force_zip64=True) as handle:
                        np.save(handle, getattr(sample, key), allow_pickle=False)
            archive.writestr("manifest.json", json.dumps(json_clean(manifest), ensure_ascii=False, allow_nan=False))
        # Windows FlushFileBuffers requires a writable handle.
        with open(temporary, "rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_project(path: str | Path) -> Project:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > 100 * 1024**2:
            raise ValueError("Project manifest exceeds 100 MB")
        if sum(i.file_size for i in archive.infolist()) > 16 * 1024**3:
            raise ValueError("Project exceeds the 16 GB uncompressed import limit")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != 1:
            raise ValueError("Unsupported project format version")
        project = Project(name=manifest["name"], id=manifest["id"], layouts=manifest.get("layouts", []),
                          history=manifest.get("history", []))
        for entry in manifest["samples"]:
            fields = dict(entry)
            sid = fields["id"]
            raw = np.load(io.BytesIO(archive.read(f"arrays/{sid}/raw.npy")), allow_pickle=False)
            same = fields.pop("data_is_raw")
            data = raw if same else np.load(io.BytesIO(archive.read(f"arrays/{sid}/data.npy")), allow_pickle=False)
            fields["gates"] = [Gate(**g) for g in fields["gates"]]
            project.samples.append(Sample(raw=raw, data=data, **fields))
        if len({s.id for s in project.samples}) != len(project.samples):
            raise ValueError("Duplicate sample ID in project")
        from .gating import masks
        for sample in project.samples:
            masks(sample)
        return project


def read_matrix(path: str | Path) -> tuple[list[str], np.ndarray]:
    import pandas as pd

    table = pd.read_csv(path, index_col=0, sep=None, engine="python")
    channels = list(table.columns.astype(str))
    if list(table.index.astype(str)) != channels:
        raise ValueError("Matrix CSV must have matching row and column channel names in the same order")
    return channels, table.to_numpy(dtype=float)


def spill_from_metadata(sample: Sample) -> tuple[list[str], np.ndarray]:
    value = sample.metadata.get("spillover") or sample.metadata.get("spill")
    if not value:
        raise ValueError("No SPILL/SPILLOVER matrix in this FCS file")
    parts = value.split(",")
    n = int(parts[0])
    if n < 1 or len(parts) != 1 + n + n * n:
        raise ValueError("Malformed FCS spillover matrix")
    return parts[1:n + 1], np.asarray(parts[n + 1:], float).reshape(n, n)
