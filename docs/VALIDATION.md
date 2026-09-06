# 验证记录 / Validation

2026-09-06，FlowAnalysis 0.1.0。实测：macOS 26.6.2、Apple Silicon arm64、Python 3.12.14、PySide6 6.8.3。依赖版本见 `packaging/requirements-macos-arm64.lock`。

[最终构建记录](https://github.com/JiaGuangshuai/FlowAnalysis/actions/runs/34032432843)：macOS 和 Windows 两个平台均通过 **29 项测试**，并通过独立程序 UI + 后台算法检查。发布代码提交为 `708f936c0b7136f8394b5f58c2a0103f502a0d95`。

## 完成的检查

- 补偿正负真值回收、通道重排、防重复处理；带背景光谱回收、秩不足拒绝、参考谱估计。
- 父子/布尔门、门边界、象限互斥、空群体、坐标变换、受限派生表达式、FCS 与项目往返、门模板引用重映射。
- 固定事件索引和种子的 UMAP / t-SNE 可重复性；FlowSOM 抽样训练后全事件映射及已知双群体区分。
- 已知细胞周期混合物及偏离真实峰值的初始参数；已知增殖代数混合物与独立指数算例；动力学空窗、末尾事件与零基线拒绝。
- GUI 的 7 个页面、中英切换、全部图形模式、门工具、建门撤销重做、图版预览、孔板分配。
- 公开真实 FCS 读取数值与 FlowKit 一致。
- 3 个公开 8 色样本共 **859,431 个事件**；**42 个门**转换后与 FlowKit 参考成员逐事件一致，无冻结回退。
- 公开光谱数组：10,000 个事件、48 检测器、33 成分。SVD OLS 对独立参考最大绝对误差约 **1.68 × 10⁻⁸**，矩阵条件数约 63.78。
- 源码程序与 Mac 独立 `.app` 均完成 UI 和后台进程实测，实际运行 FCS、项目读写、门控、补偿、光谱解混、UMAP、t-SNE、FlowSOM、细胞周期、增殖、动力学。

## 限制

这些检查不代表与所有 FlowJo 版本、插件和仪器软件完全等价。细胞周期采用独立探索模型；光谱数据为公开数组及转换文件，尚未覆盖多个厂商完整对照采集流程。工作区导入不含插件结果与图版；不支持的门型明确保留为原样本事件索引，不能跨样本复制。

Mac 已本机核对，最低系统版本、Intel Mac、极大数据和各厂家非标准 FCS 尚未全面覆盖。Windows x64 已在 GitHub Actions 的 Windows 环境完成测试、安装包构建及独立程序验证；尚未在用户个人 Windows 电脑上实测。

## 重现

```bash
python scripts/download_test_data.py
python -m pytest -q
python -m ruff check src tests scripts packaging
python -m flowanalysis --self-test source-smoke.json
python packaging/build.py
```

无显示环境设置 `QT_QPA_PLATFORM=offscreen`。Mac 独立程序测试：

```bash
dist/FlowAnalysis.app/Contents/MacOS/FlowAnalysis --self-test frozen-smoke.json
```

首次运行 UMAP 等会进行 JIT 编译，慢于后续运行；任务可取消。上游 FlowSOM/MuData 兼容性告警不影响当前回归算例。
