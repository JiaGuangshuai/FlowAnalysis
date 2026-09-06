"""Create portable public-data projects and explicitly labeled spectral FCS derivatives."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from flowanalysis.core.compatibility import import_workspace
from flowanalysis.core.io import save_project, write_fcs
from flowanalysis.core.model import Project, Sample
from flowanalysis.core.processing import apply_unmixing

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "local-data/public-flowkit"


def main():
    paths = sorted(str(p) for p in DATA.glob("101*.fcs"))
    samples, report = import_workspace(str(DATA / "8_color_ICS.wsp"), paths)
    project = Project(name="公开8色流式测试 · FlowKit public data", samples=samples)
    project.record("public_dataset_import", source="https://github.com/whitews/FlowKit/tree/master/data/8_color_data_set")
    for sample in samples:
        sample.group = "Public 8-color ICS"
    save_project(project, DATA / "公开8色流式测试.flowproj")
    (DATA / "WORKSPACE_IMPORT_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with (DATA / "den_comp.csv").open() as handle:
        channels = [n.strip() for n in handle.readline().strip().lstrip("#").strip().split(",")]
    pd.DataFrame(np.loadtxt(DATA / "den_comp.csv", delimiter=","), index=channels, columns=channels).to_csv(DATA / "den_comp_labeled.csv")
    labels = json.loads((ROOT / "scripts/spectral-labels.json").read_text())
    raw = np.load(DATA / "spectral_raw_events.npy")
    spectra = np.load(DATA / "spectral_comp_matrix.npy").T
    components = ["Component_"+c for c in labels["spectral_true_detectors"]]
    metadata = {"source":"https://github.com/whitews/FlowKit/tree/master/data/spectral_data",
                "notice":"Converted from public .npy fixture; not an original instrument FCS. Component names identify reference matrix rows, not antibody identities."}
    sample = Sample("[PUBLIC FIXTURE] Spectral raw",raw,labels["spectral_sample_labels"],metadata=metadata,
                    state="raw-spectral",group="Public spectral fixture")
    write_fcs(DATA / "public_spectral_fixture_converted.fcs",sample)
    processed = Sample("[PUBLIC FIXTURE] Spectral unmixed",raw,labels["spectral_sample_labels"],metadata=dict(metadata),
                       state="raw-spectral",group="Public spectral fixture")
    apply_unmixing(processed,labels["spectral_all_detectors"],components,spectra)
    pd.DataFrame(spectra,index=labels["spectral_all_detectors"],columns=components).to_csv(DATA / "spectral_reference_labeled.csv")
    save_project(Project(name="公开光谱测试 · FlowKit fixture",samples=[sample,processed]),DATA / "公开光谱测试.flowproj")
    print("Prepared public conventional and spectral projects in", DATA)


if __name__ == "__main__":
    main()
