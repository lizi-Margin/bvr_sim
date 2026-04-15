cmake_minimum_required(VERSION 3.15)
project(bvr_sim_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MSVC)
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} /FS")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /FS")
endif()

if(DEFINED SKBUILD)
    set(_bvr_sim_native_opt_default OFF)
    set(_bvr_sim_build_tests_default OFF)
    set(_bvr_sim_install_dev_artifacts_default OFF)
else()
    set(_bvr_sim_native_opt_default ON)
    set(_bvr_sim_build_tests_default ON)
    set(_bvr_sim_install_dev_artifacts_default ON)
endif()

option(BVR_SIM_ENABLE_NATIVE_OPTIMIZATIONS "Enable CPU-specific compiler optimizations" ${_bvr_sim_native_opt_default})
option(BVR_SIM_BUILD_TESTS "Build native test executables" ${_bvr_sim_build_tests_default})
option(BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS "Install static libraries and native test executables" ${_bvr_sim_install_dev_artifacts_default})
set(BVR_SIM_PYTHON_MODULE_DESTINATION "lib" CACHE STRING "Install destination for the Python extension module")

# # Set Debug mode for debugging symbols and cpptrace output
# set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
# if(NOT CMAKE_BUILD_TYPE)
#     if(MSVC)
#         set(CMAKE_CXX_FLAGS_DEBUG "/Zi /O2" CACHE STRING "Debug flags" FORCE)
#     elseif(UNIX AND NOT APPLE)
#         set(CMAKE_CXX_FLAGS_DEBUG "-g -O2 -march=native" CACHE STRING "Debug flags" FORCE)
#     endif()
# endif()

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose the type of build." FORCE)
endif()


if (CMAKE_BUILD_TYPE STREQUAL "Release")
    if (MSVC)
        set(CMAKE_CXX_FLAGS_RELEASE "/Zi /O2 /Ob2 /Oi /Ot /GL /fp:fast /arch:AVX2 /wd4100")
    else ()
        set(CMAKE_CXX_FLAGS_RELEASE "-g -O3 -Wno-unused-parameter")
    endif()
endif()


message(STATUS "Building bvr_sim_cpp for ${CMAKE_SYSTEM_NAME}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Python module install destination: ${BVR_SIM_PYTHON_MODULE_DESTINATION}")
message(STATUS "Native optimizations enabled: ${BVR_SIM_ENABLE_NATIVE_OPTIMIZATIONS}")
message(STATUS "Build native tests: ${BVR_SIM_BUILD_TESTS}")
message(STATUS "Install development artifacts: ${BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS}")



add_subdirectory("src_cxx")
