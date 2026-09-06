from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from flowanalysis.core.export import export_layout, export_statistics, plot_on_axes
from flowanalysis.core.gating import statistics
from .common import combo, fill_table, integer


class StatisticsPane(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(window.tr("计数和比例使用全量事件；强度统计在处理后线性数据上计算。",
                                        "Counts use all events; intensity statistics use processed linear data.")),1)
        for zh,en,fn in [("刷新","Refresh",self.refresh),("导出 CSV / XLSX","Export CSV / XLSX",self.export)]:
            button = QPushButton(window.tr(zh,en))
            button.clicked.connect(fn)
            row.addWidget(button)
        layout.addLayout(row)
        self.table = QTableWidget()
        layout.addWidget(self.table,1)

    def refresh(self):
        try:
            rows = []
            sample = self.window.current_sample()
            if sample:
                rows = statistics(sample,sample.channels)
            fill_table(self.table,rows)
        except Exception as error:
            self.window.show_error(str(error))

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,self.window.tr("导出全部样本统计","Export all sample statistics"),
                                             "statistics.xlsx","Excel (*.xlsx);;CSV (*.csv)")
        if path:
            self.window.start_task(export_statistics,(self.window.project,path),
                                   lambda _:self.window.statusBar().showMessage(self.window.tr("导出完成","Export complete")),
                                   self.window.tr("计算并导出全量统计","Computing and exporting full statistics"))


class LayoutPane(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window = window
        self.canvas = None
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(window.tr("在工作台点击“加入图版”；拖动列表可排序。","Use Add to layout in Analysis; drag list entries to reorder.")),1)
        self.columns = integer(2,1,4)
        row.addWidget(QLabel(window.tr("列数","Columns")))
        row.addWidget(self.columns)
        for zh,en,fn in [("预览","Preview",self.preview),("移除所选","Remove selected",self.remove),("导出图版","Export layout",self.export)]:
            button = QPushButton(window.tr(zh,en))
            button.clicked.connect(fn)
            row.addWidget(button)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setMaximumHeight(150)
        self.list.model().rowsMoved.connect(self.reordered)
        layout.addWidget(self.list)
        self.holder = QVBoxLayout()
        layout.addLayout(self.holder,1)

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for specification in self.window.project.layouts:
            try:
                sample = self.window.project.sample(specification["sample_id"])
                item = QListWidgetItem(f'{sample.name} · {specification["x"]} / {specification["y"]}')
                item.setData(Qt.ItemDataRole.UserRole,deepcopy(specification))
                self.list.addItem(item)
            except StopIteration:
                continue
        self.list.blockSignals(False)

    def reordered(self,*args):
        self.window.checkpoint("reorder_layout")
        self.window.project.layouts = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.window.mark_dirty()

    def remove(self):
        row = self.list.currentRow()
        if row >= 0:
            self.window.checkpoint("remove_layout_plot")
            self.window.project.layouts.pop(row)
            self.refresh()
            self.window.mark_dirty()

    def preview(self):
        if not self.window.project.layouts:
            return
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            from flowanalysis.core.export import configure_fonts
            configure_fonts()
            if self.canvas:
                self.holder.removeWidget(self.canvas)
                self.canvas.deleteLater()
            specs = self.window.project.layouts
            cols = min(self.columns.value(),len(specs))
            rows = (len(specs)+cols-1)//cols
            figure = Figure(figsize=(5*cols,4*rows),layout="constrained")
            self.canvas = FigureCanvasQTAgg(figure)
            self.holder.addWidget(self.canvas)
            for i,spec in enumerate(specs):
                plot_on_axes(figure.add_subplot(rows,cols,i+1),self.window.project.sample(spec["sample_id"]),spec)
            self.canvas.draw()
        except Exception as error:
            self.window.show_error(str(error))

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,self.window.tr("导出图版","Export layout"),"layout.pdf",
                                             "PDF (*.pdf);;SVG (*.svg);;PNG (*.png)")
        if path:
            self.window.start_task(_export_layout_job,(self.window.project,self.window.project.layouts,path,self.columns.value()),
                                   lambda _:self.window.statusBar().showMessage(self.window.tr("图版已导出","Layout exported")),
                                   self.window.tr("导出图版","Exporting layout"))


def _export_layout_job(project,specs,path,columns):
    export_layout(project,specs,path,columns)
    return path


