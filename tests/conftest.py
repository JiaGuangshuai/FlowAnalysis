import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")


@pytest.fixture(scope="session")
def qapp_args():
    return ["FlowAnalysis-tests", "-style", "Fusion"]
