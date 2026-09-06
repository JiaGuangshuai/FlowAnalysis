"""Record the concrete software environment with portable scientific results."""
from functools import lru_cache
from importlib.metadata import version
import platform

from flowanalysis import __version__


@lru_cache(maxsize=1)
def software_versions():
    return {"FlowAnalysis": __version__, "Python": platform.python_version(),
            **{name: version(name) for name in ["PySide6", "flowkit", "flowio", "flowutils", "numpy", "scipy",
                                               "scikit-learn", "umap-learn", "flowsom"]}}
