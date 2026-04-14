---
name: test
description: Run unified test suite for BVR Sim. One-click testing with automatic build and validation.
---

# BVR Sim Test Suite

Run comprehensive tests automatically from the project root.

## Quick Start

| Command | Description |
|---------|-------------|
| `/test` | Run full test suite (build + all tests) |

## What Gets Run

The unified test suite (`run_tests.py`) does:

1. **Build** C++ components (Windows: `build_windows.bat`, Linux: `build_linux.sh`)
2. **Import** local `bvr_sim` package directly (no pip install)
3. **C++ unit tests** - Low-level C++ functionality
4. **C3Utils unit tests** - C3Utils library tests
5. **C++ core tests** - C++ backend validation
6. **Python core tests** - Python backend validation

## Benefits

- **Faster test runs** - No pip install overhead, direct import of local changes
- **Instant feedback** - Test local modifications immediately after build
- **Simple workflow** - Single command from project root

## Requirements

- Windows: MSVC build tools
- Linux: GCC or Clang
- Python 3.8+

## Usage

```bash
# From project root, run all tests
python run_tests.py

# Or use the Claude Code /test skill
/test
```

## Troubleshooting

- **Build fails**: Check compiler is installed and in PATH
- **Import errors**: Ensure `build_windows.bat` completed successfully (looks for `bvr_sim_cpp.pyd` in `bvr_sim/`)
- **C++ tests fail**: Verify Eigen and pybind11 were downloaded during build
