@echo off
cd /d "%~dp0.."
python -m bvr_game play --map game/maps/training_range_v3/generated-map.json --aircraft F22 --quality high
if errorlevel 1 pause
