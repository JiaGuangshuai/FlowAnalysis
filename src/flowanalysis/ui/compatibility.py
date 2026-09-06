import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from flowanalysis.core.compatibility import import_gatingml, import_workspace
from .common import TextDialog


def compatibility_dialog(window):
    path,_ = QFileDialog.getOpenFileName(window,window.tr("导入工作区／策略","Import workspace / strategy"),"",
                                         "FlowJo workspace (*.wsp);;GatingML (*.xml)")
    if not path:
        return
    def accept(result):
        samples,report = result
        if samples:
            window.checkpoint("import_compatibility")
            window.project.samples.extend(samples)
            window.sample_id,window.gate_id = samples[0].id,"root"
            window.refresh_tree()
            window.mark_dirty()
        TextDialog(window.tr("兼容性报告","Compatibility report"),json.dumps(report,ensure_ascii=False,indent=2),window).exec()
    if Path(path).suffix.lower() == ".wsp":
        paths = sorted({s.source for s in window.project.samples if s.source and Path(s.source).is_file()})
        if not paths:
            paths,_ = QFileDialog.getOpenFileNames(window,window.tr("选择对应 FCS","Select matching FCS files"),"","FCS (*.fcs *.FCS)")
        if paths:
            window.start_task(import_workspace,(path,paths),accept,window.tr("核对并导入门策略","Validating and importing gating strategy"))
    else:
        sample = window.current_sample()
        if sample is None:
            window.show_error(window.tr("先选择对应 FCS 样本","Select the corresponding FCS sample first"))
            return
        window.start_task(import_gatingml,(path,sample),accept,window.tr("核对并导入 GatingML","Validating and importing GatingML"))
