from dataclasses import asdict

import numpy as np
import pytest

from flowanalysis.core.gating import copy_strategy, masks, polygon_mask, statistics
from flowanalysis.core.io import load_project, read_fcs, save_project, write_fcs
from flowanalysis.core.model import Gate, Project, Sample, Transform
from flowanalysis.core.processing import (
    apply_compensation, apply_unmixing, compensate, derived_parameter, estimate_spill,
    reference_spectra, unmix,
)


def sample_grid():
    x,y = np.meshgrid(np.arange(-2,3),np.arange(-2,3))
    return Sample("grid",np.column_stack([x.ravel(),y.ravel()]),["x","y"])


def test_compensation_recovers_signed_truth():
    rng = np.random.default_rng(1)
    true = rng.normal(300,500,(2000,3))
    spill = np.array([[1,.23,.12],[.04,1,.02],[.07,.08,1]])
    observed = true @ spill
    np.testing.assert_allclose(compensate(observed,spill),true,rtol=1e-12,atol=1e-10)
    with pytest.raises(ValueError):
        compensate(observed,np.ones((3,3)))


def test_compensation_channel_order_and_duplicate_prevention():
    s = Sample("s",np.array([[1,3,100],[2,5,110]],float),["A","B","FSC"],state="raw-conventional")
    apply_compensation(s,["B","A"],np.array([[1,.2],[.1,1]]))
    np.testing.assert_array_equal(s.column("FSC"),[100,110])
    np.testing.assert_allclose(s.data[:,:2][:,[1,0]] @ np.array([[1,.2],[.1,1]]),s.raw[:,:2][:,[1,0]])
    with pytest.raises(ValueError):
        apply_compensation(s,["A","B"],np.eye(2))


def test_spectral_recovery_background_and_rank():
    rng = np.random.default_rng(2)
    reference = rng.uniform(.1,1,(9,4))
    truth = rng.normal(1000,500,(5000,4))
    background = np.arange(9)
    result,qc = unmix(truth @ reference.T + background,reference,background)
    np.testing.assert_allclose(result,truth,rtol=1e-11,atol=1e-9)
    assert qc["rank"] == 4
    assert qc["median_event_rmse"] < 1e-9
    assert np.any(result < 0)
    with pytest.raises(ValueError):
        unmix(np.zeros((10,3)),np.ones((3,2)))


def test_spectral_preserves_scatter():
    r = np.array([[1,.1],[.4,1],[.2,.7]])
    true = np.array([[100,200],[200,300]],float)
    raw = np.column_stack([[11,12],true @ r.T])
    s = Sample("s",raw,["FSC","D1","D2","D3"],state="raw-spectral")
    apply_unmixing(s,["D1","D2","D3"],["Dye1","Dye2"],r)
    assert s.channels == ["FSC","Dye1","Dye2"]
    np.testing.assert_allclose(s.data,np.column_stack([[11,12],true]))
    np.testing.assert_array_equal(s.raw,raw)


def test_reference_estimation_has_explicit_orientation():
    negative = [np.zeros((30,2)),np.zeros((30,2))]
    positive = [np.tile([100,20],(30,1)),np.tile([30,100],(30,1))]
    np.testing.assert_allclose(estimate_spill(positive,negative,[0,1]),[[1,.2],[.3,1]])
    np.testing.assert_allclose(reference_spectra(positive,negative),[[1,.3],[.2,1]])
    with pytest.raises(ValueError):
        reference_spectra([positive[0][:3]],[negative[0]])


def test_polygon_boundaries_and_nonfinite():
    points = np.array([[0,0],[1,1],[.5,.5],[1.1,.5],[np.nan,0]])
    result = polygon_mask(points,[[0,0],[1,0],[1,1],[0,1]])
    assert result.tolist() == [True,True,True,False,False]


def test_parent_and_boolean_complement_scope():
    s = sample_grid()
    tr = asdict(Transform())
    parent = Gate("parent","range",["x"],[tr],{"bounds":[[0,None]]})
    positive = Gate("positive","range",["y"],[tr],{"bounds":[[0,None]]},parent=parent.id)
    negative = Gate("not","boolean",geometry={"refs":[positive.id],"op":"NOT"},parent=parent.id)
    s.gates = [parent,positive,negative]
    result = masks(s)
    assert result[parent.id].sum() == 15
    assert result[positive.id].sum() == 9
    assert result[negative.id].sum() == 6
    assert not np.any(result[negative.id] & ~result[parent.id])


def test_quadrants_partition_threshold_events_once():
    s = sample_grid()
    tr = asdict(Transform())
    for flags in [(True,True),(True,False),(False,True),(False,False)]:
        s.gates.append(Gate(str(flags),"quadrant",["x","y"],[tr,tr],{"thresholds":[0,0],"positive":flags}))
    result = masks(s)
    np.testing.assert_array_equal(np.sum([result[g.id] for g in s.gates],axis=0),np.ones(25))


def test_empty_stats_and_cycle_error():
    s = sample_grid()
    gate = Gate("empty","range",["x"],[asdict(Transform())],{"bounds":[[5,None]]})
    child = Gate("child","range",["x"],[asdict(Transform())],{"bounds":[[5,None]]},parent=gate.id)
    s.gates = [gate,child]
    row = statistics(s,["x"])[-1]
    assert row["events"] == 0 and row["percent_parent"] is None and row["x:median"] is None
    gate.parent = child.id
    with pytest.raises(ValueError,match="cycle"):
        masks(s)


def test_transforms_are_finite_and_monotonic():
    values = np.array([-1000,-1,0,1,100,100000],float)
    for kind in ["linear","arcsinh","logicle","hyperlog","biexponential"]:
        result = Transform(kind).apply(values)
        assert np.isfinite(result).all()
        assert np.all(np.diff(result) > 0)
    log = Transform("log").apply(values)
    assert np.isnan(log[:3]).all()


def test_expression_does_not_execute_python():
    columns = {"c0":np.array([4,9]),"c1":np.array([2,3])}
    np.testing.assert_array_equal(derived_parameter("sqrt(c0) + c0 / c1",columns),[4,6])
    for expr in ["__import__('os').system('touch bad')","c0.__class__","[x for x in c0]","c0 / 0"]:
        with pytest.raises(ValueError):
            derived_parameter(expr,columns)


def test_project_portability_and_fcs_linear_roundtrip(tmp_path):
    s = sample_grid()
    s.source = "/nonexistent/original.fcs"
    s.gates = [Gate("gate","range",["x"],[asdict(Transform())],{"bounds":[[0,None]]})]
    project = Project("中文项目",[s])
    path = tmp_path/"中文.flowproj"
    save_project(project,path)
    restored = load_project(path)
    np.testing.assert_array_equal(restored.samples[0].data,s.data)
    assert masks(restored.samples[0])[s.gates[0].id].sum() == 15
    fcs = tmp_path/"测试.fcs"
    write_fcs(fcs,s)
    imported = read_fcs(fcs)
    np.testing.assert_allclose(imported.data,s.data)
    assert imported.raw_channels == s.raw_channels


def test_template_references_are_remapped():
    source,destination = sample_grid(),sample_grid()
    source.gates = [Gate("x+","range",["x"],[asdict(Transform())],{"bounds":[[0,None]]})]
    source.gates.append(Gate("not x+","boolean",geometry={"refs":[source.gates[0].id],"op":"NOT"}))
    copy_strategy(source,destination)
    assert destination.gates[0].id != source.gates[0].id
    assert destination.gates[1].geometry["refs"] == [destination.gates[0].id]
    assert masks(destination)[destination.gates[1].id].sum() == 10
