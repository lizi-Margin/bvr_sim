@echo off
REM BVR Sim C++ Build Script for Windows (MSVC)
REM Usage: build_windows.bat [clean]

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
