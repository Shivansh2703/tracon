cmake_minimum_required(VERSION 3.26)
project(tracon_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(tracon_core src/core.cpp)

install(TARGETS tracon_core LIBRARY DESTINATION .)
install(FILES src/tracon_core.pyi DESTINATION .)
