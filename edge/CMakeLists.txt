@'
cmake_minimum_required(VERSION 3.20)
project(ElevatorAdPlayer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 输出目录
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# 包含目录
include_directories(${CMAKE_SOURCE_DIR}/include)

# 添加可执行文件
add_executable(AdPlayer
    src/core/main.cpp
    # 其他文件稍后添加
)

message(STATUS "项目基础配置完成")
'@ | Out-File -FilePath CMakeLists.txt -Encoding UTF8