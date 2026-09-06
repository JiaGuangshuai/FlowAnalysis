"""Deterministic synthetic examples, never presented as biological observations."""
import numpy as np

from .model import Gate, Project, Sample, Transform
from dataclasses import asdict


def demo_project(n=20000):
    rng = np.random.default_rng(42)
    project = Project("Synthetic demonstration / 模拟演示")
    channels = ["FSC-A", "FSC-H", "SSC-A", "CD3", "CD4", "CD8", "Viability", "DNA", "CFSE", "Time"]
    tr = asdict(Transform())
    for i, group in enumerate(["Control", "Treatment"]):
        fsc = rng.normal(80000, 15000, n)
        cd3_positive = rng.random(n) < (.6 + i * .1)
        cd4_positive = rng.random(n) < .6
        cd3 = np.where(cd3_positive, rng.lognormal(8.8, .4, n), rng.normal(50, 60, n))
        cd4 = np.where(cd4_positive & cd3_positive, rng.lognormal(8.3, .4, n), rng.normal(50, 60, n))
        cd8 = np.where(~cd4_positive & cd3_positive, rng.lognormal(8.4, .35, n), rng.normal(50, 60, n))
        phase = rng.choice(3, n, p=[.6, .25, .15])
        dna = np.where(phase == 0, rng.normal(50000, 3000, n),
                       np.where(phase == 1, rng.uniform(50000, 100000, n) + rng.normal(0, 3000, n),
                                rng.normal(100000, 4242.64, n)))
        generation = rng.choice(5, n, p=[.3, .25, .22, .15, .08])
        cfse = 50000 / 2.0**generation * 2**rng.normal(0, .16, n)
        data = np.column_stack([fsc, fsc * .85 + rng.normal(0, 3500, n), rng.normal(40000, 13000, n),
                                cd3, cd4, cd8, rng.lognormal(4, 1, n), dna, cfse, np.linspace(0, 300, n)])
        sample = Sample(f"{group}_01 [SIMULATED]", data, channels, state="compensated", group=group,
                        well=f"A{i+1:02d}", metadata={"synthetic": True, "seed": 42})
        cells = Gate("Cells", "rectangle", ["FSC-A", "SSC-A"], [tr, tr],
                     {"bounds": [[30000, 130000], [0, 90000]]})
        cd3_gate = Gate("CD3+", "range", ["CD3"], [tr], {"bounds": [[1000, None]]}, parent=cells.id)
        sample.gates = [cells, cd3_gate]
        project.samples.append(sample)
    spectra = np.array([[1, .08, .15], [.5, .2, .23], [.08, 1, .3], [.02, .45, .5], [.01, .04, 1]])
    detectors = [f"V{i+1}" for i in range(5)]
    for i, component in enumerate(["Dye_A", "Dye_B", "AF"]):
        amplitude = np.r_[rng.normal(5000, 400, 1000), rng.normal(0, 15, 1000)]
        signal = amplitude[:, None] * spectra[:, i] + rng.normal(0, 8, (2000, 5))
        control = Sample(f"Reference_{component} [SIMULATED]", signal, detectors,
                         state="raw-spectral", group="Spectral controls", metadata={"synthetic": True})
        channel = detectors[int(np.argmax(spectra[:, i]))]
        control.gates = [Gate("Positive", "range", [channel], [tr], {"bounds": [[1000, None]]}),
                         Gate("Negative", "range", [channel], [tr], {"bounds": [[None, 500]]})]
        project.samples.append(control)
    amplitudes = rng.lognormal(7, .7, (n, 3))
    mixed = amplitudes @ spectra.T + rng.normal(0, 12, (n, 5))
    project.samples.append(Sample("Spectral_sample [SIMULATED]", mixed, detectors,
                                  state="raw-spectral", group="Spectral samples",
                                  metadata={"synthetic": True, "demo_spectra": spectra.tolist()}))
    project.record("create_synthetic_demo", seed=42, event_count=n)
    return project
