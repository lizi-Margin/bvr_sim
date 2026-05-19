# Third-Party Licenses

This file summarizes notable third-party code and resources bundled with or used by `bvr-sim`. It is not a replacement for the original license texts shipped with each dependency.

## JSBSim

- License: GNU Lesser General Public License v2.1
- Website: https://jsbsim.sourceforge.net/
- Notes: JSBSim source/resources are used by the flight dynamics path. Preserve upstream copyright notices and comply with LGPLv2.1 when distributing modified copies or linked binaries.

## Eigen

- License: Mozilla Public License v2.0
- Website: https://eigen.tuxfamily.org/
- Notes: Eigen is used as a C++ math dependency. Preserve upstream notices; modifications to Eigen files remain subject to MPL-2.0.

## pybind11

- License: BSD 3-Clause
- Website: https://github.com/pybind/pybind11
- Notes: Used for Python/C++ bindings. Preserve upstream copyright and license notices.

## cpptrace

- License: MIT
- Website: https://github.com/jeremy-rifkin/cpptrace
- Notes: Used for native stack traces. Preserve upstream copyright and license notices.

## Web Frontend Dependencies

The web visualization uses Node/npm dependencies declared in [`web/package.json`](web/package.json) and locked in [`web/package-lock.json`](web/package-lock.json). Review the lockfile before publishing binary or hosted distributions.

## Runtime Assets

Runtime assets under `bvr_sim/resources/` may include upstream aircraft definitions, engine definitions, textures, meshes, and project-specific simulation parameters. Keep source notices beside those files and review asset-level license files before publishing release archives or wheels.
