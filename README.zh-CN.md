# FlowAnalysis

[English](README.md) · 简体中文

本地运行的开源流式细胞分析桌面软件，面向 macOS 和 Windows，提供中英文界面。处理常规流式、已解混 FCS，以及有匹配参考数据的原始光谱数据。

当前为 **0.1.0 科研测试版**。实现和验证状态见 [验证记录](docs/VALIDATION.md)，安装方式见 [构建与安装](docs/BUILD.md)。功能范围不代表已与所有版本的 FlowJo 或各仪器软件达到数值等价。

## 功能

- FCS 2.0 / 3.0 / 3.1 读取、元数据查看、处理后子群 FCS 导出。
- 密度图、散点图、等高线、直方图和样本叠加。
- 矩形、多边形、椭圆、区间、象限、布尔门，父子层级、门定义编辑、门模板及样本组应用。
- 常规溢出矩阵补偿：读取 FCS 矩阵、CSV 导入、从有门控的单染正负对照估算。
- 原始光谱解混：导入参考谱或由对照建立参考谱，SVD 最小二乘求解、背景向量、可选 AF 谱、秩/条件数/重建残差检查。
- 全量群体计数、父比例/总比例、线性强度均值/中位数/标准差，CSV/XLSX 导出。
- UMAP、t-SNE、FlowSOM；随机种子、输入变换、抽样索引和参数随结果保留。
- 细胞周期探索拟合、染料稀释增殖拟合、时间分箱动力学、受限算术表达式派生参数。
- 96/384 孔板样本映射、组合图版及 PDF/SVG/PNG 导出。
- 可移植 .flowproj 项目、撤销重做、自动保存恢复副本、长任务取消。
- 导入 FlowJo WSP / GatingML，以 FlowKit 逐事件核对转换门；不支持的几何明确保留为当前样本的冻结群体。

## 本地运行

需要 Python 3.12；安装包用户无需另装 Python。

macOS / Linux 开发环境：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m flowanalysis
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m flowanalysis
```

打开内置合成演示：

```bash
python -m flowanalysis --demo
```

演示包含免疫表型、DNA、CFSE、时间和光谱参考数据，均明确标为模拟数据。公开真实 FCS 的下载及来源见 [测试数据说明](docs/TEST_DATA.md)。

## 使用流程

1. 导入 FCS，核查右侧的数据状态：原始常规、已补偿、原始光谱或已解混。未知状态不会自动进行补偿/解混。
2. 常规数据在“补偿”页导入/估算溢出矩阵；原始光谱数据在“光谱解混”页匹配检测器和参考成分。用于估计矩阵的对照应先建立正负群体门。
3. 在工作台选择通道和坐标变换，点击门工具，拖动边界/顶点后保存。选中父群体继续建子门。
4. “编辑所选门”可调整已有门；“分析 → 编辑门定义”提供包括无界阈值的完整参数编辑。
5. 进阶分析先选输入通道与参数。细胞周期、增殖、动力学各选一个信号通道；UMAP/t-SNE/FlowSOM 至少两个。
6. 从统计页导出结果；工作台将图形加入图版，组合导出。
7. 保存 .flowproj，原始事件、处理数据、门及结果存于同一项目，不依赖源 FCS 的原路径。

## 分析约定与限制

- 图形显示可抽样，门和描述统计始终使用完整群体。负值不会被默认截断。Log 显示不包含非正值。
- 输入 FCS 先由 FlowIO 处理增益、对数放大及时间步长；后续补偿与解混在相应线性检测空间进行。
- 溢出矩阵采用来源荧光为行、检测器为列，比例单位；光谱参考矩阵采用检测器为行、成分为列。
- 细胞周期为独立的 G1/G2 高斯与平滑均匀 S 期模型，**不是** Watson 或 Dean–Jett–Fox 的复刻。需先选择单细胞，并检查残差与排除事件。
- 增殖模型需要未分裂对照峰，默认每代减半，共享 log2 峰宽；不估计染料流失。所报告指数按估计前体数计算。
- 原始光谱解混依赖参考对照、采集设置和通道匹配，通用最小二乘结果不保证与厂家专有解混算法逐事件一致。
- FlowSOM 建立的事件索引门只适用于原样本；不能直接跨样本复制。
- 导入文件按严格模式读取；损坏或非标准 FCS 报错，不静默修改数值。

## 隐私与数据

分析在本地运行，无需云账号，不上传实验数据。公开源码仓库默认忽略 FCS、项目文件、证书、密钥及本地测试数据。公开数据只按其各自许可使用，来源和校验和独立记录。

## 开发与打包

```bash
python -m pytest
python -m ruff check src tests
python packaging/build.py
```

Mac 与 Windows 必须分别在对应操作系统上构建。个人本地使用无需购买发布证书；公开分发的签名/公证可后续配置。未签名包可能受到目标系统安全策略限制。构建文档将列出实测架构及最低版本。

## 开源许可

本项目采用 **GPL-3.0-only**。FlowSOM 及其部分依赖采用 GPL，完整分发版据此统一采用 GPLv3；早期设计中拟议的 BSD 自有代码许可已调整。各第三方库保留自己的许可和版权。

感谢 [FlowKit](https://github.com/whitews/FlowKit)、[FlowIO](https://github.com/whitews/FlowIO)、[FlowUtils](https://github.com/whitews/FlowUtils)、[FlowSOM](https://github.com/saeyslab/FlowSOM_Python)、Qt/PySide、PyQtGraph、NumPy、SciPy、scikit-learn、UMAP 和 Matplotlib。
