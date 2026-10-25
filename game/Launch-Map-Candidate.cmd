@echo off
setlocal
cd /d "%~dp0.."
python -m bvr_game play --mission training --aircraft F16 --quality high %*
if errorlevel 1 pause
endlocal
