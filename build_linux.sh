#!/bin/bash
# BVR Sim C++ Build Script for Linux (GCC/Clang)
# Usage: ./build_linux.sh [clean]

set -e

BUILD_DIR="build"
CMAKE_BUILD_TYPE="Release"

echo "========================================"
echo "BVR Sim C++ Build Script (Linux)"
echo "========================================"
echo ""

# Create build directory
if [ ! -d "$BUILD_DIR" ]; then
    echo "Creating build directory..."
    mkdir -p "$BUILD_DIR"
fi

# Navigate to build directory
cd "$BUILD_DIR"

# Configure CMake
echo "Configuring CMake..."
cmake .. -DCMAKE_BUILD_TYPE=$CMAKE_BUILD_TYPE

echo ""

# Build project
echo "Building project ($CMAKE_BUILD_TYPE)..."
cmake --build . -- -j$(nproc)

echo ""

cmake --install . --prefix ../install --config $CMAKE_BUILD_TYPE

# Navigate back
cd ..

echo "========================================"
echo "Build completed successfully!"
echo "========================================"
