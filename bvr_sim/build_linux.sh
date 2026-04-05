#!/bin/bash
# BVR Sim C++ Build Script for Linux (GCC/Clang)
# Usage: ./build_linux.sh [clean]
# This script automatically clones C++ dependencies before building

set -e

BUILD_DIR="build"
CMAKE_BUILD_TYPE="Release"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "BVR Sim C++ Build Script (Linux)"
echo "========================================"
echo ""

# Function to clone or update external dependencies
clone_or_update_extern() {
    local extern_dir="${SCRIPT_DIR}/src_cxx/extern"

    echo "Setting up C++ external dependencies..."
    echo ""

    # Eigen
    if [ ! -d "$extern_dir/eigen" ]; then
        echo "Cloning Eigen..."
        git clone --depth 1 https://gitlab.com/libeigen/eigen.git "$extern_dir/eigen"
    else
        echo "Eigen already exists at $extern_dir/eigen"
    fi

    # pybind11
    if [ ! -d "$extern_dir/pybind11" ]; then
        echo "Cloning pybind11..."
        git clone --depth 1 https://github.com/pybind/pybind11.git "$extern_dir/pybind11"
    else
        echo "pybind11 already exists at $extern_dir/pybind11"
    fi

    # cpptrace
    if [ ! -d "$extern_dir/cpptrace" ]; then
        echo "Cloning cpptrace..."
        git clone --depth 1 https://github.com/jeremy-rifkin/cpptrace.git "$extern_dir/cpptrace"
    else
        echo "cpptrace already exists at $extern_dir/cpptrace"
    fi

    echo ""
}

clone_or_update_extern

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
