from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTabWidget,
    QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from flowanalysis import __version__
from flowanalysis.core.demo import demo_project
from flowanalysis.core.gating import copy_strategy, masks, statistics
from flowanalysis.core.io import json_clean, load_project, save_project, write_fcs
from flowanalysis.core.jobs import import_files, process_sample
from flowanalysis.core.model import Gate, Project
from flowanalysis.core.processing import derived_parameter
from .advanced import AdvancedPane
from .common import FormDialog, TextDialog, combo
from .plot import PlotPane
from .processing import ProcessingPane
from .reports import LayoutPane, PlatePane, StatisticsPane
from .tasks import TaskManager


class MainWindow(QMainWindow):
    def __init__(self,project=None,recover=True,settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("FlowAnalysis","FlowAnalysis")
        self.language = self.settings.value("language","zh")
        self.project = project or Project()
        self.project_path = None
        self.sample_id = self.project.samples[0].id if self.project.samples else None
        self.gate_id = "root"
        self.dirty = bool(project)
        self.undo_stack,self.redo_stack = [],[]
        self.tasks = TaskManager(self)
        self.tasks.finished.connect(self.task_finished)
        self.tasks.failed.connect(self.task_failed)
        self.tasks.busyChanged.connect(self.busy_changed)
        self.task_callback = None
        self.resize(1500,980)
        self.setMinimumSize(1050,700)
        self.setAcceptDrops(True)
        self.build_ui()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(180000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        if recover and not project:
            QTimer.singleShot(200,self.offer_recovery)

    def tr(self,zh,en=None):
        return zh if self.language == "zh" or en is None else en

    def build_ui(self):
        self.menuBar().clear()
        for bar in self.findChildren(QToolBar):
            self.removeToolBar(bar)
            bar.deleteLater()
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f7f9fb; color: #203040; font-size: 13px; }
            QToolBar { spacing: 8px; padding: 8px; background: #eef3f6; border: 0; }
            QTreeWidget, QTableWidget, QListWidget, QPlainTextEdit { background: white; alternate-background-color: #f3f7fa; border: 1px solid #dae2e9; }
            QHeaderView::section { background: #edf2f6; padding: 7px; border: 0; }
            QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #ced9e2; border-radius: 5px; padding: 6px; }
            QPushButton:hover { background: #e3f1f2; }
            QPushButton:disabled { color: #8e9ba8; background: #f3f4f5; }
            QPushButton#primaryAction { background: #146f79; color: white; padding: 9px; }
            QTabWidget::pane { border: 1px solid #dce4eb; }
            QTabBar::tab { background: #edf2f6; padding: 11px 15px; }
            QTabBar::tab:selected { background: white; color: #146f79; border-bottom: 2px solid #146f79; }
            QTreeWidget::item { padding: 5px; }
            QTreeWidget::item:selected { background: #dceff0; color: #164e57; }
            QSplitter::handle { background: #dce4eb; }
        """)
        file_menu = self.menuBar().addMenu(self.tr("文件","File"))
        edit_menu = self.menuBar().addMenu(self.tr("编辑","Edit"))
        analysis_menu = self.menuBar().addMenu(self.tr("分析","Analysis"))
        help_menu = self.menuBar().addMenu(self.tr("帮助","Help"))
        self.actions = {}
        def action(menu,key,zh,en,callback,shortcut=None):
            a = QAction(self.tr(zh,en),self)
            a.triggered.connect(callback)
            if shortcut:
                a.setShortcut(shortcut)
            menu.addAction(a)
            self.actions[key] = a
            return a
        action(file_menu,"new","新建项目","New project",self.new_project,QKeySequence.StandardKey.New)
        action(file_menu,"open","打开项目","Open project",self.open_project,QKeySequence.StandardKey.Open)
        action(file_menu,"import","导入 FCS","Import FCS",self.import_dialog,"Ctrl+I")
        action(file_menu,"demo","打开模拟演示","Open synthetic demo",self.open_demo)
        action(file_menu,"save","保存项目","Save project",self.save,QKeySequence.StandardKey.Save)
        action(file_menu,"save_as","项目另存为","Save project as",lambda:self.save(True),QKeySequence.StandardKey.SaveAs)
        action(file_menu,"export_fcs","导出当前群体 FCS","Export population FCS",self.export_fcs)
        action(file_menu,"export_plot","导出当前图形","Export current plot",self.export_plot)
        action(file_menu,"template_export","导出门模板","Export gate template",self.export_template)
        action(file_menu,"template_import","导入门模板","Import gate template",self.import_template)
        action(file_menu,"compat","导入 FlowJo / GatingML","Import FlowJo / GatingML",self.import_compatibility)
        action(edit_menu,"undo","撤销","Undo",self.undo,QKeySequence.StandardKey.Undo)
        action(edit_menu,"redo","重做","Redo",self.redo,QKeySequence.StandardKey.Redo)
        action(edit_menu,"rename","重命名","Rename",self.rename_current,"F2")
        action(edit_menu,"remove","移除所选门或样本","Remove selected gate or sample",self.remove_current)
        action(analysis_menu,"boolean","布尔门","Boolean gate",self.boolean_gate)
        action(analysis_menu,"definition","编辑门定义","Edit gate definition",self.edit_gate_definition)
        action(analysis_menu,"apply_template","将门策略应用到样本组","Apply strategy to sample group",self.apply_template)
        action(analysis_menu,"derived","派生参数","Derived parameter",self.derived_dialog)
        action(analysis_menu,"group","更改样本组","Change sample group",self.change_group)
        action(analysis_menu,"raw","恢复导入数据","Restore imported data",self.restore_raw)
        action(analysis_menu,"metadata","元数据与处理记录","Metadata and provenance",self.show_metadata)
        action(help_menu,"guide","快速指南","Quick guide",self.quick_guide)
        action(help_menu,"about","关于与版本","About and versions",self.about)
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        for key in ["import","open","save","undo","redo","demo"]:
            toolbar.addAction(self.actions[key])
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        language = combo([("简体中文","zh"),("English","en")],self.language)
        language.currentIndexChanged.connect(lambda:self.switch_language(language.currentData()))
        toolbar.addWidget(language)
        self.splitter = QSplitter()
        self.setCentralWidget(self.splitter)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel(self.tr("样本与门控层级","Samples & gating hierarchy")))
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("查找样本","Find samples"))
        self.search.textChanged.connect(self.filter_tree)
        left_layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("群体","Population"),self.tr("事件数","Events")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.itemSelectionChanged.connect(self.overlay_changed)
        self.tree.setColumnWidth(0,180)
        left_layout.addWidget(self.tree,1)
        left_layout.addWidget(QLabel(self.tr("多选样本可叠加直方图。","Multi-select samples for histogram overlays.")))
        self.splitter.addWidget(left)
        self.tabs = QTabWidget()
        self.plot_pane = PlotPane(self.tr)
        self.plot_pane.gateReady.connect(self.save_gate)
        self.plot_pane.layoutReady.connect(self.add_layout)
        self.plot_pane.error.connect(lambda error:self.statusBar().showMessage(error))
        self.compensation = ProcessingPane(self)
        self.spectral = ProcessingPane(self,spectral=True)
        self.advanced = AdvancedPane(self)
        self.statistics = StatisticsPane(self)
        self.layout_pane = LayoutPane(self)
        self.plate_pane = PlatePane(self)
        for widget,zh,en in [(self.plot_pane,"分析工作台","Analysis"),(self.compensation,"补偿","Compensation"),
                             (self.spectral,"光谱解混","Unmixing"),(self.advanced,"进阶分析","Advanced"),
                             (self.statistics,"统计表","Statistics"),(self.layout_pane,"图版","Layout"),
                             (self.plate_pane,"板布局","Plates")]:
            self.tabs.addTab(widget,self.tr(zh,en))
        self.tabs.currentChanged.connect(self.tab_changed)
        self.splitter.addWidget(self.tabs)
        inspector = QWidget()
        info_layout = QVBoxLayout(inspector)
        info_layout.addWidget(QLabel(self.tr("群体详情","Population details")))
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.details)
        info_layout.addWidget(QLabel(self.tr("导入数据状态","Imported data state")))
        self.state_control = combo([(self.tr("未知／待确认","Unknown / verify"),"unknown"),
                                    (self.tr("原始常规","Raw conventional"),"raw-conventional"),
                                    (self.tr("已补偿","Compensated"),"compensated"),
                                    (self.tr("原始光谱","Raw spectral"),"raw-spectral"),
                                    (self.tr("已解混","Unmixed"),"unmixed")])
        info_layout.addWidget(self.state_control)
        state_button = QPushButton(self.tr("确认数据状态","Set data state"))
        state_button.clicked.connect(self.set_data_state)
        info_layout.addWidget(state_button)
        note = QLabel(self.tr("补偿/解混后结果保存为新数据层。原始事件保留。均值与中位数分别报告。","Processing creates a new data layer. Imported events are retained. Mean and median are separate statistics."))
        note.setWordWrap(True)
        info_layout.addWidget(note)
        info_layout.addStretch()
        metadata = QPushButton(self.tr("查看处理记录","View provenance"))
        metadata.clicked.connect(self.show_metadata)
        info_layout.addWidget(metadata)
        self.splitter.addWidget(inspector)
        self.splitter.setSizes([270,1000,230])
        status = self.statusBar()
        for widget in getattr(self,"status_widgets",[]):
            status.removeWidget(widget)
            widget.deleteLater()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(150)
        self.progress.setRange(0,0)
        self.progress.hide()
        self.cancel_button = QPushButton(self.tr("取消任务","Cancel task"))
        self.cancel_button.clicked.connect(self.cancel_task)
        self.cancel_button.hide()
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.cancel_button)
        self.status_widgets = [self.progress,self.cancel_button]
        self.refresh_tree()
        self.mark_dirty(self.dirty)

    def switch_language(self,language):
        self.language = language
        self.settings.setValue("language",language)
        self.build_ui()

    def current_sample(self):
        return next((s for s in self.project.samples if s.id == self.sample_id),None)

    def checkpoint(self,action):
        memo = {}
        for sample in self.project.samples:
            memo[id(sample.raw)] = sample.raw
            memo[id(sample.data)] = sample.data
        self.undo_stack.append(deepcopy(self.project,memo))
        self.undo_stack = self.undo_stack[-20:]
        self.redo_stack.clear()
        self.project.record(action,sample_id=self.sample_id,gate_id=self.gate_id)

    def mark_dirty(self,value=True):
        self.dirty = value
        self.setWindowTitle(f"FlowAnalysis {__version__} · {self.project.name}" + (" *" if value else ""))
        self.actions["undo"].setEnabled(bool(self.undo_stack) and not self.tasks.busy)
        self.actions["redo"].setEnabled(bool(self.redo_stack) and not self.tasks.busy)

    def undo(self):
        if self.undo_stack and not self.tasks.busy:
            self.redo_stack.append(self.project)
            self.project = self.undo_stack.pop()
            self.refresh_tree()
            self.mark_dirty()

    def redo(self):
        if self.redo_stack and not self.tasks.busy:
            self.undo_stack.append(self.project)
            self.project = self.redo_stack.pop()
            self.refresh_tree()
            self.mark_dirty()

    def refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        selected = None
        for sample in self.project.samples:
            if sample.group not in groups:
                groups[sample.group] = QTreeWidgetItem(self.tree,[sample.group])
                groups[sample.group].setFlags(groups[sample.group].flags() & ~Qt.ItemFlag.ItemIsSelectable)
            root = QTreeWidgetItem(groups[sample.group],[sample.name,f"{len(sample.data):,}"])
            root.setData(0,Qt.ItemDataRole.UserRole,(sample.id,"root"))
            nodes = {"root":root}
            try:
                membership = masks(sample)
            except Exception as error:
                membership = {}
                root.setToolTip(0,str(error))
            pending = list(sample.gates)
            while pending:
                added = False
                for gate in pending[:]:
                    if gate.parent not in nodes:
                        continue
                    value = f"{int(membership[gate.id].sum()):,}" if gate.id in membership else "!"
                    item = QTreeWidgetItem(nodes[gate.parent],[gate.name,value])
                    item.setData(0,Qt.ItemDataRole.UserRole,(sample.id,gate.id))
                    nodes[gate.id] = item
                    pending.remove(gate)
                    added = True
                if not added:
                    break
            if sample.id == self.sample_id:
                selected = nodes.get(self.gate_id,root)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        if selected is None and self.project.samples:
            self.sample_id,self.gate_id = self.project.samples[0].id,"root"
            selected = self.tree.topLevelItem(0).child(0)
        if selected:
            self.tree.setCurrentItem(selected)
        else:
            self.sample_id,self.gate_id = None,"root"
            self.selection_changed(None,None)
        self.layout_pane.refresh()
        self.plate_pane.refresh()

    def selection_changed(self,current,previous):
        data = current.data(0,Qt.ItemDataRole.UserRole) if current else None
        if data:
            self.sample_id,self.gate_id = data
        sample = self.current_sample()
        self.plot_pane.set_sample(sample,self.gate_id,self.selected_samples())
        self.compensation.set_sample(sample)
        self.spectral.set_sample(sample)
        self.advanced.set_sample(sample)
        self.update_details()
        self.tab_changed(self.tabs.currentIndex())

    def selected_samples(self):
        ids = {item.data(0,Qt.ItemDataRole.UserRole)[0] for item in self.tree.selectedItems()
               if item.data(0,Qt.ItemDataRole.UserRole)}
        return [s for s in self.project.samples if s.id in ids]

    def overlay_changed(self):
        self.plot_pane.overlays = self.selected_samples()
        if self.plot_pane.mode.currentData() == "histogram":
            self.plot_pane.redraw()

    def filter_tree(self,text):
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                item = group.child(j)
                item.setHidden(text.lower() not in item.text(0).lower())

    def update_details(self):
        sample = self.current_sample()
        if not sample:
            self.details.setText(self.tr("尚未选择样本","No sample selected"))
            return
        try:
            row = next(r for r in statistics(sample) if r["gate_id"] == self.gate_id)
            parent = "NA" if row["percent_parent"] is None else f'{row["percent_parent"]:.3f}%'
            total = "NA" if row["percent_total"] is None else f'{row["percent_total"]:.3f}%'
            self.details.setText(self.tr(
                f'{row["gate"]}\n\n事件数：{row["events"]:,}\n占父群体：{parent}\n占总事件：{total}\n\n通道数：{len(sample.channels)}\n样本组：{sample.group}\n孔位：{sample.well or "—"}',
                f'{row["gate"]}\n\nEvents: {row["events"]:,}\n% parent: {parent}\n% total: {total}\n\nChannels: {len(sample.channels)}\nGroup: {sample.group}\nWell: {sample.well or "—"}'))
            self.state_control.setCurrentIndex(self.state_control.findData(sample.state))
        except Exception as error:
            self.details.setText(str(error))

    def tab_changed(self,index):
        if self.tabs.widget(index) is self.statistics:
            self.statistics.refresh()
        elif self.tabs.widget(index) is self.plate_pane:
            self.plate_pane.refresh()

    def start_task(self,function,args,callback,label):
        if self.tasks.busy:
            self.show_error(self.tr("另一个任务正在运行","Another task is running"))
            return
        self.task_callback = callback
        self.statusBar().showMessage(label)
        try:
            self.tasks.start(function,*args)
        except Exception as error:
            self.task_callback = None
            self.tasks.cleanup()
            self.show_error(str(error))

    def task_finished(self,result):
        callback,self.task_callback = self.task_callback,None
        try:
            if callback:
                callback(result)
            self.statusBar().showMessage(self.tr("任务完成","Task complete"),10000)
        except Exception as error:
            self.show_error(str(error))

    def task_failed(self,message,details):
        self.task_callback = None
        self.show_error(message,details)

    def busy_changed(self,busy):
        self.splitter.setEnabled(not busy)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setEnabled(not busy)
        self.menuBar().setEnabled(not busy)
        self.progress.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.mark_dirty(self.dirty)

    def cancel_task(self):
        self.tasks.cancel()
        self.task_callback = None
        self.statusBar().showMessage(self.tr("任务已取消；现有数据未改变","Task cancelled; existing data unchanged"))

    def show_error(self,message,details=""):
        dialog = QMessageBox(QMessageBox.Icon.Warning,self.tr("无法完成操作","Unable to complete operation"),message,parent=self)
        if details:
            dialog.setDetailedText(details)
        dialog.exec()

    def maybe_save(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self,self.tr("保存项目","Save project"),
                    self.tr("当前项目有未保存修改，是否保存？","Save changes to the current project?"),
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def new_project(self):
        if self.maybe_save():
            self.project = Project()
            self.project_path = None
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.refresh_tree()
            self.mark_dirty(False)

    def open_demo(self):
        if self.maybe_save():
            self.start_task(demo_project,(),self.accept_demo,self.tr("生成模拟演示","Generating synthetic demo"))

    def accept_demo(self,project):
        self.project = project
        self.project_path = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.refresh_tree()
        self.mark_dirty()

    def open_project(self):
        if not self.maybe_save():
            return
        path,_ = QFileDialog.getOpenFileName(self,self.tr("打开项目","Open project"),"","FlowAnalysis (*.flowproj *.autosave)")
        if path:
            def accept(project):
                self.accept_demo(project)
                self.project_path = path
                self.mark_dirty(False)
            self.start_task(load_project,(path,),accept,self.tr("打开项目中","Opening project"))

    def save(self,save_as=False):
        path = None if save_as else self.project_path
        if not path:
            path,_ = QFileDialog.getSaveFileName(self,self.tr("保存项目","Save project"),
                                                 self.project.name+".flowproj","FlowAnalysis (*.flowproj)")
        if not path:
            return False
        if not str(path).endswith(".flowproj"):
            path += ".flowproj"
        try:
            save_project(self.project,path)
            self.project_path = path
            self.mark_dirty(False)
            return True
        except Exception as error:
            self.show_error(str(error))
            return False

    def import_dialog(self):
        paths,_ = QFileDialog.getOpenFileNames(self,self.tr("导入 FCS","Import FCS"),"","FCS (*.fcs *.FCS)")
        if paths:
            self.import_paths(paths)

    def import_paths(self,paths):
        self.start_task(import_files,(paths,),self.accept_import,self.tr("读取 FCS 中","Reading FCS files"))

    def accept_import(self,result):
        samples,errors = result
        if samples:
            self.checkpoint("import_fcs")
            self.project.samples.extend(samples)
            self.sample_id,self.gate_id = samples[0].id,"root"
            self.refresh_tree()
            self.mark_dirty()
        if errors:
            TextDialog(self.tr("导入报告","Import report"),json.dumps(errors,ensure_ascii=False,indent=2),self).exec()

    def save_gate(self,definition):
        sample = self.current_sample()
        if not sample:
            return
        edit_id = definition.pop("edit_id",None)
        old = next((g for g in sample.gates if g.id == edit_id),None)
        name,ok = QInputDialog.getText(self,self.tr("保存门","Save gate"),self.tr("群体名称","Population name"),
                                       text=old.name if old else definition["kind"])
        if not ok or not name.strip():
            return
        before = deepcopy(sample.gates)
        self.checkpoint("save_gate")
        try:
            if old:
                replacement = Gate(name.strip(),parent=old.parent,id=old.id,**definition)
                sample.gates[sample.gates.index(old)] = replacement
                self.gate_id = old.id
            elif definition["kind"] == "quadrant":
                for label,positive in [("++",[True,True]),("+-",[True,False]),("-+",[False,True]),("--",[False,False])]:
                    d = deepcopy(definition)
                    d["geometry"]["positive"] = positive
                    sample.gates.append(Gate(name.strip()+" "+label,parent=self.gate_id,**d))
            else:
                sample.gates.append(Gate(name.strip(),parent=self.gate_id,**definition))
            masks(sample)
            sample.revision += 1
            sample.results = []
            self.refresh_tree()
            self.mark_dirty()
        except Exception as error:
            sample.gates = before
            self.show_error(str(error))

    def boolean_gate(self):
        sample = self.current_sample()
        if not sample or not sample.gates:
            return
        dialog = FormDialog(self.tr("布尔门","Boolean gate"),self,
                            self.tr("NOT 相对于当前父群体求补；NOT 只能选择一个门。","NOT is relative to the selected parent population and takes one gate."))
        name = dialog.add(self.tr("名称","Name"),QLineEdit("Boolean"))
        operation = dialog.add(self.tr("运算","Operation"),combo([(v,v) for v in ["AND","OR","NOT"]]))
        selection = QListWidget()
        for gate in sample.gates:
            item = QListWidgetItem(gate.name)
            item.setData(Qt.ItemDataRole.UserRole,gate.id)
            item.setCheckState(Qt.CheckState.Unchecked)
            selection.addItem(item)
        dialog.extra.insertWidget(1,selection)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            refs = [selection.item(i).data(Qt.ItemDataRole.UserRole) for i in range(selection.count())
                    if selection.item(i).checkState() == Qt.CheckState.Checked]
            if not refs or (operation.currentData() == "NOT" and len(refs) != 1):
                self.show_error(self.tr("所选门数量不适合此运算","Invalid number of gate operands"))
                return
            self.checkpoint("boolean_gate")
            sample.gates.append(Gate(name.text() or "Boolean","boolean",parent=self.gate_id,
                                     geometry={"refs":refs,"op":operation.currentData()}))
            sample.revision += 1
            sample.results = []
            self.refresh_tree()
            self.mark_dirty()

    def edit_gate_definition(self):
        sample = self.current_sample()
        gate = next((g for g in sample.gates if g.id == self.gate_id),None) if sample else None
        if gate is None:
            return
        dialog = FormDialog(self.tr("编辑门定义","Edit gate definition"),self,
                            self.tr("高级编辑：null 表示无界；变换和坐标必须匹配。","Advanced editor: null means unbounded. Coordinates and transform must agree."))
        editor = QPlainTextEdit(json.dumps(gate.to_dict(),ensure_ascii=False,indent=2))
        dialog.extra.insertWidget(1,editor)
        dialog.resize(650,700)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                replacement = Gate(**json.loads(editor.toPlainText()))
                replacement.id = gate.id
                trial = deepcopy(sample.gates)
                trial[sample.gates.index(gate)] = replacement
                original = sample.gates
                sample.gates = trial
                try:
                    masks(sample)
                finally:
                    sample.gates = original
                self.checkpoint("edit_gate_definition")
                sample.gates = trial
                sample.revision += 1
                sample.results = []
                self.refresh_tree()
                self.mark_dirty()
            except Exception as error:
                self.show_error(str(error))

    def rename_current(self):
        sample = self.current_sample()
        if not sample:
            return
        target = sample if self.gate_id == "root" else next(g for g in sample.gates if g.id == self.gate_id)
        name,ok = QInputDialog.getText(self,self.tr("重命名","Rename"),self.tr("名称","Name"),text=target.name)
        if ok and name.strip():
            self.checkpoint("rename")
            target.name = name.strip()
            self.refresh_tree()
            self.mark_dirty()

    def remove_current(self):
        sample = self.current_sample()
        if not sample:
            return
        self.checkpoint("remove")
        if self.gate_id == "root":
            self.project.samples.remove(sample)
            self.project.layouts = [s for s in self.project.layouts if s["sample_id"] != sample.id]
            self.sample_id = None
        else:
            invalid = {self.gate_id}
            while True:
                old = len(invalid)
                invalid |= {g.id for g in sample.gates if g.parent in invalid or set(g.geometry.get("refs",[])) & invalid}
                if old == len(invalid):
                    break
            sample.gates = [g for g in sample.gates if g.id not in invalid]
            self.project.layouts = [s for s in self.project.layouts if not(s["sample_id"] == sample.id and s["gate_id"] in invalid)]
            sample.revision += 1
            sample.results = []
        self.gate_id = "root"
        self.refresh_tree()
        self.mark_dirty()

    def change_group(self):
        sample = self.current_sample()
        if sample:
            name,ok = QInputDialog.getText(self,self.tr("样本组","Sample group"),self.tr("组名","Group name"),text=sample.group)
            if ok and name.strip():
                self.checkpoint("change_group")
                for item in self.selected_samples() or [sample]:
                    item.group = name.strip()
                self.refresh_tree()
                self.mark_dirty()

    def apply_template(self):
        sample = self.current_sample()
        if not sample:
            return
        groups = sorted({s.group for s in self.project.samples if s.id != sample.id})
        group,ok = QInputDialog.getItem(self,self.tr("应用门策略","Apply gating strategy"),self.tr("目标样本组（替换该组门策略，可撤销）","Target group (replaces gates; undo available)"),groups,editable=False)
        if not ok:
            return
        try:
            targets = [s for s in self.project.samples if s.group == group and s.id != sample.id]
            # Validate every destination before changing any one of them.
            for target in targets:
                copy_strategy(sample,__import__("copy").copy(target))
            self.checkpoint("apply_gate_template")
            for target in targets:
                copy_strategy(sample,target)
                self.project.layouts = [s for s in self.project.layouts if s["sample_id"] != target.id]
            self.refresh_tree()
            self.mark_dirty()
        except Exception as error:
            self.show_error(str(error))

    def derived_dialog(self):
        sample = self.current_sample()
        if not sample:
            return
        dialog = FormDialog(self.tr("派生参数","Derived parameter"),self,
                            self.tr("支持 + − * / **、log10、log2、sqrt、abs、arcsinh、exp、minimum、maximum。非法数值会被拒绝。",
                                    "Supports arithmetic, log10/log2/sqrt/abs/arcsinh/exp/minimum/maximum. Non-finite values are rejected."))
        name = dialog.add(self.tr("新通道名","New channel"),QLineEdit("Ratio"))
        expression = dialog.add(self.tr("表达式","Expression"),QLineEdit("c0 / c1"))
        aliases = QPlainTextEdit("\n".join(f"c{i} = {sample.label(c)}" for i,c in enumerate(sample.channels)))
        aliases.setReadOnly(True)
        dialog.extra.insertWidget(1,aliases)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                label = name.text().strip()
                if not label or label in sample.channels:
                    raise ValueError(self.tr("通道名称不能为空或重复","Channel name must be nonempty and unique"))
                columns = {f"c{i}":sample.data[:,i] for i in range(len(sample.channels))}
                values = derived_parameter(expression.text(),columns)
                self.checkpoint("derived_parameter")
                sample.replace_data(np.column_stack([sample.data,values]),sample.channels+[label],
                                    {"method":"derived_parameter","expression":expression.text(),"aliases":dict(enumerate(sample.channels))},sample.state)
                self.refresh_tree()
                self.mark_dirty()
            except Exception as error:
                self.show_error(str(error))

    def set_data_state(self):
        sample = self.current_sample()
        if sample:
            if sample.processing:
                self.show_error(self.tr("此样本已有处理记录；如需重新处理，请先恢复导入数据。","This sample has processing history; restore imported data before relabeling its state."))
                return
            self.checkpoint("set_data_state")
            sample.state = self.state_control.currentData()
            sample.metadata["declared_import_state"] = sample.state
            self.mark_dirty()
            self.update_details()

    def restore_raw(self):
        sample = self.current_sample()
        if sample:
            self.checkpoint("restore_imported_data")
            sample.data = sample.raw
            sample.channels = list(sample.raw_channels)
            sample.markers = list(sample.raw_markers)
            sample.metadata.setdefault("archived_processing",[]).append(deepcopy(sample.processing))
            sample.metadata.setdefault("archived_gates",[]).append([g.to_dict() for g in sample.gates])
            sample.processing = []
            sample.gates = []
            self.project.layouts = [s for s in self.project.layouts if s["sample_id"] != sample.id]
            sample.results = []
            sample.state = sample.metadata.get("declared_import_state",sample.metadata.get("flowanalysis_state","unknown"))
            sample.revision += 1
            self.gate_id = "root"
            self.refresh_tree()
            self.mark_dirty()

    def process_current(self,mode,channels,matrix,components=None,background=None,provenance=None):
        sample = self.current_sample()
        if sample is None:
            return
        if sample.state == "unknown":
            self.show_error(self.tr("请先在右侧确认这是原始常规或原始光谱数据，避免重复处理。","Confirm raw conventional or raw spectral state in the right panel first, to avoid duplicate processing."))
            return
        def accept(result):
            self.checkpoint("apply_"+mode)
            index = next(i for i,s in enumerate(self.project.samples) if s.id == result.id)
            self.project.samples[index] = result
            valid_gates = {"root", *(g.id for g in result.gates)}
            self.project.layouts = [s for s in self.project.layouts if s["sample_id"] != result.id or s["gate_id"] in valid_gates]
            self.gate_id = "root"
            self.refresh_tree()
            self.mark_dirty()
            if mode == "spectral":
                TextDialog(self.tr("解混质量检查","Unmixing diagnostics"),json.dumps(json_clean(result.processing[-1]["qc"]),indent=2),self).exec()
        self.start_task(process_sample,(sample,mode,channels,matrix,components,background,provenance),accept,
                         self.tr("补偿／解混计算中","Computing compensation/unmixing"))

    def add_layout(self,spec):
        self.checkpoint("add_layout_plot")
        self.project.layouts.append(deepcopy(spec))
        self.layout_pane.refresh()
        self.mark_dirty()
        self.statusBar().showMessage(self.tr("已加入图版","Added to layout"),5000)

    def export_plot(self):
        if self.current_sample():
            from .reports import _export_layout_job
            path,_ = QFileDialog.getSaveFileName(self,self.tr("导出图形","Export plot"),"plot.pdf","PDF (*.pdf);;SVG (*.svg);;PNG (*.png)")
            if path:
                self.start_task(_export_layout_job,(self.project,[self.plot_pane.specification()],path,1),lambda _:None,self.tr("导出图形","Exporting plot"))

    def export_fcs(self):
        sample = self.current_sample()
        if sample:
            path,_ = QFileDialog.getSaveFileName(self,self.tr("导出群体","Export population"),sample.name+".fcs","FCS (*.fcs)")
            if path:
                try:
                    mask = masks(sample)[self.gate_id]
                    self.start_task(write_fcs,(path,sample,mask),lambda _:None,self.tr("导出 FCS","Exporting FCS"))
                except Exception as error:
                    self.show_error(str(error))

    def export_template(self):
        sample = self.current_sample()
        if sample:
            path,_ = QFileDialog.getSaveFileName(self,self.tr("导出门模板","Export gate template"),"gates.json","JSON (*.json)")
            if path:
                try:
                    if any(g.kind == "indices" for g in sample.gates):
                        raise ValueError("Event-index gates cannot be exported as transferable templates")
                    Path(path).write_text(json.dumps({"schema":1,"gates":[g.to_dict() for g in sample.gates]},
                                                     ensure_ascii=False,indent=2),encoding="utf-8")
                except Exception as error:
                    self.show_error(str(error))

    def import_template(self):
        sample = self.current_sample()
        if sample:
            path,_ = QFileDialog.getOpenFileName(self,self.tr("导入门模板","Import gate template"),"","JSON (*.json)")
            if path:
                try:
                    value = json.loads(Path(path).read_text(encoding="utf-8"))
                    if value.get("schema") != 1:
                        raise ValueError("Unsupported gate template version")
                    gates = [Gate(**g) for g in value["gates"]]
                    original = sample.gates
                    sample.gates = gates
                    try:
                        masks(sample)
                    finally:
                        sample.gates = original
                    self.checkpoint("import_gate_template")
                    sample.gates = gates
                    sample.revision += 1
                    sample.results = []
                    self.gate_id = "root"
                    self.refresh_tree()
                    self.mark_dirty()
                except Exception as error:
                    self.show_error(str(error))

    def create_cluster_gates(self,result):
        sample = self.project.sample(result["sample_id"])
        if sample.revision != result["sample_revision"]:
            self.show_error(self.tr("聚类结果已过期，请重新运行","Clustering result is stale; rerun the analysis"))
            return
        self.checkpoint("create_cluster_gates")
        labels,ids = np.asarray(result["labels"]),np.asarray(result["event_indices"])
        for label in np.unique(labels):
            sample.gates.append(Gate(f"FlowSOM {label}","indices",parent=result["gate_id"],
                                     geometry={"indices":ids[labels == label].tolist(),"source":"FlowSOM"}))
        sample.revision += 1
        self.refresh_tree()
        self.mark_dirty()

    def show_metadata(self):
        sample = self.current_sample()
        if sample:
            value = {"metadata":sample.metadata,"processing":sample.processing,
                     "gates":[g.to_dict() for g in sample.gates],"results":[{k:v for k,v in r.items()
                     if k not in {"coordinates","labels","event_indices","som_nodes","components","rows"}} for r in sample.results]}
            TextDialog(self.tr("元数据与处理记录","Metadata & provenance"),json.dumps(json_clean(value),ensure_ascii=False,indent=2),self).exec()

    def quick_guide(self):
        text = self.tr(
            "1. 导入 FCS，或打开“模拟演示”。\n2. 在右侧确认数据状态；按需要进行补偿或光谱解混。\n3. 选择 X/Y 通道与变换；点击门工具，拖动边界后保存。\n4. 在左侧选择群体继续建子门；勾选“编辑所选门”可调整已有门。\n5. 进阶分析页选择通道、方法与参数后运行；长任务可取消。\n6. 统计页导出全部样本；工作台“加入图版”可组合输出。\n7. 保存为 .flowproj，包含事件、门和处理记录，可在另一台电脑打开。\n\n所有演示数据均为合成。细胞周期和增殖采用明确记录的独立探索模型，需检查拟合残差。\n原始光谱解混需匹配仪器通道、单染与未染对照。\nFlowSOM 的事件索引门仅适用于原样本，不能跨样本套用。",
            "1. Import FCS or open Synthetic demo.\n2. Confirm data state; compensate or unmix as appropriate.\n3. Select axes and transforms; choose a gate tool, drag handles and save.\n4. Select populations to build children; use Edit selected gate to adjust.\n5. Choose channels and parameters in Advanced, then run; long tasks are cancellable.\n6. Export all statistics or add workspace plots to a layout.\n7. Save .flowproj including events, gates and provenance for portable reopening.\n\nDemo data are synthetic. Cell-cycle and proliferation use documented exploratory models; inspect residuals.\nRaw spectral unmixing requires matching detector metadata and reference controls.\nFlowSOM index gates are specific to their source sample.")
        TextDialog(self.tr("快速指南","Quick guide"),text,self).exec()

    def about(self):
        import importlib.metadata
        versions = {name:importlib.metadata.version(name) for name in ["PySide6","flowkit","flowio","flowutils","numpy","scipy","umap-learn","flowsom"]}
        TextDialog(self.tr("关于","About"),"FlowAnalysis "+__version__+"\nGPL-3.0-only\n\n"+json.dumps(versions,indent=2),self).exec()

    def import_compatibility(self):
        from .compatibility import compatibility_dialog
        compatibility_dialog(self)

    def autosave_path(self):
        directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        directory.mkdir(parents=True,exist_ok=True)
        return directory/"recovery.autosave"

    def autosave(self):
        if self.dirty and self.project.samples and not self.tasks.busy:
            self.start_task(save_project,(self.project,str(self.autosave_path())),lambda _:None,
                             self.tr("自动保存恢复副本","Autosaving recovery copy"))

    def offer_recovery(self):
        path = self.autosave_path()
        if path.exists():
            answer = QMessageBox.question(self,self.tr("恢复项目","Recover project"),
                                           self.tr("发现自动保存副本，是否恢复？","An autosaved project exists. Recover it?"))
            if answer == QMessageBox.StandardButton.Yes:
                self.start_task(load_project,(str(path),),self.accept_demo,self.tr("恢复项目中","Recovering project"))

    def closeEvent(self,event):
        if self.tasks.busy:
            answer = QMessageBox.question(self,self.tr("任务正在运行","Task running"),
                                           self.tr("取消任务并退出？","Cancel the running task and close?"))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_task()
        if self.maybe_save():
            self.tasks.cancel()
            event.accept()
        else:
            event.ignore()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and not self.tasks.busy:
            event.acceptProposedAction()

    def dropEvent(self,event):
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                paths.extend(str(p) for p in path.iterdir() if p.suffix.lower() == ".fcs")
            elif path.suffix.lower() == ".fcs":
                paths.append(str(path))
        if paths:
            self.import_paths(sorted(set(paths)))
