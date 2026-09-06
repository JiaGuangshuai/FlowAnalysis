from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


def combo(options, current=None):
    control = QComboBox()
    for label, data in options:
        control.addItem(label, data)
    if current is not None:
        index = control.findData(current)
        if index >= 0:
            control.setCurrentIndex(index)
    return control


def number(value, minimum=-1e12, maximum=1e12, decimals=4):
    control = QDoubleSpinBox()
    control.setRange(minimum, maximum)
    control.setDecimals(decimals)
    control.setValue(value)
    control.setKeyboardTracking(False)
    return control


def integer(value, minimum=1, maximum=10000000):
    control = QSpinBox()
    control.setRange(minimum, maximum)
    control.setValue(value)
    return control


def fill_table(table, rows):
    headers = list(rows[0]) if rows else []
    table.clear()
    table.setColumnCount(len(headers))
    table.setRowCount(len(rows))
    labels = {"sample":"样本", "sample_id":"样本 ID", "group":"样本组", "plate":"板", "well":"孔位",
              "gate":"群体", "gate_id":"门 ID", "parent_id":"父门 ID", "events":"事件数",
              "parent_events":"父群体事件数", "percent_parent":"占父群体 %", "percent_total":"占总事件 %",
              "data_state":"数据状态", "intensity_space":"强度空间", "parameter":"参数", "value":"数值",
              "statistic":"统计量", "metacluster":"元簇", "time_start":"起始时间", "time_end":"结束时间",
              "time_mid":"时间中点", "median":"中位数", "mean":"均值", "std":"标准差",
              "q25":"下四分位数", "q75":"上四分位数", "fold_baseline":"相对基线倍数"}
    chinese = getattr(table.window(), "language", "en") == "zh"
    def translated(header):
        if not chinese:
            return header
        if ":" in header:
            channel, statistic = header.rsplit(":", 1)
            return channel + ":" + labels.get(statistic, statistic)
        return labels.get(header, header)
    table.setHorizontalHeaderLabels([translated(h) for h in headers])
    for r, row in enumerate(rows):
        for c, header in enumerate(headers):
            value = row[header]
            if isinstance(value, float):
                text = f"{value:.5g}"
            else:
                text = "NA" if value is None else str(value)
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


class FormDialog(QDialog):
    def __init__(self, title, parent=None, explanation=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 400)
        layout = QVBoxLayout(self)
        if explanation:
            label = QLabel(explanation)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.extra = layout
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def add(self, label, widget):
        self.form.addRow(label, widget)
        return widget


class TextDialog(QDialog):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        button = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button.rejected.connect(self.reject)
        layout.addWidget(button)


def result_table(parent, title, rows):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(950, 600)
    layout = QVBoxLayout(dialog)
    table = QTableWidget()
    fill_table(table, rows)
    layout.addWidget(table)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.exec()
