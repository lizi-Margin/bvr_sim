@echo off
setlocal
cd /d "%~dp0.."
python -m bvr_game play --runtime game/runtime-ui.json %*
