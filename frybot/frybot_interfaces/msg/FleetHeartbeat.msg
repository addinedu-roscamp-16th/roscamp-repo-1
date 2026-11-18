# Task Manager -> all robots, about 5 Hz on /fms/heartbeat. Liveness of the central control and the emergency-stop
# channel (independent of the NavigateRoute action).
# A robot that drives a route and hears no heartbeat for fms_timeout seconds stops where it is until one arrives.
builtin_interfaces/Time stamp
string session        # changes every time the Task Manager starts: a robot then drops old permissions and its route
string[] estop        # robots that must stand still now (drive and serving arm) until they leave this list
