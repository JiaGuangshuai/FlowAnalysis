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
    table.setHorizontalHeaderLabels(headers)
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
