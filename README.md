# FlowAnalysis

English · [简体中文](README.zh-CN.md)

An offline, open-source cytometry desktop application for macOS and Windows with Chinese and English interfaces.

**Version 0.1.0 is a research preview.** See [validation status](docs/VALIDATION.md). Implemented features do not imply numerical equivalence to every FlowJo version, plugin or instrument-specific algorithm.

## Download

[macOS Apple Silicon](https://github.com/JiaGuangshuai/FlowAnalysis/releases/download/v0.1.0/FlowAnalysis-0.1.0-macOS-arm64.zip) · [Windows x64 installer](https://github.com/JiaGuangshuai/FlowAnalysis/releases/download/v0.1.0/FlowAnalysis-0.1.0-Windows-x64-Setup.exe) · [All release files and checksums](https://github.com/JiaGuangshuai/FlowAnalysis/releases/tag/v0.1.0)

Both platform builds passed 29 automated tests and a standalone application check that runs the analysis algorithms in a separate process. The packages include Python; no programming environment is needed.

## Capabilities

- FlowJo WSP / GatingML import with event-by-event conversion checks; unsupported geometry is explicitly frozen to source-sample membership.
- Strict FCS import, metadata, processed population export, portable projects and undo/redo.
- Scatter, density, contour, histogram and overlays; hierarchical rectangle, polygon, ellipse, range, quadrant and Boolean gates.
- Conventional compensation from matrices or gated single-stain controls.
- Raw spectral least-squares unmixing with detector/component mapping, reference controls, optional AF spectrum, background and reconstruction diagnostics.
- Full-population descriptive statistics and CSV/XLSX export; PDF/SVG/PNG layouts.
- UMAP, t-SNE and FlowSOM with saved seeds, transforms, event indices and parameters.
- Exploratory cell-cycle and dye-dilution models, binned kinetics, derived arithmetic parameters and 96/384-well sample mapping.

## Implementation and open-source foundations

FlowAnalysis implements the desktop workflow, project format, gate evaluation, processing safeguards, exploratory cell-cycle/proliferation models and reporting integration. It uses established open-source scientific libraries; it does not use FlowJo's commercial engine.

| Component | Foundation |
|---|---|
| Desktop interface and interactive plots | PySide6 / Qt, PyQtGraph, Matplotlib |
| FCS reading and writing | FlowIO |
| Cytometry transforms and workspace compatibility | FlowUtils and FlowKit |
| Numerical processing | NumPy and SciPy |
| Dimension reduction | umap-learn and scikit-learn t-SNE |
| Self-organizing maps and metaclustering | FlowSOM Python |

## Run from source

Use Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m flowanalysis --demo
```

On Windows, use `.venv\Scripts\python.exe` instead. Remove `--demo` to start an empty project.

The built-in demonstration is synthetic. See [test data](docs/TEST_DATA.md) for public FCS sources.

## Workflow

Import FCS → verify input state → compensate/unmix if appropriate → select channels and transforms → position gate handles and save → select populations for downstream analysis → export statistics/layouts → save the project.

Projects contain imported events, processed data, gate definitions and analysis provenance; moving the original FCS does not break a saved project. Scatter downsampling does not alter full-event gating or statistics.

## Scientific conventions

- Compensation uses source-dye rows and detector columns; spectral references use detector rows and component columns.
- Negative values are retained. Intensity statistics use processed linear data, independently of display transforms.
- Cell cycle uses an explicit exploratory Gaussian G1/G2 plus broadened uniform S model, without debris, doublet or aneuploid components.
- Proliferation uses an undivided control peak, fixed twofold dilution and a shared log2 peak width. Inspect fit residuals and excluded events.
- Spectral results depend on reference controls and instrument compatibility; ordinary least squares is not assumed identical to a vendor's proprietary algorithm.
- FlowSOM event-index gates cannot be transferred to other samples.

## Build and contribute

```bash
python -m pytest
python -m ruff check src tests
python packaging/build.py
```

Build each platform on that operating system. Personal local builds do not require a purchased signing certificate. Public distribution may use platform signing and notarization later.

License: **GPL-3.0-only**. Third-party libraries retain their own notices and licenses. FlowSOM and GPL dependencies are included under compatible GPLv3 distribution terms. Experimental data and credentials are excluded from version control.
