cmake_minimum_required(VERSION 3.16)
project(gaelic_football C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(game_core src/game.c)
target_include_directories(game_core PUBLIC src)
if(NOT MSVC)
    target_link_libraries(game_core PUBLIC m)
endif()

add_executable(core_tests tests/core_tests.c)
target_link_libraries(core_tests PRIVATE game_core)

enable_testing()
add_test(NAME core_tests COMMAND core_tests)

find_package(raylib QUIET)
if(raylib_FOUND)
    add_executable(gaelic_football src/main.c src/audio.c src/player_model.c)
    target_link_libraries(gaelic_football PRIVATE game_core raylib)
    target_compile_definitions(gaelic_football PRIVATE PLATFORM_RAYLIB)
else()
    message(STATUS "raylib was not found; only the portable game-core tests will be built.")
endif()
