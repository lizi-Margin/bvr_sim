@echo off
call "%~dp0Launch-Frontend.cmd" --map game/maps/training_range_v3/generated-map.json --aircraft F22 --quality high %*
exit /b %errorlevel%
