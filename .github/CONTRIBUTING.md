# Contributing

Thanks for improving `bvr-sim`. This repository contains both Python environment code and a native C++ backend, so keep changes scoped and test the backend that your change touches.

## Development Setup

Install the package from the repository root:

```bash
pip install -e .
```

For native backend work, build the C++ extension first:

```bash
bvr_sim\build_windows.bat
```

or on Linux:

```bash
bash bvr_sim/build_linux.sh
```

## Tests

Use the smallest test that covers your change:

```bash
python scripts/tests/test_py.py
python scripts/tests/test_cpp.py
python scripts/tests/cpp_unit_tests.py
```

Before a larger pull request, run:

```bash
python scripts/run_tests.py
```

If you change the web visualization, also run:

```bash
python scripts/tests/test_web_bridge_smoke.py
npm --prefix bvr_sim/web run build
```

## Code Style

- Match the existing style in the touched files.
- Python uses 4-space indentation and `snake_case`.
- C++ files use `.cxx` and `.hxx`; keep changes local to the relevant module.
- Do not commit generated files from `bvr_sim/build/`, `bvr_sim/install/`, `benchmark_logs/`, or `test_logs/`.

## Pull Requests

Include:

- The scenario or behavior affected.
- The tests or build commands you ran.
- Any compatibility notes for configs, wrappers, or visualization output.
