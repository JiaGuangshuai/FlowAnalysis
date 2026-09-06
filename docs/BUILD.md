# 构建与本地安装

使用 Python 3.12，按 README 安装开发依赖后执行 `python packaging/build.py`。安装包包含 Python 和分析依赖，用户无需编程环境。

- **macOS arm64**：输出 `dist/FlowAnalysis.app` 和 ZIP。解压后把 `.app` 拖到“应用程序”或 `~/Applications`。免费 ad-hoc 签名不是 Apple Developer ID 签名，未公证；网络下载的包可能需要在系统设置中允许打开。
- **Windows x64**：输出 ZIP，完整解压后运行 `FlowAnalysis.exe`，不要单独移动 EXE。可选 Inno Setup 6 构建当前用户安装包。
- 必须在目标系统分别构建。`.github/workflows/build.yml` 在真实 Mac / Windows 环境运行测试、打包和独立程序验证。

Apple Silicon 已本机实测，Intel Mac 需另行构建和验证。依赖以 macOS 13+ / Windows 10 或更新版本为目标，最低系统版本仍需实机验证。

## 证书与许可

自己运行本地版本无需购买证书。后续公开分发可配置 Apple Developer ID + notarization、Windows Authenticode。证书和密码不要加入仓库；当前工作流不包含付费签名。

完整分发采用 GPL-3.0-only。包内 `licenses` 目录提供依赖版本及可获取的第三方许可副本，Qt 以动态库分发。源码和构建脚本应与二进制版本一起发布。

## 本机开发环境

云同步的 Documents/Desktop 可能产生插件占位和冲突副本，建议把虚拟环境放在非同步目录。本次本机 `.venv` 指向 `~/.cache/flowanalysis-venv`，不随仓库发布。
