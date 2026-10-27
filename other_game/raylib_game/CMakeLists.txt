cmake_minimum_required(VERSION 3.16)

project(raylib_game C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(raylib CONFIG REQUIRED)

add_executable(raylib_game
    src/main.c
    src/game.c
)

target_include_directories(raylib_game PRIVATE src)
target_link_libraries(raylib_game PRIVATE raylib)
