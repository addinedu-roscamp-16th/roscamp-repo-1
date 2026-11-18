# Central traffic permission: the robot may advance up to waypoint index granted_index of plan_version.
# - plan_version never repeats: the Task Manager starts every session from a time-based number, so a permission of an
#   earlier session can not match a new route. The robot also drops permissions older than its current route.
# - The Task Manager repeats the current permission of every active route (about 2 Hz), so a lost message or a robot
#   that subscribed late only delays the robot by one period.
# - task_id is for logs only; the robot matches on robot_id + plan_version.
string robot_id
string task_id
int32 plan_version
int32 granted_index