class PlatePane(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.plate = QComboBox()
        self.plate.setEditable(True)
        self.plate.addItem("Plate 1")
        self.size = combo([("96",96),("384",384)])
        self.plate.currentTextChanged.connect(self.refresh)
        self.size.currentIndexChanged.connect(self.refresh)
        row.addWidget(QLabel(window.tr("板名","Plate")))
        row.addWidget(self.plate)
        row.addWidget(self.size)
        for zh,en,fn in [("将当前样本分配至所选孔","Assign sample to selected well",self.assign),
                         ("导入映射 CSV","Import mapping CSV",self.import_mapping),
                         ("导出映射 CSV","Export mapping CSV",self.export_mapping)]:
            button = QPushButton(window.tr(zh,en))
            button.clicked.connect(fn)
            row.addWidget(button)
        layout.addLayout(row)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table,1)
        self.note = QLabel(window.tr("每孔显示样本名和总事件数。CSV 列：sample, plate, well, group；sample 名必须唯一。",
                                     "Each well shows sample name and total events. CSV columns: sample, plate, well, group; sample names must be unique."))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.refresh()

    def refresh(self,*args):
        if not hasattr(self,"table"):
            return
        rows,cols = (8,12) if self.size.currentData() == 96 else (16,24)
        self.table.clear()
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self.table.setVerticalHeaderLabels([chr(65+i) for i in range(rows)])
        self.table.setHorizontalHeaderLabels([str(i+1) for i in range(cols)])
        for sample in self.window.project.samples:
            if sample.plate != self.plate.currentText() or not sample.well:
                continue
            try:
                r,c = parse_well(sample.well)
                if r < rows and c < cols:
                    item = self.table.item(r,c)
                    text = (item.text()+"\n" if item else "")+f"{sample.name}\n{len(sample.data):,}"
                    self.table.setItem(r,c,QTableWidgetItem(text))
            except ValueError:
                continue
        self.table.resizeRowsToContents()
        self.table.resizeColumnsToContents()

    def assign(self):
        sample = self.window.current_sample()
        row,col = self.table.currentRow(),self.table.currentColumn()
        if sample and row >= 0 and col >= 0:
            well = f"{chr(65+row)}{col+1:02d}"
            plate = self.plate.currentText().strip()
            if not plate:
                return
            occupied = [s for s in self.window.project.samples if s.id != sample.id and s.plate == plate and s.well == well]
            if occupied:
                self.window.show_error(self.window.tr("该孔已有样本，请选择空孔。","That well already has a sample; choose an empty well."))
                return
            self.window.checkpoint("assign_plate_well")
            sample.plate,sample.well = plate,well
            self.window.mark_dirty()
            self.refresh()

    def import_mapping(self):
        path,_ = QFileDialog.getOpenFileName(self,"CSV","","CSV (*.csv)")
        if not path:
            return
        try:
            import pandas as pd
            table = pd.read_csv(path,dtype=str).fillna("")
            if not {"sample","plate","well"}.issubset(table.columns):
                raise ValueError("CSV requires sample, plate, well columns")
            updates = []
            for _,row in table.iterrows():
                matches = [s for s in self.window.project.samples if s.name == row["sample"]]
                if len(matches) != 1:
                    raise ValueError(f"Sample missing or ambiguous: {row['sample']}")
                r,c = parse_well(row["well"])
                updates.append((matches[0],row["plate"],f"{chr(65+r)}{c+1:02d}",row.get("group",matches[0].group)))
            wells = [(p,w) for _,p,w,_ in updates]
            updated_ids = [s.id for s,_,_,_ in updates]
            if len(set(updated_ids)) != len(updated_ids):
                raise ValueError("Duplicate sample rows in CSV")
            wells += [(s.plate,s.well) for s in self.window.project.samples if s.id not in updated_ids and s.well]
            if len(set(wells)) != len(wells):
                raise ValueError("Duplicate well assignments across CSV and existing samples")
            self.window.checkpoint("import_plate_mapping")
            for sample,plate,well,group in updates:
                sample.plate,sample.well,sample.group = plate,well,group
            self.window.refresh_tree()
            self.refresh()
            self.window.mark_dirty()
        except Exception as error:
            self.window.show_error(str(error))

    def export_mapping(self):
        path,_ = QFileDialog.getSaveFileName(self,"CSV","plate-map.csv","CSV (*.csv)")
        if path:
            try:
                import pandas as pd
                pd.DataFrame([{"sample":s.name,"sample_id":s.id,"plate":s.plate,"well":s.well,"group":s.group}
                              for s in self.window.project.samples]).to_csv(path,index=False,encoding="utf-8-sig")
            except Exception as error:
                self.window.show_error(str(error))


def parse_well(value):
    import re
    match = re.fullmatch(r"([A-Pa-p])0?([1-9]|1[0-9]|2[0-4])",str(value).strip())
    if not match:
        raise ValueError(f"Invalid well: {value}")
    return ord(match[1].upper())-65,int(match[2])-1
