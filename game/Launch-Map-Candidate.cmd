@echo off
call "%~dp0Launch-Frontend.cmd" --mission training --aircraft F16 --quality high %*
exit /b %errorlevel%
