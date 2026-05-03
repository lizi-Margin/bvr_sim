message("Enter subdirectory c3utils")


function(set_compiler_params target_name)
    if(MSVC)
        # Windows MSVC
        target_compile_options(${target_name} PRIVATE /W4 /WX- /EHsc /wd4819)
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

        message("CMAKE_BUILD_TYPE: ${CMAKE_BUILD_TYPE}, LIBRARY_OUTPUT_DIRECTORY: ${CMAKE_BINARY_DIR}/${CMAKE_BUILD_TYPE}")
        message(STATUS "MSVC detected: Configuring for Windows")

    elseif(UNIX AND NOT APPLE)
        # Linux GCC/Clang
        # target_compile_options(${target_name} PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(${target_name} PRIVATE -Wall)
        target_compile_options(${target_name} PRIVATE -fPIC)

        # Add debug symbols for Debug builds
        if(CMAKE_BUILD_TYPE MATCHES Debug)
            target_compile_options(${target_name} PRIVATE -g -O2 -march=native)
        endif()
        target_compile_options(${target_name} PRIVATE -g)



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

# Build c3utils library
add_library(c3utils STATIC "vector.cxx")
target_include_directories(c3utils PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_include_directories(c3utils PUBLIC "${Eigen3_DIR}")
set_target_properties(c3utils PROPERTIES POSITION_INDEPENDENT_CODE ON)
set_compiler_params(c3utils)
if(BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS)
    install(TARGETS c3utils
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
        ARCHIVE DESTINATION lib
    )
endif()

# Install PDB files for c3utils (MSVC debug symbols)
# if(MSVC AND CMAKE_BUILD_TYPE MATCHES Debug)
if(MSVC)
    if(BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS)
        install(FILES "${CMAKE_BINARY_DIR}/src_cxx/c3utils/${CMAKE_BUILD_TYPE}/c3utils.pdb"
            DESTINATION lib
        )
    endif()
endif()

if(BVR_SIM_BUILD_TESTS)
    add_executable(test_c3utils "test_c3utils.cxx" "vector.hxx" "funcs.hxx" "c3utils.hxx" "def.hxx" "io.hxx")
    target_link_libraries(test_c3utils PRIVATE c3utils)
    set_compiler_params(test_c3utils)

    if(BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS)
        install(TARGETS test_c3utils
            LIBRARY DESTINATION lib
            RUNTIME DESTINATION bin
            ARCHIVE DESTINATION lib
        )
    endif()
endif()

# Install PDB files for test_c3utils (MSVC debug symbols)
# if(MSVC AND CMAKE_BUILD_TYPE MATCHES Debug)
if(MSVC)
    if(BVR_SIM_BUILD_TESTS AND BVR_SIM_INSTALL_DEVELOPMENT_ARTIFACTS)
        install(FILES "${CMAKE_BINARY_DIR}/${CMAKE_BUILD_TYPE}/test_c3utils.pdb"
            DESTINATION bin
            OPTIONAL
        )
    endif()
endif()




message("Exit subdirectory c3utils")
