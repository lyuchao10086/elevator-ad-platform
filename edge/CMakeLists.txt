cmake_minimum_required(VERSION 3.10)
project(ScheduleModule)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find SQLite3
find_package(SQLite3 REQUIRED)
include_directories(${SQLite3_INCLUDE_DIRS})

include_directories(include)

# Add source files
file(GLOB SOURCES "src/*.cpp" "src/models/*.cpp")

# Create executable (exclude test.cpp)
add_executable(schedule_app src/main.cpp src/Database.cpp src/ScheduleManager.cpp src/models/Asset.cpp src/models/Schedule.cpp src/models/Interrupt.cpp src/models/TimeSlot.cpp src/models/PlayItem.cpp)
target_compile_features(schedule_app PUBLIC cxx_std_17)

# Link SQLite3
target_link_libraries(schedule_app PRIVATE SQLite::SQLite3)

# Add test executable
add_executable(schedule_test src/test.cpp src/Database.cpp src/ScheduleManager.cpp src/models/Asset.cpp src/models/Schedule.cpp src/models/Interrupt.cpp src/models/TimeSlot.cpp src/models/PlayItem.cpp)
target_compile_features(schedule_test PUBLIC cxx_std_17)
target_link_libraries(schedule_test PRIVATE SQLite::SQLite3)

# Copy resources directory to build directory
add_custom_command(TARGET schedule_app POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
    ${CMAKE_SOURCE_DIR}/resources
    ${CMAKE_BINARY_DIR}/resources
    COMMENT "Copying resources directory to build directory"
)

