# One roadmap node on a route.
# not_before = planned earliest departure toward the NEXT node (unix seconds, wall clock of the Task Manager, 0 = none).
# It is information only: the robot does NOT wait for it. The Task Manager enforces the timing by holding back the
# TrafficGrant of the next node until that moment (and shifts its own plan when a robot runs late).
string node_id
float64 x
float64 y
float64 not_before
