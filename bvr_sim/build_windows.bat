@echo off
REM BVR Sim C++ Build Script for Windows (MSVC)
REM Usage: build_windows.bat [clean]
REM This script automatically clones C++ dependencies before building

setlocal

set BUILD_DIR=build
@REM set BUILD_TYPE=Debug
set BUILD_TYPE=Release
set CMAKE_GENERATOR="Visual Studio 17 2022"
set CMAKE_ARCH=x64

echo ========================================
echo BVR Sim C++ Build Script (Windows)
echo ========================================
echo.

REM Get script directory
for %%I in ("%~dp0.") do set SCRIPT_DIR=%%~fI

REM ========================================
REM Clone or update external dependencies
REM ========================================

set EXTERN_DIR=%SCRIPT_DIR%\src_cxx\extern
if not exist "%EXTERN_DIR%" mkdir "%EXTERN_DIR%"

echo Setting up C++ external dependencies...
echo.

REM Eigen
if not exist "%EXTERN_DIR%\eigen" (
    echo Cloning Eigen...
    cd /d "%EXTERN_DIR%"
    git clone --depth 1 https://gitlab.com/libeigen/eigen.git eigen
    if errorlevel 1 (
        echo Failed to clone Eigen!
        cd /d "%SCRIPT_DIR%"
        exit /b 1
    )
) else (
    echo Eigen already exists at %EXTERN_DIR%\eigen
)

REM pybind11
if not exist "%EXTERN_DIR%\pybind11" (
    echo Cloning pybind11...
    cd /d "%EXTERN_DIR%"
    git clone --depth 1 https://github.com/pybind/pybind11.git pybind11
    if errorlevel 1 (
        echo Failed to clone pybind11!
        cd /d "%SCRIPT_DIR%"
        exit /b 1
    )
) else (
    echo pybind11 already exists at %EXTERN_DIR%\pybind11
)

REM cpptrace
if not exist "%EXTERN_DIR%\cpptrace" (
    echo Cloning cpptrace...
    cd /d "%EXTERN_DIR%"
    git clone --depth 1 https://github.com/jeremy-rifkin/cpptrace.git cpptrace
    if errorlevel 1 (
        echo Failed to clone cpptrace!
        cd /d "%SCRIPT_DIR%"
        exit /b 1
    )
) else (
    echo cpptrace already exists at %EXTERN_DIR%\cpptrace
)

echo.


REM Return to script directory
cd /d "%SCRIPT_DIR%"

REM ========================================
REM CMake Build
REM ========================================

REM Create build directory
if not exist %BUILD_DIR% (
    echo Creating build directory...
    mkdir %BUILD_DIR%
)

REM Navigate to build directory
cd %BUILD_DIR%

REM Configure CMake
echo Configuring CMake...
cmake .. -G %CMAKE_GENERATOR% -A %CMAKE_ARCH%
if %ERRORLEVEL% neq 0 (
    echo CMake configuration failed!
    cd ..
    exit /b 1
)
echo.

REM Build project
echo Building project (%BUILD_TYPE%)...
cmake --build . --config %BUILD_TYPE%
if %ERRORLEVEL% neq 0 (
    echo Build failed!
    cd ..
    exit /b 1
)
echo.

cmake --install . --prefix ../install --config %BUILD_TYPE%

REM Navigate back
cd ..

echo ========================================
echo Build completed successfully!
echo ========================================

endlocal
