# BVR Sim Mission

Compact overview of the BVR (Beyond Visual Range) air-combat scenario used by UHRL.

## Quick Start
### Pure Python Environment
```bash
python main.py --cfg MISSION/bvr_sim/conf_system/random-1v1-test.jsonc
```
Runs the lightest scenario to validate environment wiring after code changes.

### C++ & Python Hybrid Environment
```bash
git clone --recurse-submodules https://github.com/lizi-Margin/UHRL.git
# git submodule update --init --recursive

cd MISSION/bvr_sim/
./build_windows.bat
./build_linux.sh
cd ../..

python ./test.py
```