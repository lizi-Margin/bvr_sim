@echo off
call "%~dp0Launch-Frontend.cmd" --map-version source-regional-horizon-v327@8d00e8c01c008c2dab680bab --aircraft F16 --quality high %*
exit /b %errorlevel%
