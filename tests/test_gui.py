from dataclasses import asdict

import pytest
from PySide6.QtWidgets import QInputDialog

from flowanalysis.core.demo import demo_project
from flowanalysis.core.model import Transform
from flowanalysis.ui.window import MainWindow


@pytest.fixture
def window(qtbot):
    window = MainWindow(demo_project(1000),recover=False)
    window.show_error = lambda message,*args:pytest.fail(message)
    window.maybe_save = lambda: True
    qtbot.addWidget(window)
    window.show()
    yield window
    window.dirty = False
    window.tasks.cancel()


def test_seven_workspaces_and_language_switch(window):
    assert window.tabs.count() == 7
    assert len(window.project.samples) == 6
    window.switch_language("en")
    assert window.tabs.tabText(0) == "Analysis"
    window.switch_language("zh")
    assert window.tabs.tabText(0) == "分析工作台"


def test_all_plot_modes_and_gate_handles(window):
    pane = window.plot_pane
    for mode in ["scatter","density","contour","histogram"]:
        pane.mode.setCurrentIndex(pane.mode.findData(mode))
        pane.redraw()
        assert len(pane.plot.listDataItems()) or mode == "density"
    pane.mode.setCurrentIndex(pane.mode.findData("scatter"))
    for kind in ["rectangle","polygon","ellipse","range","quadrant"]:
        pane.begin_roi(kind)
        assert pane.roi is not None


def test_create_gate_then_undo_redo(window,monkeypatch):
    monkeypatch.setattr(QInputDialog,"getText",lambda *args,**kwargs:("New gate",True))
    sample = window.current_sample()
    n = len(sample.gates)
    window.save_gate({"kind":"range","axes":["FSC-A"],"transforms":[asdict(Transform())],
                      "geometry":{"bounds":[[50000,100000]]},"edit_id":None})
    assert len(window.current_sample().gates) == n+1
    window.undo()
    assert len(window.current_sample().gates) == n
    window.redo()
    assert len(window.current_sample().gates) == n+1


def test_layout_and_plate_assignment(window):
    window.add_layout(window.plot_pane.specification())
    window.layout_pane.preview()
    assert window.layout_pane.canvas is not None
    window.plate_pane.table.setCurrentCell(1,2)
    window.plate_pane.assign()
    assert window.current_sample().well == "B03"
