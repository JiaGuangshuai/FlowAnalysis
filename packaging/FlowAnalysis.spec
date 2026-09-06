from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / "LICENSE"), "."), (str(root / "build/licenses"), "licenses")]
hiddenimports = ["flowanalysis.core.compatibility", "flowanalysis.core.jobs", "flowanalysis.core.advanced",
                 "sklearn.utils._cython_blas", "scipy.special._ufuncs_cxx"]
for package in ["flowkit", "flowio", "flowutils", "flowsom", "umap", "pynndescent", "scanpy"]:
    datas += collect_data_files(package, include_py_files=True)
for package in ["flowkit", "flowsom", "umap-learn", "scanpy", "anndata", "scverse-misc", "fast-array-utils"]:
    datas += copy_metadata(package, recursive=True)
hiddenimports += collect_submodules("flowsom")
hiddenimports += collect_submodules("umap", filter=lambda name: "parametric" not in name)
hiddenimports += collect_submodules("pyqtgraph.graphicsItems")

a = Analysis([str(root / "src/flowanalysis/__main__.py")], pathex=[str(root / "src")],
             binaries=[], datas=datas, hiddenimports=hiddenimports,
             hookspath=[], runtime_hooks=[str(root / "packaging/runtime_hook.py")],
             excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "notebook", "pytest"],
             hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg"]}}, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FlowAnalysis", console=False,
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FlowAnalysis")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="FlowAnalysis.app", bundle_identifier="org.flowanalysis.desktop",
                 info_plist={"CFBundleShortVersionString": "0.1.0", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "13.0"})
