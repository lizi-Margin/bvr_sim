# ============================================================================
# Find Required Packages
# ============================================================================
# Use local Eigen
set(Eigen3_DIR "${CMAKE_CURRENT_SOURCE_DIR}/extern/eigen")
if(NOT EXISTS "${Eigen3_DIR}")
    message(FATAL_ERROR "Eigen3 not found at ${Eigen3_DIR}")
endif()
add_subdirectory("${Eigen3_DIR}" Eigen3_build EXCLUDE_FROM_ALL)
message(STATUS "Using local Eigen3 at: ${Eigen3_DIR}")

# Use local pybind11
set(pybind11_DIR "${CMAKE_CURRENT_SOURCE_DIR}/extern/pybind11")
if(NOT EXISTS "${pybind11_DIR}")
    message(FATAL_ERROR "pybind11 not found at ${pybind11_DIR}")
endif()
add_subdirectory("${pybind11_DIR}" pybind11_build)
message(STATUS "Using local pybind11 at: ${pybind11_DIR}")

# Use local cpptrace
set(cpptrace_DIR "${CMAKE_CURRENT_SOURCE_DIR}/extern/cpptrace")
if(NOT EXISTS "${cpptrace_DIR}")
    message(FATAL_ERROR "cpptrace not found at ${cpptrace_DIR}")
endif()
set(CPPTRACE_BUILD_TESTING OFF CACHE BOOL "Disable cpptrace testing" FORCE)
set(CPPTRACE_BUILD_BENCHMARKING OFF CACHE BOOL "Disable cpptrace benchmarking" FORCE)
set(CPPTRACE_BUILD_TOOLS OFF CACHE BOOL "Disable cpptrace tools" FORCE)
add_subdirectory("${cpptrace_DIR}" cpptrace_build EXCLUDE_FROM_ALL)
message(STATUS "Using local cpptrace at: ${cpptrace_DIR}")

# ============================================================================
# c3utils Configuration
# ============================================================================
add_subdirectory(c3utils)

# ============================================================================
# JSBSim Configuration
# ============================================================================

