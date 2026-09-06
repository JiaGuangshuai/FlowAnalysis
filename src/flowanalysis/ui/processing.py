from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from flowanalysis.core.gating import masks
from flowanalysis.core.io import spill_from_metadata
from flowanalysis.core.processing import estimate_spill, reference_spectra
from .common import FormDialog, combo


class ProcessingPane(QWidget):
    def __init__(self, window, spectral=False):
        super().__init__()
        self.window, self.tr, self.spectral = window, window.tr, spectral
        self.provenance = {}
        layout = QVBoxLayout(self)
        description = self.tr(
            "原始检测通道 → 单染/未染参考谱 → SVD 最小二乘解混。保留负值。行是检测器，列是成分。",
            "Raw detectors → reference spectra → SVD least-squares unmixing. Negative values retained. Rows: detectors; columns: components."
        ) if spectral else self.tr(
            "常规溢出补偿。行是来源荧光，列是检测通道，默认单位为比例（对角线 = 1）。",
            "Conventional spillover compensation. Rows: source dyes; columns: detectors. Default units: fractions (diagonal = 1).")
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        row = QHBoxLayout()
        self.channels = QListWidget()
        self.channels.setMaximumHeight(130)
        row.addWidget(self.channels, 1)
        options = QVBoxLayout()
        self.components = QLineEdit("Dye_A, Dye_B, AF")
        if spectral:
            options.addWidget(QLabel(self.tr("成分名，以英文逗号分隔", "Components, comma separated")))
            options.addWidget(self.components)
            options.addWidget(QLabel(self.tr("背景向量（空白 = 0）；AF 已建模时勿重复减背景", "Background vector (blank = 0); do not subtract modeled AF twice")))
            self.background = QLineEdit()
            options.addWidget(self.background)
        self.percent = QCheckBox(self.tr("输入矩阵单位为百分数（对角线 = 100）", "Input matrix uses percent (diagonal = 100)"))
        if not spectral:
            options.addWidget(self.percent)
        reset = QPushButton(self.tr("按所选通道建立矩阵", "Build matrix from selected channels"))
        reset.clicked.connect(self.initialize_matrix)
        options.addWidget(reset)
        row.addLayout(options, 2)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        for zh,en,fn in [("导入矩阵 CSV", "Import matrix CSV", self.import_matrix),
                         ("从对照计算", "Build from controls", self.control_dialog),
                         ("导出矩阵", "Export matrix", self.export_matrix)]:
            button = QPushButton(self.tr(zh,en))
            button.clicked.connect(fn)
            buttons.addWidget(button)
        if not spectral:
            metadata = QPushButton(self.tr("读取 FCS 补偿矩阵", "Read FCS spillover"))
            metadata.clicked.connect(self.metadata_matrix)
            buttons.addWidget(metadata)
        layout.addLayout(buttons)
        self.table = QTableWidget()
        self.table.setMinimumHeight(220)
        layout.addWidget(self.table, 1)
        self.note = QLabel(self.tr("选择样本后配置。应用后使用“撤销”可恢复；移除通道上的门会归档。",
                                   "Select a sample to configure. Undo restores processing; gates on removed channels are archived."))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.apply = QPushButton(self.tr("应用到当前样本", "Apply to current sample"))
        self.apply.setObjectName("primaryAction")
        self.apply.clicked.connect(self.apply_current)
        layout.addWidget(self.apply)

    def set_sample(self, sample):
        previous = {self.channels.item(i).text() for i in range(self.channels.count()) if self.channels.item(i).checkState() == Qt.CheckState.Checked}
        self.channels.clear()
        if sample is None:
            return
        for name in sample.raw_channels:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            selected = name in previous if previous else not any(k in name.lower() for k in ["fsc", "ssc", "time"])
            item.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
            self.channels.addItem(item)

    def selected_channels(self):
        return [self.channels.item(i).text() for i in range(self.channels.count()) if self.channels.item(i).checkState() == Qt.CheckState.Checked]

    def set_matrix(self, rows, columns, matrix):
        self.table.clear()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(columns))
        self.table.setVerticalHeaderLabels(rows)
        self.table.setHorizontalHeaderLabels(columns)
        for i in range(len(rows)):
            for j in range(len(columns)):
                self.table.setItem(i,j,QTableWidgetItem(f"{matrix[i,j]:.8g}"))
        self.table.resizeColumnsToContents()

    def get_matrix(self):
        rows = [self.table.verticalHeaderItem(i).text() for i in range(self.table.rowCount())]
        columns = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
        matrix = np.array([[float(self.table.item(i,j).text()) for j in range(len(columns))] for i in range(len(rows))])
        if not rows or not columns or not np.isfinite(matrix).all():
            raise ValueError(self.tr("请先建立有效矩阵", "Build a finite matrix first"))
        return rows,columns,matrix

    def initialize_matrix(self):
        try:
            channels = self.selected_channels()
            if not channels:
                raise ValueError(self.tr("请选择通道", "Select channels"))
            if self.spectral:
                components = [c.strip() for c in self.components.text().split(",") if c.strip()]
                self.set_matrix(channels,components,np.zeros((len(channels),len(components))))
            else:
                self.set_matrix(channels,channels,np.eye(len(channels)) * (100 if self.percent.isChecked() else 1))
            self.provenance = {"source": "manual"}
        except Exception as error:
            self.window.show_error(str(error))

    def import_matrix(self):
        path,_ = QFileDialog.getOpenFileName(self,self.tr("导入矩阵", "Import matrix"),"","CSV / TSV (*.csv *.tsv *.txt)")
        if not path:
            return
        try:
            import pandas as pd
            table = pd.read_csv(path,index_col=0,sep=None,engine="python")
            self.set_matrix(list(table.index.astype(str)),list(table.columns.astype(str)),table.to_numpy(float))
            self.provenance = {"source": path}
        except Exception as error:
            self.window.show_error(str(error))

    def export_matrix(self):
        try:
            rows,columns,matrix = self.get_matrix()
            path,_ = QFileDialog.getSaveFileName(self,self.tr("导出矩阵", "Export matrix"),"matrix.csv","CSV (*.csv)")
            if path:
                import pandas as pd
                pd.DataFrame(matrix,index=rows,columns=columns).to_csv(path)
        except Exception as error:
            self.window.show_error(str(error))

    def metadata_matrix(self):
        try:
            sample = self.window.current_sample()
            if not sample:
                return
            channels,matrix = spill_from_metadata(sample)
            self.percent.setChecked(False)
            self.set_matrix(channels,channels,matrix)
            self.provenance = {"source": "FCS SPILLOVER", "sample_id": sample.id}
        except Exception as error:
            self.window.show_error(str(error))

    def control_dialog(self):
        channels = self.selected_channels()
        components = [c.strip() for c in self.components.text().split(",") if c.strip()] if self.spectral else channels
        samples = self.window.project.samples
        if not channels or not components or not samples:
            self.window.show_error(self.tr("请选择通道并导入对照", "Select channels and import controls"))
            return
        dialog = FormDialog(self.tr("参考对照", "Reference controls"),self,
                            self.tr("先在分析工作台给每个对照建立 Positive / Negative 门。每群至少 20 事件。AF 行使用未染细胞的绝对中位谱，假设电子背景为零。",
                                    "Create positive/negative gates first (≥20 events each). AF rows use the unstained population's absolute median spectrum with zero electronic baseline."))
        dialog.resize(1000,550)
        table = QTableWidget(len(components),6)
        table.setHorizontalHeaderLabels([self.tr("成分", "Component"),self.tr("阳性样本", "Positive sample"),
                                          self.tr("阳性门", "Positive gate"),self.tr("阴性样本", "Negative sample"),
                                          self.tr("阴性门", "Negative gate"),"AF"])
        entries = []
        for row,name in enumerate(components):
            table.setItem(row,0,QTableWidgetItem(name))
            positive = combo([(s.name,s.id) for s in samples])
            negative = combo([(s.name,s.id) for s in samples])
            pgate,ngate = QComboBox(),QComboBox()
            af = QCheckBox()
            af.setChecked(self.spectral and name.upper() in {"AF","AUTOFLUORESCENCE"})
            af.setEnabled(self.spectral)
            def update(control,gatebox,preferred):
                selected = self.window.project.sample(control.currentData())
                gatebox.clear()
                gatebox.addItem("All events","root")
                for gate in selected.gates:
                    gatebox.addItem(gate.name,gate.id)
                match = next((i for i in range(gatebox.count()) if preferred in gatebox.itemText(i).lower()),0)
                gatebox.setCurrentIndex(match)
            positive.currentIndexChanged.connect(lambda _,c=positive,g=pgate: update(c,g,"positive"))
            negative.currentIndexChanged.connect(lambda _,c=negative,g=ngate: update(c,g,"negative"))
            preferred_sample = next((i for i,s in enumerate(samples) if name.lower() in s.name.lower()),0)
            positive.setCurrentIndex(preferred_sample)
            negative.setCurrentIndex(preferred_sample)
            update(positive,pgate,"positive")
            update(negative,ngate,"negative")
            for col,widget in enumerate([positive,pgate,negative,ngate,af],1):
                table.setCellWidget(row,col,widget)
            entries.append((positive,pgate,negative,ngate,af))
        table.horizontalHeader().setStretchLastSection(True)
        dialog.extra.insertWidget(1,table)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            pos,neg,records,spectra = [],[],[],[]
            target = self.window.current_sample()
            for name,(ps,pgate,ns,ngate,af) in zip(components,entries):
                p,n = self.window.project.sample(ps.currentData()),self.window.project.sample(ns.currentData())
                for control in [p,n]:
                    if set(channels)-set(control.raw_channels):
                        raise ValueError(f"Missing detectors in {control.name}")
                    if control.state not in {"unknown","raw-conventional","raw-spectral"}:
                        raise ValueError(f"Control must contain raw detector data: {control.name}")
                    if target:
                        for key in ["cyt","cytsn"]:
                            a,b = target.metadata.get(key),control.metadata.get(key)
                            if a and b and a != b:
                                raise ValueError(f"Instrument mismatch ({key}): {control.name}")
                pv = p.raw[masks(p)[pgate.currentData()]][:,[p.raw_channels.index(c) for c in channels]]
                nv = n.raw[masks(n)[ngate.currentData()]][:,[n.raw_channels.index(c) for c in channels]]
                if af.isChecked():
                    if len(pv) < 20:
                        raise ValueError("AF reference requires ≥20 events")
                    spectrum = np.median(pv,axis=0)
                    if spectrum.max() <= 0:
                        raise ValueError("AF spectrum must contain positive signal")
                    spectra.append(spectrum/spectrum.max())
                elif self.spectral:
                    spectra.append(reference_spectra([pv],[nv])[:,0])
                pos.append(pv)
                neg.append(nv)
                records.append({"component":name,"positive_sample":p.id,"positive_gate":pgate.currentData(),
                                "negative_sample":n.id,"negative_gate":ngate.currentData(),"af_absolute_median":af.isChecked(),
                                "positive_gates":[g.to_dict() for g in p.gates],"negative_gates":[g.to_dict() for g in n.gates]})
            matrix = np.column_stack(spectra) if self.spectral else estimate_spill(pos,neg,list(range(len(channels))))
            if not self.spectral:
                self.percent.setChecked(False)
            self.set_matrix(channels,components,matrix)
            self.provenance = {"references":records,"estimator":"median_difference_peak_normalized"}
            self.note.setText(self.tr("参考矩阵已计算；请核查矩阵与通道后应用。", "Reference matrix calculated. Review channels and values before applying."))
        except Exception as error:
            self.window.show_error(str(error))

    def apply_current(self):
        sample = self.window.current_sample()
        if not sample:
            return
        try:
            rows,columns,matrix = self.get_matrix()
            if self.spectral:
                bgtext = self.background.text().strip()
                background = [float(x.strip()) for x in bgtext.split(",")] if bgtext else None
                self.window.process_current("spectral",rows,matrix,columns,background,self.provenance)
            else:
                if rows != columns:
                    raise ValueError("Conventional matrix needs identical row/column channel labels")
                if self.percent.isChecked():
                    matrix = matrix/100
                self.window.process_current("compensation",rows,matrix,provenance=self.provenance)
        except Exception as error:
            self.window.show_error(str(error))
