"""Generate the Gazebo (gz sim) world of the store from the layout: floor, outer walls, tables and chairs."""
import json
import subprocess
import sys

from frybot_control import layout as L


def box(name, r, z0, h, rgba):
    x, y = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    sx, sy = r[2] - r[0], r[3] - r[1]
    c = ' '.join(str(v) for v in rgba)
    return f'''
    <model name="{name}"><static>true</static><pose>{x:.3f} {y:.3f} {z0 + h / 2:.3f} 0 0 0</pose><link name="link">
      <collision name="c"><geometry><box><size>{sx:.3f} {sy:.3f} {h:.3f}</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>{sx:.3f} {sy:.3f} {h:.3f}</size></box></geometry>
        <material><ambient>{c}</ambient><diffuse>{c}</diffuse></material></visual></link></model>'''


def marker_bits(ids, n=6):
    """Cell pattern (n x n, 0 = black) of each ArUco marker id. OpenCV runs in a child process: the pip build of
    cv2 points QT_QPA_PLATFORM_PLUGIN_PATH at its own Qt plugins on import, and imported into the launch process that
    setting was inherited by RViz and the Gazebo GUI, which then failed to start ("could not load the Qt platform
    plugin xcb")."""
    code = ('import cv2, json, sys; d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, sys.argv[1])); '
            'print(json.dumps({i: cv2.aruco.generateImageMarker(d, int(i), int(sys.argv[2])).tolist() '
            'for i in sys.argv[3:]}))')
    out = subprocess.check_output([sys.executable, '-c', code, L.ARUCO_DICT, str(n)] + [str(i) for i in ids])
    return {int(k): v for k, v in json.loads(out).items()}


def aruco_marker(name, bits, x, y, facing):
    """ArUco marker on a wall as a static model: a white plate with the black cells as thin boxes on it (no texture
    file, so the pattern cannot end up mirrored). (x, y) is the point on the wall face and `facing` the direction the
    marker looks, which is the model's +x. The cells are laid out as a camera in front of the wall sees them: image
    column -> to the viewer's right (model +y), image row -> down."""
    n = len(bits)                                           # 4x4 bits + 1 cell border
    c = L.MARKER_SIZE / n
    plate = L.MARKER_SIZE + 2 * c                           # one white cell around the marker (quiet zone)
    mat = lambda v: (f'<material><ambient>{v} {v} {v} 1</ambient><diffuse>{v} {v} {v} 1</diffuse>'
                     f'<specular>0 0 0 1</specular><emissive>{v} {v} {v} 1</emissive></material>')
    vis = [f'<visual name="plate"><pose>0.001 0 0 0 0 0</pose><geometry><box><size>0.002 {plate:.4f} {plate:.4f}'
           f'</size></box></geometry>{mat(1)}</visual>']
    for i in range(n):                                      # black runs of each row
        j = 0
        while j < n:
            if bits[i][j] > 127:
                j += 1
                continue
            k = j
            while k < n and bits[i][k] <= 127:
                k += 1
            yc, zc, w = ((j + k) / 2 - n / 2) * c, (n / 2 - i - 0.5) * c, (k - j) * c
            vis.append(f'<visual name="b{i}_{j}"><pose>0.0025 {yc:.5f} {zc:.5f} 0 0 0</pose><geometry><box>'
                       f'<size>0.001 {w:.5f} {c:.5f}</size></box></geometry>{mat(0)}</visual>')
            j = k
    return (f'\n    <model name="{name}"><static>true</static><pose>{x:.4f} {y:.4f} {L.MARKER_Z:.4f} 0 0 {facing:.5f}'
            f'</pose><link name="link">{"".join(vis)}</link></model>')


def world_sdf(fortress=False):
    lay = L.to_json()
    m = [box('wall_cook', lay['zones']['wall'], 0, 0.22, (0.15, 0.15, 0.15, 1)),
         box('wall_left', [-0.08, -0.08, -0.06, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_bottom', [-0.08, -0.08, 2.04, -0.06], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_top_a', [-0.08, 1.06, 0.12, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('wall_top_b', [0.32, 1.06, 2.04, 1.08], 0, 0.22, (0.3, 0.3, 0.3, 1)),
         box('counter', [2.045, 0.08, 2.11, 0.92], 0, 0.10, (0.8, 0.8, 0.8, 1))]
    for tid, t in lay['tables'].items():
        m.append(box(f'table_{tid}', t['table'], 0, 0.20, (0.55, 0.38, 0.28, 1)))
        for j, c in enumerate(t['chairs']):
            m.append(box(f'chair_{tid}_{j}', c, 0, 0.18, (0.95, 0.95, 0.95, 1)))
    marked = [d for d in L.docks().values() if d['kind'] == 'marker']      # ArUco markers the AMRs dock on
    bits = marker_bits([d['marker_id'] for d in marked])
    for d in marked:
        m.append(aruco_marker(f'aruco_{d["name"]}', bits[d['marker_id']], *d['marker']))
    sdf = f'''<?xml version="1.0"?>
<sdf version="1.8"><world name="frybot_store">
  <physics name="1ms" type="ignored"><max_step_size>0.002</max_step_size><real_time_factor>1.0</real_time_factor></physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
  <light type="directional" name="sun"><cast_shadows>false</cast_shadows><pose>0 0 10 0 0 0</pose>
    <diffuse>0.9 0.9 0.9 1</diffuse><direction>-0.3 0.2 -0.9</direction></light>
  <model name="floor"><static>true</static><link name="link">
    <collision name="c"><geometry><plane><normal>0 0 1</normal><size>6 4</size></plane></geometry></collision>
    <visual name="v"><geometry><plane><normal>0 0 1</normal><size>6 4</size></plane></geometry>
      <material><ambient>0.95 0.95 0.93 1</ambient><diffuse>0.95 0.95 0.93 1</diffuse></material></visual></link></model>
  {''.join(m)}
</world></sdf>
'''
    if fortress:                       # Fortress (ROS 2 Humble) still uses the ignition names
        sdf = sdf.replace('gz-sim-', 'ignition-gazebo-').replace('gz::sim::systems', 'ignition::gazebo::systems')
    return sdf


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/frybot_store.sdf'
    with open(out, 'w') as f:
        f.write(world_sdf())
    print(out)


if __name__ == '__main__':
    main()
