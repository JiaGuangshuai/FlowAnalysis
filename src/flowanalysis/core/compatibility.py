from dataclasses import asdict
import inspect
from pathlib import Path
import warnings

import numpy as np

from .gating import masks
from .io import json_clean
from .model import Gate, Sample, Transform


def serialize_transform(transform):
    if transform is None:
        return asdict(Transform())
    parameters = {}
    for name,param in inspect.signature(type(transform)).parameters.items():
        if name in {"args","kwargs"}:
            continue
        attribute = "width_basis" if name == "width" else name
        if hasattr(transform,attribute):
            parameters[name] = getattr(transform,attribute)
        elif param.default is not inspect.Parameter.empty:
            parameters[name] = param.default
        else:
            raise ValueError(f"Cannot serialize transform parameter {name}")
    result = Transform(kind="flowkit",fk_class=type(transform).__name__,fk_parameters=json_clean(parameters))
    result.apply(np.array([1.,100.]))
    return asdict(result)


def convert_strategy(fk_sample,strategy,source):
    """Convert supported geometry and preserve unsupported populations as frozen membership.

    Every converted population is compared event-by-event with FlowKit before
    acceptance. A discrepancy is explicit and falls back to a frozen population.
    """
    result = strategy.gate_sample(fk_sample,cache_events=False)
    sample = Sample(fk_sample.id,fk_sample.get_events(source="raw"),list(fk_sample.pnn_labels),
                    list(fk_sample.pns_labels),metadata={**dict(fk_sample.metadata),"imported_workspace":str(source)},
                    source=str(getattr(fk_sample,"current_filename","") or ""),state="unknown")
    arrays = [sample.raw]
    channels = list(sample.raw_channels)
    comp_arrays = {}
    extra_axes = {}
    for key,matrix in strategy.comp_matrices.items():
        comp_arrays[key] = matrix.apply(fk_sample)
    report = {"source":str(source),"native":[],"frozen":[],"skipped":[]}
    gate_map = {("root",):"root"}
    for name,path in sorted(strategy.get_gate_ids(),key=lambda item:len(item[1])):
        full = tuple(path)+(name,)
        try:
            reference_mask = result.get_gate_membership(name,path)
        except (KeyError,ValueError):
            report["skipped"].append({"gate":name,"path":path,"reason":"Container gate without direct event membership"})
            gate_map[full] = gate_map.get(tuple(path),"root")
            continue
        foreign = strategy.get_gate(name,path)
        parent_id = gate_map.get(tuple(path),"root")
        gate = None
        reason = ""
        try:
            axes,transforms = [],[]
            for dimension in foreign.dimensions:
                channel = dimension.id
                cref = dimension.compensation_ref
                if channel not in sample.raw_channels:
                    raise ValueError("Derived/imported dimension requires frozen membership")
                if cref not in (None,"uncompensated"):
                    if cref == "FCS":
                        import flowkit as fk
                        matrix = fk.Matrix(fk_sample.metadata.get("spillover") or fk_sample.metadata.get("spill"),
                                           [fk_sample.pnn_labels[i] for i in fk_sample.fluoro_indices])
                        comp_arrays[cref] = matrix.apply(fk_sample)
                    if cref not in comp_arrays:
                        raise ValueError(f"Missing compensation reference {cref}")
                    key = (channel,cref)
                    if key not in extra_axes:
                        label = f"{channel} [{cref}]"
                        if label in channels:
                            raise ValueError("Imported channel alias collision")
                        channels.append(label)
                        arrays.append(comp_arrays[cref][:,[sample.raw_channels.index(channel)]])
                        extra_axes[key] = label
                    channel = extra_axes[key]
                axes.append(channel)
                transform = strategy.transformations.get(dimension.transformation_ref)
                transforms.append(serialize_transform(transform))
            if getattr(foreign,"use_complement",False):
                raise ValueError("Complement geometry preserved as frozen membership")
            kind = type(foreign).__name__
            if kind == "RectangleGate":
                geometry = {"bounds":[[d.min,d.max] for d in foreign.dimensions],"max_inclusive":False}
                gate = Gate(name,"range" if len(axes)==1 else "rectangle",axes,transforms,geometry,parent=parent_id)
            elif kind == "PolygonGate":
                gate = Gate(name,"polygon",axes,transforms,{"vertices":json_clean(foreign.vertices)},parent=parent_id)
            else:
                raise ValueError(f"{kind} is preserved as frozen membership")
        except Exception as error:
            reason = str(error)
        sample.data = np.column_stack(arrays)
        sample.channels = channels
        sample.markers = sample.raw_markers + [""]*(len(channels)-len(sample.raw_markers))
        if gate:
            sample.gates.append(gate)
            try:
                actual = masks(sample)[gate.id]
                mismatch = int(np.count_nonzero(actual != reference_mask))
                if mismatch:
                    reason = f"{mismatch} event-boundary differences; frozen to preserve the reference result"
                    sample.gates.pop()
                    gate = None
            except Exception as error:
                sample.gates.pop()
                gate = None
                reason = str(error)
        if gate is None:
            gate = Gate(name,"indices",parent=parent_id,
                        geometry={"indices":np.flatnonzero(reference_mask).tolist(),"source":str(source)})
            sample.gates.append(gate)
            report["frozen"].append({"gate":name,"path":path,"reason":reason})
        else:
            report["native"].append({"gate":name,"path":path})
        gate_map[full] = gate.id
    sample.data.setflags(write=False)
    sample.state = "compensated" if comp_arrays else "unknown"
    sample.processing.append({"method":"FlowKit_workspace_import","source":str(source),"report":report,
                              "compensation_matrices":{key:{"detectors":m.detectors,"matrix":m.matrix.tolist()}
                                                       for key,m in strategy.comp_matrices.items()}})
    return sample,report


def import_workspace(path,fcs_paths):
    import flowkit as fk

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        workspace = fk.Workspace(path,fcs_samples=fcs_paths,find_fcs_files_from_wsp=False)
        converted,reports = [],[]
        for sid in workspace.get_sample_ids():
            sample,report = convert_strategy(workspace.get_sample(sid),workspace.get_gating_strategy(sid),path)
            original = next((p for p in fcs_paths if Path(p).name == sid),"")
            sample.source = original
            converted.append(sample)
            reports.append(report)
    return converted,{"samples":reports,"warnings":[str(w.message) for w in caught],
                      "limitations":"Unsupported geometry is frozen event membership; no layout/plugin import."}


def import_gatingml(path,sample):
    import flowkit as fk
    fs = fk.Sample(sample.raw,sample_id=sample.name,channel_labels=sample.raw_channels,preprocess=False)
    converted,report = convert_strategy(fs,fk.parse_gating_xml(path),path)
    converted.source = sample.source
    return [converted],{"samples":[report],"warnings":[]}
