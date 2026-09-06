from dataclasses import asdict

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from flowanalysis.core.gating import masks
from flowanalysis.core.model import Gate, Transform
from .common import FormDialog, combo, number


class PlotPane(QWidget):
    gateReady = Signal(dict)
    layoutReady = Signal(dict)
    error = Signal(str)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.sample = None
        self.gate_id = "root"
        self.roi = None
        self.roi_kind = ""
        self.tx = Transform()
        self.ty = Transform()
        self.current_masks = {}
        self.overlays = []
        layout = QVBoxLayout(self)
        self.title = QLabel(tr("导入 FCS 或打开模拟演示以开始", "Import FCS or open the synthetic demo to begin"))
        layout.addWidget(self.title)
        row = QHBoxLayout()
        self.x = QComboBox()
        self.y = QComboBox()
        for label, control in [("X", self.x), ("Y", self.y)]:
            row.addWidget(QLabel(label))
            row.addWidget(control, 1)
            control.currentIndexChanged.connect(self.axes_changed)
        self.mode = combo([(tr("密度", "Density"), "density"), (tr("散点", "Scatter"), "scatter"),
                           (tr("等高线", "Contour"), "contour"), (tr("直方图", "Histogram"), "histogram")])
        self.mode.currentIndexChanged.connect(self.redraw)
        row.addWidget(self.mode)
        self.settings = QPushButton(tr("坐标变换", "Transforms"))
        self.settings.clicked.connect(self.transform_dialog)
        row.addWidget(self.settings)
        layout.addLayout(row)
        tools = QHBoxLayout()
        for zh, en, kind in [("矩形", "Rectangle", "rectangle"), ("多边形", "Polygon", "polygon"),
                             ("椭圆", "Ellipse", "ellipse"), ("区间", "Range", "range"),
                             ("象限", "Quadrants", "quadrant")]:
            button = QPushButton(tr(zh, en))
            button.clicked.connect(lambda checked=False, k=kind: self.begin_roi(k))
            tools.addWidget(button)
        self.edit = QCheckBox(tr("编辑所选门", "Edit selected gate"))
        self.edit.toggled.connect(self.redraw)
        tools.addWidget(self.edit)
        layout.addLayout(tools)
        self.plot = pg.PlotWidget(background="w")
        self.plot.showGrid(x=True, y=True, alpha=.08)
        self.plot.getPlotItem().getAxis("bottom").setPen("#63758b")
        self.plot.getPlotItem().getAxis("left").setPen("#63758b")
        self.plot.getPlotItem().getAxis("bottom").setTextPen("#203040")
        self.plot.getPlotItem().getAxis("left").setTextPen("#203040")
        self.plot.setMinimumSize(350, 300)
        layout.addWidget(self.plot, 1)
        footer = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        footer.addWidget(self.hint, 1)
        save = QPushButton(tr("保存门", "Save gate"))
        save.clicked.connect(self.save_roi)
        footer.addWidget(save)
        add = QPushButton(tr("加入图版", "Add to layout"))
        add.clicked.connect(lambda: self.layoutReady.emit(self.specification()) if self.sample else None)
        footer.addWidget(add)
        layout.addLayout(footer)

    def set_sample(self, sample, gate_id="root", overlays=None):
        previous = self.sample.id if self.sample else None
        self.sample, self.gate_id = sample, gate_id
        self.overlays = overlays or []
        if sample is None:
            self.plot.clear()
            return
        for control in [self.x, self.y]:
            old = control.currentData()
            control.blockSignals(True)
            control.clear()
            for channel in sample.channels:
                control.addItem(sample.label(channel), channel)
            control.setCurrentIndex(max(0, control.findData(old)))
            control.blockSignals(False)
        if previous != sample.id and len(sample.channels) > 1 and self.y.currentIndex() == self.x.currentIndex():
            self.y.setCurrentIndex(min(2, len(sample.channels)-1))
        gate = next((g for g in sample.gates if g.id == gate_id), None)
        if gate and gate.axes:
            self.x.blockSignals(True)
            self.y.blockSignals(True)
            self.x.setCurrentIndex(self.x.findData(gate.axes[0]))
            self.tx = Transform(**gate.transforms[0])
            if len(gate.axes) > 1:
                self.y.setCurrentIndex(self.y.findData(gate.axes[1]))
                self.ty = Transform(**gate.transforms[1])
            self.x.blockSignals(False)
            self.y.blockSignals(False)
        self.redraw()

    def axes_changed(self):
        if self.edit.isChecked():
            self.edit.blockSignals(True)
            self.edit.setChecked(False)
            self.edit.blockSignals(False)
        self.redraw()

    def specification(self):
        return {"sample_id": self.sample.id, "gate_id": self.gate_id, "x": self.x.currentData(),
                "y": self.y.currentData(), "tx": asdict(self.tx), "ty": asdict(self.ty),
                "mode": self.mode.currentData()}

    def redraw(self):
        self.plot.clear()
        self.roi = None
        self.roi_kind = ""
        if not self.sample or self.x.currentData() is None or self.y.currentData() is None:
            return
        try:
            self._draw()
        except Exception as error:
            self.hint.setText(str(error))
            self.error.emit(str(error))

    def _draw(self):
        sample = self.sample
        self.current_masks = masks(sample)
        gate = next((g for g in sample.gates if g.id == self.gate_id), None)
        display_id = gate.parent if self.edit.isChecked() and gate else self.gate_id
        mask = self.current_masks[display_id]
        x = self.tx.apply(sample.column(self.x.currentData())[mask])
        y = self.ty.apply(sample.column(self.y.currentData())[mask])
        valid = np.isfinite(x) & np.isfinite(y)
        mode = self.mode.currentData()
        self.plot.setLabel("bottom", sample.label(self.x.currentData()) + f" [{self.tx.kind}]")
        self.plot.setLabel("left", self.tr("事件数", "Events") if mode == "histogram" else sample.label(self.y.currentData()) + f" [{self.ty.kind}]")
        self.title.setText(f"{sample.name}  /  {gate.name if gate else 'All events'}  ·  {sample.state}")
        count = int(mask.sum())
        shown = min(int(valid.sum()), 40000)
        if mode == "histogram":
            vals = x[np.isfinite(x)]
            if len(vals):
                hist, edges = np.histogram(vals, bins=128)
                self.plot.plot(edges, hist, stepMode="center", fillLevel=0, brush=(20, 111, 121, 30), pen=pg.mkPen("#146f79", width=2))
            for index, other in enumerate(self.overlays):
                if other.id == sample.id or self.x.currentData() not in other.channels:
                    continue
                candidates = [g for g in other.gates if gate and g.name == gate.name]
                other_gate = candidates[0].id if len(candidates) == 1 else "root"
                omask = masks(other)[other_gate]
                v = self.tx.apply(other.column(self.x.currentData())[omask])
                v = v[np.isfinite(v)]
                if len(v):
                    h, e = np.histogram(v, bins=128)
                    self.plot.plot(e, h, stepMode="center", pen=pg.mkPen(pg.intColor(index + 2), width=2), name=other.name)
        elif valid.any():
            if mode == "scatter":
                ids = np.flatnonzero(valid)
                if len(ids) > shown:
                    ids = np.random.default_rng(42).choice(ids, shown, replace=False)
                self.plot.plot(x[ids], y[ids], pen=None, symbol="o", symbolSize=2,
                               symbolPen=None, symbolBrush=(20, 111, 121, 110))
            else:
                hist, xe, ye = np.histogram2d(x[valid], y[valid], bins=200)
                if mode == "density":
                    image = pg.ImageItem(np.log1p(hist), axisOrder="col-major")
                    image.setLookupTable(pg.colormap.get("viridis").getLookupTable())
                    self.plot.addItem(image)
                    from PySide6.QtCore import QRectF
                    image.setRect(QRectF(xe[0], ye[0], xe[-1]-xe[0], ye[-1]-ye[0]))
                else:
                    from scipy.ndimage import gaussian_filter
                    import contourpy
                    density = gaussian_filter(hist.T, 1.5)
                    generator = contourpy.contour_generator(x=(xe[:-1]+xe[1:])/2, y=(ye[:-1]+ye[1:])/2, z=density)
                    for level in np.linspace(density.max()*.08, density.max()*.9, 7):
                        for line in generator.lines(level):
                            self.plot.plot(line[:, 0], line[:, 1], pen=pg.mkPen("#146f79", width=1))
        self.plot.autoRange()
        self.hint.setText(self.tr(f"全量群体 {count:,} 事件；散点最多显示 40,000。门边界以当前变换坐标保存。",
                                  f"Population: {count:,} events; scatter displays ≤40,000. Gates store their coordinate transform."))
        if self.edit.isChecked() and gate:
            self.load_gate_roi(gate)
        else:
            self.draw_children(display_id)

    def draw_children(self, parent):
        for gate in self.sample.gates:
            if gate.parent != parent or gate.axes != [self.x.currentData(), self.y.currentData()]:
                continue
            if [Transform(**t) for t in gate.transforms] != [self.tx, self.ty]:
                continue
            pen = pg.mkPen("#c16b25", width=1.7)
            if gate.kind == "polygon":
                vertices = np.asarray(gate.geometry["vertices"])
                vertices = np.vstack([vertices, vertices[0]])
                self.plot.plot(vertices[:, 0], vertices[:, 1], pen=pen)
            elif gate.kind == "rectangle":
                (a,b),(c,d) = gate.geometry["bounds"]
                if None not in (a,b,c,d):
                    self.plot.plot([a,b,b,a,a], [c,c,d,d,c], pen=pen)
            elif gate.kind == "ellipse":
                theta = np.linspace(0, 2*np.pi, 100)
                rx, ry = gate.geometry["radii"]
                xy = np.column_stack([rx*np.cos(theta), ry*np.sin(theta)])
                angle = gate.geometry.get("angle", 0)
                rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
                xy = xy @ rotation.T + gate.geometry["center"]
                self.plot.plot(xy[:, 0], xy[:, 1], pen=pen)

    def begin_roi(self, kind):
        if not self.sample:
            return
        if self.edit.isChecked():
            self.edit.setChecked(False)
        self.redraw()
        (x0,x1),(y0,y1) = self.plot.viewRange()
        width,height = x1-x0,y1-y0
        geometry = {"bounds": [[x0+.25*width,x0+.75*width],[y0+.25*height,y0+.75*height]]}
        if kind == "polygon":
            geometry = {"vertices": [[x0+.25*width,y0+.3*height],[x0+.7*width,y0+.25*height],
                                     [x0+.8*width,y0+.7*height],[x0+.4*width,y0+.8*height]]}
        elif kind == "ellipse":
            geometry = {"center": [(x0+x1)/2,(y0+y1)/2], "radii": [width*.25,height*.25]}
        elif kind == "quadrant":
            geometry = {"thresholds": [(x0+x1)/2,(y0+y1)/2], "positive": [True,True]}
        elif kind == "range":
            geometry = {"bounds": [[x0+.25*width,x0+.75*width]]}
        gate = Gate("", kind, [self.x.currentData(),self.y.currentData()],
                    [asdict(self.tx),asdict(self.ty)], geometry)
        self.load_gate_roi(gate)
        self.hint.setText(self.tr("拖动边框/顶点调整，然后点击“保存门”。多边形可在边上添加顶点。",
                                  "Drag the outline/handles, then Save gate. Click polygon edges to add vertices."))

    def load_gate_roi(self, gate):
        kind,g = gate.kind,gate.geometry
        pen = pg.mkPen("#c16b25",width=2)
        if kind == "rectangle":
            (a,b),(c,d) = g["bounds"]
            if None in (a,b,c,d):
                self.hint.setText(self.tr("无界门请使用门定义编辑器", "Use the gate definition editor for unbounded gates"))
                return
            self.roi = pg.RectROI([a,c],[b-a,d-c],pen=pen)
        elif kind == "polygon":
            self.roi = pg.PolyLineROI(g["vertices"], closed=True,pen=pen)
        elif kind == "ellipse":
            center,radii = np.array(g["center"]),np.array(g["radii"])
            if g.get("angle",0) != 0:
                self.hint.setText(self.tr("旋转椭圆请使用门定义编辑器", "Use the gate definition editor for rotated ellipses"))
                return
            self.roi = pg.EllipseROI(center-radii,radii*2,pen=pen,rotatable=False)
        elif kind == "range":
            bounds = g["bounds"][0]
            xrange = self.plot.viewRange()[0]
            self.roi = pg.LinearRegionItem([xrange[0] if bounds[0] is None else bounds[0],
                                           xrange[1] if bounds[1] is None else bounds[1]],pen=pen)
        elif kind == "quadrant":
            self.roi = [pg.InfiniteLine(pos=g["thresholds"][0],angle=90,movable=True,pen=pen),
                        pg.InfiniteLine(pos=g["thresholds"][1],angle=0,movable=True,pen=pen)]
        else:
            self.hint.setText(self.tr("此门通过定义或事件索引管理", "This gate is managed through its definition or event indices"))
            return
        self.roi_kind = kind
        for item in self.roi if isinstance(self.roi,list) else [self.roi]:
            self.plot.addItem(item)

    def save_roi(self):
        if self.roi is None:
            return
        kind = self.roi_kind
        if kind == "rectangle":
            pos,size = self.roi.pos(),self.roi.size()
            geometry = {"bounds": [[pos.x(),pos.x()+size.x()],[pos.y(),pos.y()+size.y()]]}
        elif kind == "polygon":
            geometry = {"vertices": [[self.roi.mapToParent(p).x(),self.roi.mapToParent(p).y()] for _,p in self.roi.getLocalHandlePositions()]}
        elif kind == "ellipse":
            pos,size = self.roi.pos(),self.roi.size()
            geometry = {"center": [pos.x()+size.x()/2,pos.y()+size.y()/2], "radii": [size.x()/2,size.y()/2], "angle": 0}
        elif kind == "range":
            geometry = {"bounds": [list(self.roi.getRegion())]}
        else:
            geometry = {"thresholds": [line.value() for line in self.roi],"positive": [True,True]}
        axes = [self.x.currentData()] if kind == "range" else [self.x.currentData(),self.y.currentData()]
        transforms = [asdict(self.tx)] if kind == "range" else [asdict(self.tx),asdict(self.ty)]
        self.gateReady.emit({"kind": kind,"axes": axes,"transforms": transforms,"geometry": geometry,
                             "edit_id": self.gate_id if self.edit.isChecked() else None})

    def transform_dialog(self):
        dialog = FormDialog(self.tr("坐标变换", "Coordinate transforms"),self,
                            self.tr("门保存其独立变换；更改显示变换不会移动已有门。Log 视图不显示非正值。",
                                    "Existing gates retain their own transform. Log display excludes nonpositive values."))
        kinds = [(v,v) for v in ["linear","log","logicle","biexponential","hyperlog","arcsinh"]]
        fields = []
        for label,tr in [("X",self.tx),("Y",self.ty)]:
            kind = dialog.add(label,combo(kinds,tr.kind))
            cofactor = dialog.add(label+" arcsinh cofactor",number(tr.cofactor,.0001))
            top = dialog.add(label+" T",number(tr.t,1))
            decades = dialog.add(label+" M",number(tr.m,.1,10))
            width = dialog.add(label+" W",number(tr.w,0,5))
            negative = dialog.add(label+" A",number(tr.a,-5,10))
            fields.append((kind,cofactor,top,decades,width,negative))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                transforms = [Transform(kind.currentData(),cf.value(),top.value(),m.value(),w.value(),a.value())
                              for kind,cf,top,m,w,a in fields]
                for tr in transforms:
                    tr.apply(np.array([0.,1.]))
                self.tx,self.ty = transforms
                self.edit.setChecked(False)
                self.redraw()
            except Exception as error:
                self.error.emit(str(error))
