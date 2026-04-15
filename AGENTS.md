# Repository Guidelines

## Project Structure & Module Organization
`bvr_sim/` is the main package. Top-level Python entry points such as `bvr_env.py` and `bvr_env_cpp.py` wrap the simulation backends. Core Python simulation logic lives under `bvr_sim/src_py/` (`simulator/`, `reward/`, `baseline_opponents/`), while native code lives under `bvr_sim/src_cxx/`. Build outputs land in `bvr_sim/build/` and `bvr_sim/install/`; treat both as generated artifacts. Tests and runnable configs live in `tests/`, and integration examples live in `example/`.

## Build, Test, and Development Commands
Use `pip install -e .` for an editable Python install from the repo root.

`python tests/test_py.py` runs the Python environment smoke test with `tests/demo_config.json`.

`python tests/test_cpp.py` runs the C++-backed smoke test with `tests/demo_config_cpp.jsonc`.

`python tests/cpp_unit_tests.py` runs the compiled C++ unit-test executable from `bvr_sim/install/bin/`.

`python run_tests.py` rebuilds the native extension and runs the full test suite.

For native builds only, run `bvr_sim/build_windows.bat` on Windows or `bash bvr_sim/build_linux.sh` on Linux.

## Coding Style & Naming Conventions
Follow the existing style: 4-space indentation in Python, `snake_case` for functions and modules, `PascalCase` for classes. C++ files use `.cxx`/`.hxx`; keep naming aligned with adjacent code and prefer small, focused changes. No formatter or linter is configured in `pyproject.toml`, so match local conventions carefully and keep imports and whitespace tidy.

## Testing Guidelines
Add tests beside the nearest existing suite in `tests/`. Name Python tests `test_*.py`. When changing C++ code, run `python tests/cpp_unit_tests.py` after rebuilding; when changing environment behavior, run the corresponding smoke test plus `python run_tests.py` before opening a PR.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, and `refactor:`. Keep subjects imperative and specific, for example `fix: validate missile parameter keys`. PRs should describe the scenario affected, list commands run, and attach screenshots or Tacview artifacts only when rendering, replay, or benchmark output changes.

## Generated Files & Config
Do not hand-edit files under `bvr_sim/build/`, `bvr_sim/install/`, `benchmark_logs/`, or `test_logs/`. Keep JSON/JSONC example configs reproducible, and document any new dependency or external native library requirement in `README.md` or the build scripts.
