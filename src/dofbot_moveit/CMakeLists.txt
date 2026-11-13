cmake_minimum_required(VERSION 3.8)
project(dofbot_moveit)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(kdl_parser REQUIRED)
find_package(dofbot_info REQUIRED)

set(dependencies 
  rclcpp
  kdl_parser
  dofbot_info
)

include_directories(
  include/${PROJECT_NAME}
)

add_executable(dofbot_server src/dofbot_server.cpp)
target_link_libraries(dofbot_server dofbot_kinemarics)
ament_target_dependencies(dofbot_server ${dependencies})

install(TARGETS dofbot_server
  DESTINATION lib/${PROJECT_NAME}
)

# 安装资源文件夹（必须在 ament_package 之前）
install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY rviz
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY urdf
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY meshes
  DESTINATION share/${PROJECT_NAME})

# 导出依赖
ament_export_include_directories(include)
ament_export_dependencies(${dependencies})

# 测试与代码检查配置（必须在 ament_package 之前）
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

# 最后收尾打包（只能出现一次，且必须在最后）
ament_package()