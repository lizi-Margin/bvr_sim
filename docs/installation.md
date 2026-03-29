# Installation Guide

这份文档专门讲如何安装和构建 `bvr-sim`。

如果你只是第一次体验项目，先看 [`docs/getting_started.md`](G:\bvr_sim\docs\getting_started.md)。

## 安装路径

这个项目有两条安装路径：

- 只用 Python 环境
- Python + C++ 混合环境

建议顺序是：

1. 先安装 Python 包
2. 跑通 Python smoke test
3. 再构建 C++ 后端

## 基础要求

- Python 3.8+
- `git`
- 网络可访问依赖仓库

如果要启用 C++ 后端，还需要：

- `cmake`
- 本地 C++ 编译器

Windows 建议：

- Visual Studio 2022 或带 MSVC 的 Build Tools
- CMake 已加入 PATH

Linux 建议：

- `gcc` 或 `clang`
- `make` 或 Ninja

## Python 安装

在仓库根目录执行：

```bash
pip install -e .
```

这一步会安装 [`pyproject.toml`](G:\bvr_sim\pyproject.toml) 中声明的依赖，并把当前仓库以 editable mode 安装。

安装完成后建议立即执行：

```bash
python tests/test_py.py
```

如果这一步能跑通，说明 Python 环境基本可用。

## Windows: 构建 C++ 后端

在仓库根目录执行：

```powershell
bvr_sim\build_windows.bat
```

这个脚本会做三件事：

1. 检查并拉取 `bvr_sim/src_cxx/extern/` 下的三方依赖
2. 使用 CMake 配置工程
3. 构建并安装产物到 `bvr_sim/install/`

当前脚本会拉取的外部依赖包括：

- Eigen
- pybind11
- cpptrace

构建完成后，建议依次验证：

```bash
python tests/cpp_unit_tests.py
python tests/test_cpp.py
```

## Linux: 构建 C++ 后端

在仓库根目录执行：

```bash
bash bvr_sim/build_linux.sh
```

这会完成和 Windows 脚本相同的目标：

- 拉取外部依赖
- 配置 CMake
- 构建 Release 版本
- 安装到 `bvr_sim/install/`

构建完成后建议执行：

```bash
python tests/cpp_unit_tests.py
python tests/test_cpp.py
```

## 完整验证

如果你想一次性重建并跑完主要测试：

```bash
python tests/test_everything.py
```

它会：

1. 重建 C++ 后端
2. 重新安装包
3. 跑 C++ unit tests
4. 跑 C++ smoke test
5. 跑 Python smoke test

## 目录说明

安装和构建后，常见目录含义如下：

- `bvr_sim/build/`: CMake 构建目录
- `bvr_sim/install/`: 原生安装产物
- `bvr_sim/install/lib/`: Python 原生扩展和相关库
- `bvr_sim/install/bin/`: 可执行文件，如 unit tests

这些目录都是生成产物，不要手工修改。

## 常见问题

### `bvr_sim_cpp` 导入失败

优先检查：

- 是否已经执行过构建脚本
- `bvr_sim/install/lib/` 下是否存在 `.pyd` 或 `.so`
- Python 是否正在使用当前仓库对应的安装环境

相关入口见 [`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py)。

### C++ unit test 可执行文件不存在

执行：

```bash
python tests/cpp_unit_tests.py
```

如果提示 `bvr_sim/install/bin/bvr_sim_unit_tests(.exe)` 不存在，说明 C++ 构建没有完成。

### Windows 下 CMake 配置失败

通常先检查：

- 是否安装了 MSVC
- 是否安装了 CMake
- 是否在合适的开发者命令行或 PowerShell 中执行

### Linux 下构建失败

通常先检查：

- 编译器是否存在
- 构建工具是否存在
- 网络是否能拉取依赖仓库

## 建议的最小交付流程

如果你是项目维护者，想让别人最快试用：

1. 让对方先执行 `pip install -e .`
2. 让对方先执行 `python tests/test_py.py`
3. 对方确认可用后，再引导其构建 C++ 后端
