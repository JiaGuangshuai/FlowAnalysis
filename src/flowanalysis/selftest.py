"""Exercise the standalone application and its spawned analysis process."""
import json
from pathlib import Path
import tempfile
import traceback


def numerical_smoke():
    import numpy as np
    from flowanalysis.core.advanced import cell_cycle, embedding, flowsom_cluster, proliferation, kinetics
    from flowanalysis.core.demo import demo_project
    from flowanalysis.core.gating import masks
    from flowanalysis.core.io import read_fcs, write_fcs, save_project, load_project
    from flowanalysis.core.model import Transform
    from flowanalysis.core.processing import compensate, unmix
    from flowanalysis.core.provenance import software_versions

    rng = np.random.default_rng(40)
    project = demo_project(2000)
    sample = project.samples[0]
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        save_project(project, directory / "test.flowproj")
        assert len(load_project(directory / "test.flowproj").samples) == 6
        write_fcs(directory / "test.fcs", sample)
        np.testing.assert_allclose(read_fcs(directory / "test.fcs").data, sample.data, rtol=1e-6)
    assert len(masks(sample)) == len(sample.gates) + 1
    truth = rng.normal(size=(200, 2))
    spill = np.array([[1, .2], [.1, 1]])
    np.testing.assert_allclose(compensate(truth @ spill, spill), truth, atol=1e-12)
    spectra = np.array([[1, .1], [.2, 1], [.3, .6]])
    unmixed, _ = unmix(truth @ spectra.T, spectra)
    np.testing.assert_allclose(unmixed, truth, atol=1e-12)
    features = rng.normal(size=(200, 4))
    for method in ["UMAP", "t-SNE"]:
        result = embedding(features, [0, 1, 2, 3], method=method, limit=150, iterations=300)
        assert np.shape(result["coordinates"]) == (150, 2)
    result = flowsom_cluster(features, [0, 1, 2, 3], n_clusters=2, grid=3, train_limit=100,
                             transform=Transform())
    assert len(result["labels"]) == 200
    dna = np.r_[rng.normal(50000, 3000, 1000), rng.normal(100000, 4200, 400),
                rng.uniform(50000, 100000, 600)]
    assert cell_cycle(dna, 50000)["summary"]["fitted_events"] == 2000
    dye = np.r_[50000 * 2**rng.normal(0, .15, 1000), 25000 * 2**rng.normal(0, .15, 1000)]
    proliferation(dye, 50000, generations=2)
    assert sum(r["events"] for r in kinetics([0, 1, 9, 10], [1, 2, 3, 4])["rows"]) == 4
    return {"numerical_worker": "passed", "software_versions": software_versions(), "algorithms": ["FCS", "portable project", "gating", "compensation",
            "spectral OLS", "UMAP", "t-SNE", "FlowSOM", "cell cycle", "proliferation", "kinetics"]}


def main(output):
    from PySide6.QtCore import QTimer, QSettings
    from PySide6.QtWidgets import QApplication
    from flowanalysis.core.demo import demo_project
    from flowanalysis.ui.window import MainWindow
    app = QApplication(["FlowAnalysis-self-test", "-style", "Fusion"])
    preferences = tempfile.TemporaryDirectory(prefix="flowanalysis-selftest-")
    settings = QSettings(str(Path(preferences.name)/"preferences.ini"),QSettings.Format.IniFormat)
    window = MainWindow(demo_project(1000), recover=False,settings=settings)
    window.show()
    app.processEvents()
    report = {"ui": "passed", "tabs": window.tabs.count(), "samples": len(window.project.samples)}
    def finish(result=None, error=None):
        report.update(result or {})
        if error:
            report["error"] = error
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        window.dirty = False
        window.tasks.cancel()
        window.close()
        preferences.cleanup()
        app.exit(1 if error else 0)
    try:
        window.switch_language("en")
        window.switch_language("zh")
        window.tasks.finished.disconnect()
        window.tasks.failed.disconnect()
        window.tasks.finished.connect(lambda result: finish(result))
        window.tasks.failed.connect(lambda error, trace: finish(error=error + "\n" + trace))
        # Use the production multiprocessing controller to verify frozen spawn/JIT.
        window.tasks.start(numerical_smoke)
        QTimer.singleShot(180000, lambda: finish(error="Analysis worker timed out after 180 seconds"))
        return app.exec()
    except Exception:
        finish(error=traceback.format_exc())
        return 1
