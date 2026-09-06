from __future__ import annotations

import json

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QVBoxLayout, QWidget,
)

from flowanalysis.core.io import json_clean
from flowanalysis.core.jobs import advanced_analysis
from .common import combo, fill_table, integer, number


class AdvancedPane(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window,self.tr = window,window.tr
        self.result = None
        layout = QHBoxLayout(self)
        splitter = QSplitter()
        layout.addWidget(splitter)
        panel = QWidget()
        left = QVBoxLayout(panel)
        self.method = combo([(v,v) for v in ["UMAP","t-SNE","FlowSOM"]] + [
            (self.tr("细胞周期", "Cell cycle"),"cell_cycle"),
            (self.tr("增殖 / 染料稀释", "Proliferation"),"proliferation"),
            (self.tr("动力学", "Kinetics"),"kinetics")])
        left.addWidget(self.method)
        self.channels = QListWidget()
        self.channels.setMaximumHeight(180)
        left.addWidget(QLabel(self.tr("分析通道（模型分析只选一个信号通道）", "Channels (select one signal for model fitting)")))
        left.addWidget(self.channels)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        fields = QWidget()
        self.form = QFormLayout(fields)
        scroll.setWidget(fields)
        left.addWidget(scroll,1)
        self.fields = {}
        self.row_methods = {}
        def add(key,zh,en,control,methods):
            self.fields[key] = control
            self.form.addRow(self.tr(zh,en),control)
            self.row_methods[key] = methods
        high = {"UMAP","t-SNE","FlowSOM"}
        add("transform","输入变换","Input transform",combo([(x,x) for x in ["arcsinh","logicle","linear"]]),high)
        add("cofactor","arcsinh cofactor","arcsinh cofactor",number(150,.0001),high)
        add("standardize","通道 z-score 标准化","Per-channel z-score",QCheckBox(),high)
        add("seed","随机种子","Random seed",integer(42,0),high)
        add("limit","抽样/训练事件上限","Sample/training event limit",integer(30000,10),high)
        add("neighbors","邻居数","Neighbors",integer(15,2,1000),{"UMAP"})
        add("min_dist","最小距离","Minimum distance",number(.1,0,1),{"UMAP"})
        add("perplexity","困惑度","Perplexity",number(30,1,10000),{"t-SNE"})
        add("iterations","迭代次数","Iterations",integer(1000,250,10000),{"t-SNE"})
        add("clusters","元簇数量","Metaclusters",integer(8,2,100),{"FlowSOM"})
        add("grid","SOM 网格边长","SOM grid side",integer(8,2,30),{"FlowSOM"})
        add("g1","G1 峰（线性强度）","G1 peak (linear)",number(50000,.0001),{"cell_cycle"})
        add("cv","初始 G1 CV（比例）","Initial G1 CV (fraction)",number(.06,.01,.2),{"cell_cycle"})
        add("peak","未分裂对照峰","Undivided control peak",number(50000,.0001),{"proliferation"})
        add("generations","最大分裂代数","Maximum divisions",integer(6,1,12),{"proliferation"})
        add("background","扣除背景值","Background subtraction",number(0),{"proliferation"})
        add("time_channel","时间通道","Time channel",combo([]),{"kinetics"})
        add("time_scale","时间乘数 → 秒","Time multiplier → seconds",number(1,.000001,1e6,6),{"kinetics"})
        add("bin_width","时间窗（秒）","Bin width (seconds)",number(5,.001,1e6),{"kinetics"})
        add("baseline","基线归一化","Normalize to baseline",QCheckBox(),{"kinetics"})
        add("baseline_end","基线截止（秒）","Baseline end (seconds)",number(30),{"kinetics"})
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        left.addWidget(self.notice)
        run = QPushButton(self.tr("运行分析", "Run analysis"))
        run.setObjectName("primaryAction")
        run.clicked.connect(self.run)
        left.addWidget(run)
        splitter.addWidget(panel)
        output = QWidget()
        right = QVBoxLayout(output)
        self.saved_results = combo([])
        self.results_sample = None
        right.addWidget(QLabel(self.tr("已保存的分析结果", "Saved analysis results")))
        right.addWidget(self.saved_results)
        self.saved_results.currentIndexChanged.connect(self.select_saved_result)
        self.canvas_holder = QVBoxLayout()
        right.addLayout(self.canvas_holder,1)
        self.placeholder = QLabel(self.tr("结果将在这里显示；长任务可在底部取消。", "Results appear here. Cancel long tasks using the status bar."))
        self.placeholder.setWordWrap(True)
        self.canvas_holder.addWidget(self.placeholder)
        self.canvas = None
        self.table = QTableWidget()
        self.table.setMaximumHeight(220)
        right.addWidget(self.table)
        controls = QHBoxLayout()
        for zh,en,fn in [("导出结果","Export results",self.export_result),
                         ("导出图形","Export figure",self.export_figure),
                         ("从聚类建立门","Create cluster gates",self.cluster_gates)]:
            button = QPushButton(self.tr(zh,en))
            button.clicked.connect(fn)
            controls.addWidget(button)
        right.addLayout(controls)
        splitter.addWidget(output)
        splitter.setSizes([310,680])
        self.method.currentIndexChanged.connect(self.method_changed)
        self.method_changed()

    def method_changed(self):
        method = self.method.currentData()
        for key,methods in self.row_methods.items():
            self.form.setRowVisible(self.fields[key],method in methods)
        notices = {
            "cell_cycle":self.tr("独立探索模型：G1/G2 高斯 + 平滑均匀 S 期。先选单细胞门；不包含碎片、非整倍体和双细胞模型。查看残差后判断。",
                                 "Exploratory G1/G2 Gaussian + broadened uniform-S model. Select singlets; debris, aneuploidy and doublets are not modeled. Inspect residuals."),
            "proliferation":self.tr("使用未分裂对照确定 G0；模型假设每代荧光减半。请检查拟合与被排除事件。",
                                    "Set G0 from an undivided control. Model assumes twofold dye dilution per generation. Review fit and excluded events."),
            "kinetics":self.tr("FCS 时间已按 TIMESTEP 缩放；默认乘数 1。空时间窗保留，显示中位数和四分位数。",
                               "FCS time is pre-scaled by TIMESTEP; multiplier defaults to 1. Empty bins are retained; median and quartiles are reported."),
        }
        self.notice.setText(notices.get(method,self.tr("选择荧光通道。抽样索引、变换和随机种子随结果保存；FlowSOM 将全量所选群体映射到训练网格。",
                                                       "Select fluorescence channels. Sampling indices, transform and seed are saved. FlowSOM maps the full population to its training grid.")))

    def set_sample(self,sample):
        selected = {self.channels.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.channels.count())
                    if self.channels.item(i).checkState() == Qt.CheckState.Checked}
        self.channels.clear()
        self.fields["time_channel"].clear()
        if sample:
            for channel in sample.channels:
                item = QListWidgetItem(sample.label(channel))
                item.setData(Qt.ItemDataRole.UserRole,channel)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                check = channel in selected if selected else channel in {"CD3","CD4","CD8"}
                item.setCheckState(Qt.CheckState.Checked if check else Qt.CheckState.Unchecked)
                self.channels.addItem(item)
                self.fields["time_channel"].addItem(channel,channel)
            idx = next((i for i,c in enumerate(sample.channels) if c.lower() == "time"),0)
            self.fields["time_channel"].setCurrentIndex(idx)
        self.results_sample = sample
        self.refresh_saved_results()

    def refresh_saved_results(self):
        self.saved_results.blockSignals(True)
        self.saved_results.clear()
        for index,result in enumerate(self.results_sample.results if self.results_sample else []):
            self.saved_results.addItem(f"{index+1}. {result['method']} · {result.get('gate_name', 'root')}",index)
        self.saved_results.setCurrentIndex(self.saved_results.count()-1)
        self.saved_results.blockSignals(False)
        self.select_saved_result()

    def select_saved_result(self):
        index = self.saved_results.currentData()
        if index is not None and self.results_sample:
            self.render_result(self.results_sample.results[index])
        else:
            self.result = None
            if self.canvas:
                self.canvas_holder.removeWidget(self.canvas)
                self.canvas.deleteLater()
                self.canvas = None
            self.placeholder.show()
            self.table.clear()
            self.table.setRowCount(0)

    def parameters(self):
        values = {}
        for key,control in self.fields.items():
            if hasattr(control,"currentData"):
                values[key] = control.currentData()
            elif isinstance(control,QCheckBox):
                values[key] = control.isChecked()
            else:
                values[key] = control.value()
        return values

    def run(self):
        sample = self.window.current_sample()
        if not sample:
            return
        channels = [self.channels.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.channels.count())
                    if self.channels.item(i).checkState() == Qt.CheckState.Checked]
        method = self.method.currentData()
        if not channels or (method in {"cell_cycle","proliferation","kinetics"} and len(channels) != 1):
            self.window.show_error(self.tr("降维/聚类至少选两个通道；模型分析选一个信号通道。", "Select ≥2 channels for embeddings/clustering or one signal channel for models."))
            return
        self.window.start_task(advanced_analysis,
                               (sample,self.window.gate_id,method,channels,self.parameters()),
                               self.accept_result,self.tr("分析计算中", "Running analysis"))

    def accept_result(self,result):
        sample = self.window.project.sample(result["sample_id"])
        if result["sample_revision"] != sample.revision:
            self.window.show_error(self.tr("样本已变化，丢弃过期结果", "Sample changed; discarded stale result"))
            return
        self.window.checkpoint("advanced_analysis")
        sample.results.append(json_clean(result))
        self.results_sample = sample
        self.refresh_saved_results()
        self.window.mark_dirty()

    def render_result(self,result):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        from flowanalysis.core.export import configure_fonts

        configure_fonts()
        self.result = result
        if self.canvas:
            self.canvas_holder.removeWidget(self.canvas)
            self.canvas.deleteLater()
        self.placeholder.hide()
        figure = Figure(figsize=(7,5),layout="constrained")
        self.canvas = FigureCanvasQTAgg(figure)
        self.canvas_holder.addWidget(self.canvas)
        method = result["method"]
        if "coordinates" in result:
            ax = figure.add_subplot(111)
            xy = np.asarray(result["coordinates"])
            ax.scatter(xy[:,0],xy[:,1],s=2,c="#146f79",alpha=.55,rasterized=True)
            ax.set_xlabel(method+" 1")
            ax.set_ylabel(method+" 2")
            ax.set_title(f"{method} · n={len(xy):,}")
            rows = [{"parameter":k,"value":str(v)} for k,v in result["parameters"].items()]
        elif method == "FlowSOM":
            ax = figure.add_subplot(111)
            image = ax.imshow(np.asarray(result["medians"]),aspect="auto",cmap="viridis")
            ax.set_xticks(range(len(result["channels"])),result["channels"],rotation=45,ha="right")
            ax.set_yticks(range(len(result["metaclusters"])),[str(v) for v in result["metaclusters"]])
            ax.set_ylabel("Metacluster")
            figure.colorbar(image,ax=ax,label="Median transformed intensity")
            rows = [{"metacluster":int(c),"events":int(n)} for c,n in zip(result["metaclusters"],result["counts"])]
        elif "components" in result:
            ax,residual = figure.subplots(2,1,sharex=True,gridspec_kw={"height_ratios":[3,1]})
            x,observed,expected = [np.asarray(result[k]) for k in ["x","observed","expected"]]
            ax.step(x,observed,where="mid",color="#64748b",label="Observed")
            ax.plot(x,expected,color="#146f79",label="Fit")
            parts = np.asarray(result["components"])
            for i,name in enumerate(result["component_names"]):
                ax.plot(x,parts[:,i],label=name,alpha=.7)
            ax.legend(fontsize=8)
            ax.set_ylabel("Events / bin")
            residual.axhline(0,color="#64748b",linewidth=.8)
            residual.plot(x,observed-expected,color="#b25e25")
            residual.set_ylabel("Residual")
            residual.set_xlabel("log2 intensity" if method.startswith("dye") else "Linear DNA intensity")
            ax.set_title(method)
            rows = [{"statistic":k,"value":v} for k,v in result["summary"].items()]
        else:
            ax = figure.add_subplot(111)
            rows = result["rows"]
            x = [r["time_mid"] for r in rows]
            y = [np.nan if r["median"] is None else r["median"] for r in rows]
            ax.plot(x,y,color="#146f79")
            ax.fill_between(x,[np.nan if r["q25"] is None else r["q25"] for r in rows],
                            [np.nan if r["q75"] is None else r["q75"] for r in rows],color="#146f79",alpha=.18)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel(result["channels"][0]+" · median / IQR")
        self.canvas.draw()
        fill_table(self.table,rows)

    def export_result(self):
        if not self.result:
            return
        path,_ = QFileDialog.getSaveFileName(self,self.tr("导出结果", "Export results"),"analysis.json","JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                from pathlib import Path
                Path(path).write_text(json.dumps(json_clean(self.result),ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
            else:
                import pandas as pd
                r = self.result
                if "coordinates" in r:
                    xy = np.asarray(r["coordinates"])
                    rows = {"event_index":r["event_indices"],"dimension_1":xy[:,0],"dimension_2":xy[:,1]}
                elif "labels" in r:
                    rows = {"event_index":r["event_indices"],"metacluster":r["labels"],"som_node":r["som_nodes"]}
                elif "rows" in r:
                    rows = r["rows"]
                else:
                    rows = {"x":r["x"],"observed":r["observed"],"expected":r["expected"]}
                pd.DataFrame(rows).to_csv(path,index=False,encoding="utf-8-sig")
                from pathlib import Path
                Path(path+".metadata.json").write_text(json.dumps(json_clean({k:v for k,v in r.items()
                    if k not in {"coordinates","labels","event_indices","som_nodes","x","observed","expected","components","rows"}}),
                    ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as error:
            self.window.show_error(str(error))

    def export_figure(self):
        if not self.canvas:
            return
        path,_ = QFileDialog.getSaveFileName(self,self.tr("导出图形", "Export figure"),"analysis.pdf","PDF (*.pdf);;SVG (*.svg);;PNG (*.png)")
        if path:
            try:
                self.canvas.figure.savefig(path,dpi=300)
            except Exception as error:
                self.window.show_error(str(error))

    def cluster_gates(self):
        if self.result and self.result.get("method") == "FlowSOM":
            self.window.create_cluster_gates(self.result)