set(JSBSIM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/extern/jsbsim")
set(JSBSIM_SRC_DIR "${JSBSIM_ROOT}/src")

if(NOT EXISTS "${JSBSIM_SRC_DIR}")
    message(FATAL_ERROR "JSBSim source directory not found at ${JSBSIM_SRC_DIR}")
endif()

message(STATUS "JSBSim source directory: ${JSBSIM_SRC_DIR}")

# Add JSBSim as subdirectory to build as static library
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build JSBSim as static library" FORCE)
set(BUILD_PYTHON_MODULE OFF CACHE BOOL "Disable JSBSim Python module" FORCE)
set(BUILD_DOCS OFF CACHE BOOL "Disable JSBSim documentation" FORCE)
# add_subdirectory("${JSBSIM_ROOT}" jsbsim_build)
add_subdirectory("${JSBSIM_ROOT}" jsbsim_build EXCLUDE_FROM_ALL)

# ============================================================================
# C++ Source Files
# ============================================================================

set(BVR_SIM_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/so_pool.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/bsl_pool.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/core.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/resource_paths.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/global_config.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/cmd_handler.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/trace.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_types.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_snapshot_builder.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_command_queue.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_bridge.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/embedded_web_server.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/simulator.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/register.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/unit_factory.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fighter.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fdm/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fdm/jsbsim_fdm.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fdm/simple_fdm.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fc/fc_old.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fc/flight_controller_params.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/data_obj.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/weapon_factory.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/pylon_manager.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/ground/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/ground/aa.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/ground/ground_static_target.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/ground/slamraam.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/aim120c.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/mmodelA.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/missile_aerodynamics.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/param_store.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm/generic_missile_fdm.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/sense/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/sense/awacs.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/sense/rws.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/sense/radar.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline_opponents/base.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline_opponents/mad.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline_opponents/standoff.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline_opponents/tactical.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline_opponents/straight_line.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/rl/observation_space.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/rl/reward_components.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/rl/reward_manager.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/rl/rl_manager.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/rubbish_can/set_env.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/pybind11_bindings.cxx"
)

# ============================================================================
# Include Directories
# ============================================================================

set(BVR_SIM_INCLUDE_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fdm"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm"
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fc"
    "${CMAKE_CURRENT_SOURCE_DIR}/rl"
    "${CMAKE_CURRENT_SOURCE_DIR}/extern/SimpleJSON"
    "${CMAKE_CURRENT_SOURCE_DIR}/extern/websocketpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/extern/asio/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/extern/cpptrace/include"
    "${Eigen3_DIR}"
    "${JSBSIM_SRC_DIR}"
    "${JSBSIM_SRC_DIR}/initialization"
    "${JSBSIM_SRC_DIR}/input_output"
    "${JSBSIM_SRC_DIR}/math"
    "${JSBSIM_SRC_DIR}/models"
    "${JSBSIM_SRC_DIR}/simgear"
    "${JSBSIM_SRC_DIR}/simgear/io/iostreams"
    "${JSBSIM_SRC_DIR}/simgear/magvar"
    "${JSBSIM_SRC_DIR}/simgear/misc"
    "${JSBSIM_SRC_DIR}/simgear/props"
    "${JSBSIM_SRC_DIR}/simgear/structure"
    "${JSBSIM_SRC_DIR}/simgear/xml"
    "${JSBSIM_SRC_DIR}/utilities"
    "${JSBSIM_SRC_DIR}/GeographicLib"
)


# ============================================================================
# Compiler-Specific Settings
# ============================================================================

function(set_compiler_params target_name)
    if(MSVC)
        # Windows MSVC
        target_compile_options(${target_name} PRIVATE /W4 /WX- /wd4819)
        target_compile_definitions(${target_name} PRIVATE _USE_MATH_DEFINES)

        # Add debug symbols for Debug builds
        if(CMAKE_BUILD_TYPE MATCHES Debug)
            target_compile_options(${target_name} PRIVATE /Zi /O2)
        endif()
            target_compile_options(${target_name} PRIVATE /Zi)

        set_target_properties(${target_name} PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
            RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
        )

        message(STATUS "MSVC detected: Configuring for Windows")

    elseif(UNIX AND NOT APPLE)
        # Linux GCC/Clang
        # target_compile_options(${target_name} PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(${target_name} PRIVATE -Wall)
        target_compile_options(${target_name} PRIVATE -fPIC)

        # Add debug symbols for Debug builds
        if(CMAKE_BUILD_TYPE MATCHES Debug)
            target_compile_options(${target_name} PRIVATE -g -O2)
        endif()
        target_compile_options(${target_name} PRIVATE -g)
        if(BVR_SIM_ENABLE_NATIVE_OPTIMIZATIONS)
            target_compile_options(${target_name} PRIVATE -march=native)
        endif()

        set_target_properties(${target_name} PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
            RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
        )

        # # Set output directory for Linux
        # set_target_properties(${target_name} PROPERTIES
        #     LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
        # )

        message(STATUS "Linux detected: Configuring for GCC/Clang")

    elseif(APPLE)
        # macOS Clang
        target_compile_options(${target_name} PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(${target_name} PRIVATE -fPIC)

        message(STATUS "macOS detected: Configuring for Clang")
    endif()
endfunction(set_compiler_params target_name)



# ============================================================================
# Create PyBind11 Module
# ============================================================================
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
message(STATUS "Python3 Version: ${Python3_VERSION}")
message(STATUS "Python3 Include: ${Python3_INCLUDE_DIRS}")
if(DEFINED Python3_LIBRARIES)
    message(STATUS "Python3 Library: ${Python3_LIBRARIES}")
endif()

pybind11_add_module(bvr_sim_cpp ${BVR_SIM_SOURCES})
target_include_directories(bvr_sim_cpp PRIVATE ${BVR_SIM_INCLUDE_DIRS})
target_include_directories(bvr_sim_cpp PRIVATE ${Python3_INCLUDE_DIRS})
target_include_directories(bvr_sim_cpp PRIVATE ${EIGEN3_INCLUDE_DIR})
target_link_libraries(bvr_sim_cpp PRIVATE c3utils)
target_link_libraries(bvr_sim_cpp PRIVATE cpptrace::cpptrace)
target_link_libraries(bvr_sim_cpp PRIVATE libJSBSim)
target_compile_definitions(bvr_sim_cpp PRIVATE ASIO_STANDALONE _WEBSOCKETPP_CPP11_STL_)
if(MSVC)
    target_link_libraries(bvr_sim_cpp PRIVATE ws2_32 wsock32)
endif()
set_compiler_params(bvr_sim_cpp)
install(TARGETS bvr_sim_cpp
    LIBRARY DESTINATION ${BVR_SIM_PYTHON_MODULE_DESTINATION}
    RUNTIME DESTINATION ${BVR_SIM_PYTHON_MODULE_DESTINATION}
    ARCHIVE DESTINATION ${BVR_SIM_PYTHON_MODULE_DESTINATION}
)

install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../resources"
    DESTINATION ${BVR_SIM_PYTHON_MODULE_DESTINATION}
)

# Install PDB files for bvr_sim_cpp (MSVC debug symbols)
if(MSVC AND CMAKE_BUILD_TYPE MATCHES Debug)
    if(MSVC)
        install(FILES "${CMAKE_BINARY_DIR}/${CMAKE_BUILD_TYPE}/bvr_sim_cpp.pdb"
            DESTINATION ${BVR_SIM_PYTHON_MODULE_DESTINATION}
        )
    endif()
endif()

# ============================================================================
# Unit Tests Executable
# ============================================================================

if(BVR_SIM_BUILD_TESTS)
    add_executable(bvr_sim_unit_tests
        test_main.cxx
        "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_types.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_snapshot_builder.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_command_queue.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/telemetry_bridge.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/telemetry/embedded_web_server.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/so_pool.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/global_config.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/simulator.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/register.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/param_store.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_param_store.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_action_space.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_telemetry_snapshot.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_telemetry_command_queue.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_telemetry_bridge.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/aircraft/fdm/base.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm/generic_missile_fdm.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_generic_missile_fdm.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/simulator/pylon_manager.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_pylon_manager.cxx"
    )

    # Link with main library dependencies
    target_include_directories(bvr_sim_unit_tests PRIVATE ${BVR_SIM_INCLUDE_DIRS})
    target_link_libraries(bvr_sim_unit_tests PRIVATE c3utils)
    target_link_libraries(bvr_sim_unit_tests PRIVATE cpptrace::cpptrace)
    target_link_libraries(bvr_sim_unit_tests PRIVATE libJSBSim)
    target_compile_definitions(bvr_sim_unit_tests PRIVATE ASIO_STANDALONE _WEBSOCKETPP_CPP11_STL_)
    if(MSVC)
        target_link_libraries(bvr_sim_unit_tests PRIVATE ws2_32 wsock32)
    endif()

    if(BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS)
        install(TARGETS bvr_sim_unit_tests
            LIBRARY DESTINATION lib
            RUNTIME DESTINATION bin
            ARCHIVE DESTINATION lib
        )
    endif()

    # Apply compiler settings
    set_compiler_params(bvr_sim_unit_tests)
endif()






# ============================================================================
# Output Information
# ============================================================================
