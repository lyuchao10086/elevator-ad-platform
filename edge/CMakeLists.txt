cmake_minimum_required(VERSION 3.10)
project(edge)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  add_compile_options(/utf-8)
endif()

# 设置包含目录
include_directories(include)

# 查找 SQLite3 库
find_package(SQLite3 REQUIRED)

# 查找 nlohmann_json 库 (如果是系统安装的)
# 如果是 header-only 且在 include 目录下，则不需要 find_package，直接 include_directories 即可
# 这里假设 nlohmann/json.hpp 已经在 include/nlohmann/json.hpp

# 查找 FFmpeg 库
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat libavcodec libavutil libswscale)

# 查找 SDL2 库
find_package(SDL2 CONFIG REQUIRED)

# 添加可执行文件
add_executable(edge 
    src/Database.cpp 
    src/main.cpp 
    src/EdgeManager.cpp 
    src/VideoPlayer.cpp
    src/NetworkClient.cpp
)

# 包含头文件路径
target_include_directories(edge PRIVATE 
    include 
    ${FFMPEG_INCLUDE_DIRS} 
    ${SDL2_INCLUDE_DIRS}
)
if(APPLE)
    target_include_directories(edge PRIVATE
        /opt/homebrew/include
        /opt/homebrew/Cellar/ffmpeg/7.1.1_2/include
    )
endif()

# 链接目录
link_directories(
    ${FFMPEG_LIBRARY_DIRS} 
    ${SDL2_LIBRARY_DIRS}
)
if(APPLE)
    link_directories(
        /opt/homebrew/lib
        /opt/homebrew/Cellar/ffmpeg/7.1.1_2/lib
        /usr/local/lib
        /opt/homebrew/Cellar/sdl2/2.32.6/lib
        /opt/homebrew/opt/ffmpeg/lib
        /opt/homebrew/lib/
    )
endif()

# 链接库
target_link_libraries(edge 
    SQLite::SQLite3
    PkgConfig::FFMPEG
    SDL2::SDL2
    SDL2::SDL2main
)
