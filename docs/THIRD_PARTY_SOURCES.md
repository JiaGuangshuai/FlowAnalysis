# Third-party source access

FlowAnalysis combines application code with open-source libraries. It does not include FlowJo's proprietary engine. Each library keeps its original copyright and license; the complete application is distributed under GPL-3.0-only.

The `licenses` directory inside a built application contains collected dependency notices and `DEPENDENCIES.json`. The scientific environment is also recorded in saved projects and new analysis results.

## Sources for the 0.1.0 build

| Component | Version | Source |
|---|---|---|
| FlowSOM Python | 0.2.2 | [Source distribution](https://files.pythonhosted.org/packages/5f/b6/4be17631fbe45befc01b27fae24c894528a2ea25ada842c0a112da7f4bfa/flowsom-0.2.2.tar.gz) |
| Python igraph, including its bundled C sources | 1.0.0 | [Source distribution](https://files.pythonhosted.org/packages/23/be/56bef1919005b4caf1f71522b300d359f7faeb7ae93a3b0baa9b4f146a87/igraph-1.0.0.tar.gz) |
| Qt | 6.8.3 | [Official source archive](https://download.qt.io/archive/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz) |
| PySide6 / Shiboken | 6.8.3 | [Official source archive](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz) |
| FlowKit | 1.3.2 | [Upstream repository](https://github.com/whitews/FlowKit) |
| FlowIO | 1.4.0 | [Upstream repository](https://github.com/whitews/FlowIO) |
| FlowUtils | 1.2.2 | [Upstream repository](https://github.com/whitews/FlowUtils) |

The release's `ThirdPartySources` archive contains the FlowSOM and igraph source distributions and their SHA-256 records. The larger Qt and PySide source archives are available directly at the official links above. Other dependencies, exact versions and upstream URLs are listed in `DEPENDENCIES.json`; source distributions can also be obtained from their respective PyPI release pages.

## Modifying or replacing libraries

No application-specific changes are made to these upstream libraries. Qt is bundled as dynamic libraries/frameworks rather than statically linked into application code. To use modified libraries, build and install them into your Python environment, install FlowAnalysis from source, then rerun `python packaging/build.py`. See [build instructions](BUILD.md). A modified macOS app needs to be signed again (ad-hoc signing is supported for local builds).
