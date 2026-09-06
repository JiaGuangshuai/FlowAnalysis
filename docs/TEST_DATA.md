# 公开测试数据 / Public test data

来源：[FlowKit 官方数据目录](https://github.com/whitews/FlowKit/tree/master/data)，附上游 BSD-3-Clause LICENSE。下载 URL、大小和 SHA-256 见 `scripts/test-data-manifest.json`，下载脚本会核对校验和。数据保留本地，不提交 Git。

## 本机直接测试

文件已准备到 `local-data/public-flowkit/`：

| 文件 | 用途 |
|---|---|
| 公开8色流式测试.flowproj | 优先打开：3 个真实样本、补偿通道和 42 个参考门 |
| 公开光谱测试.flowproj | 10,000 个事件、48 检测通道、33 参考成分；原始和解混后样本 |
| 101_DEN084Y5_15_E01_008_clean.fcs | 原始下载，290,172 个事件，从导入开始操作 |
| 101_DEN084Y5_15_E03_009_clean.fcs | 原始下载，283,969 个事件，组比较和叠加 |
| 101_DEN084Y5_15_E05_010_clean.fcs | 原始下载，285,290 个事件 |
| den_comp_labeled.csv | 配套常规补偿矩阵，补齐行列标签，数值不变 |
| 8_color_ICS.wsp / .xml | 上游 FlowJo 工作区 / GatingML 策略 |
| public_spectral_fixture_converted.fcs | **由公开 NPY 数组转换的 FCS**，不是原始仪器导出文件 |
| spectral_reference_labeled.csv | 光谱数据的 48 × 33 参考矩阵，可直接导入解混页 |
| test_data_diamond_01.fcs | 人工几何数据，用于门边界验证，非生物观测 |

在“文件 → 打开项目”选择 `.flowproj`；在“文件 → 导入 FCS”选择 `.fcs`。

8 色工程中，带 `[补偿矩阵标识]` 的通道列是参考工作区使用的补偿值，原列保留原始值；参考门指向对应补偿列和坐标变换。选择横纵轴时请辨认列名。

光谱测试成分沿用上游矩阵行的检测器标识，**未据此推断抗体或细胞身份**。该测试集不包含完整单染对照 FCS；配套矩阵不能用于其他实验。

细胞周期和增殖先使用“文件 → 打开模拟演示”中的 DNA / CFSE 通道；公开 8 色样本不保证具有这些标记。

## 在另一台电脑准备

安装源码开发环境后：

```bash
python scripts/download_test_data.py
python scripts/prepare_test_projects.py
```

首次下载约 66 MB，可移植工程另占磁盘空间。转换光谱 FCS 使用浮点编码，可能与 float64 NPY 略有精度差异；光谱回归直接比较 NPY。

光谱来源：[FlowKit spectral_data](https://github.com/whitews/FlowKit/tree/master/data/spectral_data)；通道顺序来自其 [test_config.py](https://github.com/whitews/FlowKit/blob/master/tests/test_config.py)。
