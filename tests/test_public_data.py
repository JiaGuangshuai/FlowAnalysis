from pathlib import Path
import json

import numpy as np
import pytest

from flowanalysis.core.compatibility import import_workspace
from flowanalysis.core.io import read_fcs
from flowanalysis.core.gating import masks

DATA = Path(__file__).resolve().parents[1]/"local-data/public-flowkit"


@pytest.mark.skipif(not (DATA/"101_DEN084Y5_15_E01_008_clean.fcs").exists(),reason="Public FCS downloaded separately")
def test_public_fcs_matches_flowkit_linearized_values():
    import flowkit as fk
    path = DATA/"101_DEN084Y5_15_E01_008_clean.fcs"
    sample = read_fcs(path)
    reference = fk.Sample(str(path))
    assert sample.data.shape[0] > 100000
    np.testing.assert_array_equal(sample.data,reference.get_events(source="raw"))
    assert sample.channels == reference.pnn_labels


@pytest.mark.skipif(not (DATA/"test_data_diamond_01.fcs").exists(),reason="Public FCS downloaded separately")
def test_workspace_native_conversion_matches_reference():
    samples,report = import_workspace(str(DATA/"test_data_diamond_asinh_rect.wsp"),
                                      [str(DATA/"test_data_diamond_01.fcs")])
    assert len(samples) == 1
    assert len(report["samples"][0]["native"]) == 1
    assert not report["samples"][0]["frozen"]
    sample = samples[0]
    assert masks(sample)[sample.gates[0].id].sum() > 0


@pytest.mark.skipif(not (DATA/"spectral_raw_events.npy").exists(),reason="Public spectral fixture downloaded separately")
def test_public_spectral_unmixing_matches_independent_reference():
    from flowanalysis.core.processing import unmix
    labels = json.loads((DATA.parents[1]/"scripts/spectral-labels.json").read_text())
    raw = np.load(DATA/"spectral_raw_events.npy")
    expected = np.load(DATA/"spectral_comp_events.npy")
    spectra = np.load(DATA/"spectral_comp_matrix.npy").T
    ids = [labels["spectral_sample_labels"].index(c) for c in labels["spectral_all_detectors"]]
    output_ids = [labels["spectral_sample_labels"].index(c) for c in labels["spectral_true_detectors"]]
    actual, _ = unmix(raw[:,ids],spectra)
    np.testing.assert_allclose(actual,expected[:,output_ids],rtol=1e-8,atol=1e-6)
