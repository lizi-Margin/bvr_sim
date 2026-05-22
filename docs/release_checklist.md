# Open Source Release Checklist

This checklist tracks the remaining work before making the repository public.

## Required Before Public Release

- Confirm the public repository URL in `CITATION.cff` remains `https://github.com/lizi-Margin/bvr_sim`.
- Confirm `LICENSE` contains the unmodified GNU GPLv3 text.
- Review third-party bundled code and resources under `bvr_sim/resources/` and `bvr_sim/src_cxx/extern/`.
- Remove or untrack generated logs, benchmark outputs, local reports, and personal research drafts after maintainer approval.
- Run the release validation commands:

```bash
python tests/test_py.py
python tests/test_cpp.py
python tests/cpp_unit_tests.py
python run_tests.py
npm --prefix bvr_sim/web run build
```

## Paper Preparation

- Move paper sources into a dedicated `paper/` or `docs/paper/` directory.
- Keep LaTeX build artifacts such as `.aux`, `.log`, `.out`, and `.pdf` out of git unless they are intentional release artifacts.
- Use benchmark CSV files as reproducible inputs or regenerate figures from scripts.
