"""Writable caches for the frozen app, including Numba's JIT worker processes."""
import os
from pathlib import Path
import sys

if sys.platform == "darwin":
    cache = Path.home() / "Library/Caches/FlowAnalysis"
elif sys.platform == "win32":
    cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlowAnalysis/Cache"
else:
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "FlowAnalysis"
cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", str(cache / "numba"))
os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
if sys.stdout is None:
    sys.stdout = open(cache / "stdout.log", "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(cache / "stderr.log", "a", encoding="utf-8")
