@echo off
setlocal
cd /d "%~dp0.."
python -X utf8 -m bvr_game.launcher play --runtime game/runtime-ui.json %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
endlocal & exit /b %exitCode%
