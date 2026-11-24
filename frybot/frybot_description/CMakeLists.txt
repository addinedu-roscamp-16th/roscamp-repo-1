cmake_minimum_required(VERSION 3.8)
project(frybot_description)

find_package(ament_cmake REQUIRED)

# pinky: Pinky Pro xacro + meshes, jetcobot: myCobot 280 Pi URDF + meshes
install(DIRECTORY pinky jetcobot licenses DESTINATION share/${PROJECT_NAME})

ament_package()
