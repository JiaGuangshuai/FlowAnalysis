import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv:
        from flowanalysis.selftest import main as selftest
        index = sys.argv.index("--self-test")
        sys.exit(selftest(sys.argv[index + 1]))
    from PySide6.QtWidgets import QApplication
    from flowanalysis.ui.window import MainWindow
    app = QApplication([*sys.argv, "-style", "Fusion"])
    app.setApplicationName("FlowAnalysis")
    app.setOrganizationName("FlowAnalysis")
    app.setStyle("Fusion")
    project = None
    if "--demo" in sys.argv:
        from flowanalysis.core.demo import demo_project
        project = demo_project()
    project_path = next((x for x in sys.argv[1:] if x.endswith(".flowproj")), None)
    if project_path:
        from flowanalysis.core.io import load_project
        project = load_project(project_path)
    window = MainWindow(project)
    if project_path:
        from pathlib import Path
        window.project_path = Path(project_path)
        window.mark_dirty(False)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
