cmake_minimum_required(VERSION 3.15)
project(bvr_sim_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
        set(CMAKE_CXX_FLAGS_RELEASE
            "/O2 /Ob2 /Oi /Ot /GL /fp:fast /arch:AVX2"
        )
    else ()
        set(CMAKE_CXX_FLAGS_RELEASE "-g -O3 -march=native")
    endif()
endif()


message(STATUS "Building bvr_sim_cpp for ${CMAKE_SYSTEM_NAME}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")



add_subdirectory("src")
