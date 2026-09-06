import numpy as np
import pytest

from flowanalysis.core.advanced import cell_cycle, embedding, flowsom_cluster, kinetics, proliferation, proliferation_metrics
from flowanalysis.core.model import Transform


@pytest.mark.parametrize("initial_peak", [46000, 50000, 54000])
def test_cell_cycle_known_mixture(initial_peak):
    rng = np.random.default_rng(7)
    n = 20000
    values = np.r_[rng.normal(50000,3000,int(n*.6)),
                   rng.uniform(50000,100000,int(n*.25))+rng.normal(0,3000,int(n*.25)),
                   rng.normal(100000,3000*np.sqrt(2),int(n*.15))]
    result = cell_cycle(values,initial_peak)
    summary = result["summary"]
    assert abs(summary["G1_percent"]-60) < 2
    assert abs(summary["S_percent"]-25) < 2
    assert abs(summary["G2M_percent"]-15) < 2
    assert abs(summary["G1_peak"]-50000) < 500
    assert abs(sum(summary[k] for k in ["G1_percent","S_percent","G2M_percent"])-100) < 1e-8


def test_proliferation_metrics_reference_arithmetic():
    metrics = proliferation_metrics([15888,32922,13647,897])
    assert metrics["division_index"] == pytest.approx(23620.875/35872.875)
    assert metrics["proliferation_index"] == pytest.approx(23620.875/19984.875)
    assert metrics["expansion_index"] == pytest.approx(63354/35872.875)
    assert proliferation_metrics([100,0])["proliferation_index"] is None


def test_proliferation_known_generations():
    rng = np.random.default_rng(8)
    counts = [4000,3000,2000,1000]
    values = np.concatenate([50000/2**g * 2**rng.normal(0,.15,n) for g,n in enumerate(counts)])
    result = proliferation(values,50000,generations=3)
    np.testing.assert_allclose(result["generation_counts"],counts,rtol=.035)
    assert result["summary"]["excluded_events"] == 0


def test_kinetics_empty_bins_and_last_event():
    result = kinetics([0,1,9,10],[1,3,7,9],bin_width=2)
    rows = result["rows"]
    assert sum(r["events"] for r in rows) == 4
    assert rows[0]["median"] == 2
    assert rows[1]["median"] is None
    assert rows[-1]["events"] == 2
    with pytest.raises(ValueError):
        kinetics([0,1],[0,0],baseline_end=1)


@pytest.mark.parametrize("method",["UMAP","t-SNE"])
def test_embeddings_reproducible_with_fixed_event_indices(method):
    rng = np.random.default_rng(4)
    data = rng.normal(size=(240,4))
    kwargs = dict(method=method,seed=12,limit=180,neighbors=8,perplexity=20,iterations=300,transform=Transform())
    a = embedding(data,[0,1,2,3],**kwargs)
    b = embedding(data,[0,1,2,3],**kwargs)
    assert np.shape(a["coordinates"]) == (180,2)
    assert np.isfinite(a["coordinates"]).all()
    np.testing.assert_array_equal(a["event_indices"],b["event_indices"])
    np.testing.assert_allclose(a["coordinates"],b["coordinates"],atol=1e-5)


def test_flowsom_assigns_all_events():
    rng = np.random.default_rng(4)
    data = np.r_[rng.normal(0,.3,(150,3)),rng.normal(4,.3,(150,3))]
    result = flowsom_cluster(data,[0,1,2],n_clusters=2,grid=3,seed=4,transform=Transform(),train_limit=150)
    assert len(result["labels"]) == 300
    assert sum(result["counts"]) == 300
    assert len(set(result["labels"])) == 2
    # The two separated clouds should be predominantly in different metaclusters.
    a = np.bincount(result["labels"][:150]).argmax()
    b = np.bincount(result["labels"][150:]).argmax()
    assert a != b
