"""Start, stop, check or update the FryBot software of the registered robots from the central PC over SSH.

    ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v001     # bring one robot up (Ctrl-C stops it)
    ros2 run frybot_bringup robot_remote --all --check                     # can we log in, is the software there?
    ros2 run frybot_bringup robot_remote --all --stop                      # stop whatever still runs on the robots
    ros2 run frybot_bringup robot_remote --all --deploy                    # copy src/frybot to the robots and build

Hosts, user and password come from the registry ~/.config/frybot/robots.yaml.
[수정 2026-11-18] P2: 패키지의 config/robots.yaml 을 대신 읽던 것을 없앰(T-30
뒤로 없는 파일). robots_file 인자로 다른 파일을 줄 수 있음.
[수정 2026-11-18] T-30: 비밀번호가 든 등록부는 저장소 밖에만 둠. 패키지에는
비밀번호 없는 config/robots.example.yaml 만 있으니 ~/.config/frybot/robots.yaml
로 복사해 채움.
real.launch.py runs one "up" process per robot, so one launch on the central PC starts the whole fleet.
The password never appears on a command line: ssh asks a helper script for it, which reads it from the environment.
"""
import argparse
import os
import shlex
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

import yaml

USER_FILE = os.path.expanduser('~/.config/frybot/robots.yaml')
# what belongs to the robot-side stack: stopped before a start and by --stop
STACK = ['[r]obot.launch.py', 'lib/[f]rybot_mobile', 'lib/[p]inky_bringup', '[s]llidar', '[r]obot_state_publisher',
         '[c]ontroller_server', '[p]lanner_server', '[b]t_navigator', '[l]ifecycle_manager', '[o]pennav_docking',
         '[m]ap_server', 'lib/nav2_amcl/[a]mcl']
# [수정 2026-11-17] 로봇 모델(frybot_description)도 로봇에 배포: robot.launch.py 가
# pinky_pro 대신 이 사본으로 robot_state_publisher 를 띄움
DEPLOY = ['frybot_interfaces', 'frybot_control', 'frybot_description', 'frybot_mobile']
# [수정 2026-11-18] T-30: 등록부가 없을 때 안내할 예시 파일 이름
EXAMPLE_NAME = 'robots.example.yaml'


def registry_file(path=''):
    if path:
        return path
    # [수정 2026-11-18] P2: 없으면 패키지의 config/robots.yaml(T-30 뒤로 없는
    # 파일) 대신 사용자 파일 경로를 돌려줌. 없으면 registry_missing 이 안내함
    return USER_FILE


# [수정 2026-11-18] T-30: 등록부가 없으면 빈 목록·traceback 대신 안내 한 줄
def registry_missing(path: str = '') -> str:
    """등록부 파일이 없을 때 보여 줄 안내 문장을 돌려준다.

    Args:
        path: robots_file 인자. 비었으면 기본 위치를 찾는다.

    Returns:
        등록부가 있으면 빈 문자열, 없으면 찾은 경로와 예시 파일 위치를
        담은 한 줄.
    """
    found = registry_file(path)
    if os.path.isfile(found):
        return ''
    from ament_index_python.packages import get_package_share_directory
    example = os.path.join(get_package_share_directory('frybot_bringup'),
                           'config', EXAMPLE_NAME)
    return (f'로봇 등록부가 없습니다: {found}. {example} 을 '
            f'{USER_FILE} 로 복사해 채우세요(권한 600)')


def load_registry(path=''):
    """{robot id: settings} of the enabled robots, defaults filled in, in the order pinky1, pinky2, ..."""
    path = registry_file(path)
    with open(path) as stream:
        data = yaml.safe_load(stream) or {}
    defaults = data.get('defaults') or {}
    out = {}
    for rid, cfg in (data.get('robots') or {}).items():
        cfg = {**defaults, **(cfg or {})}
        if not cfg.get('enabled', True):
            continue
        if not cfg.get('host'):
            raise ValueError(f'{path}: robot {rid} has no host')
        out[rid] = cfg
    number = lambda rid: int(''.join(c for c in rid if c.isdigit()) or 0)
    return dict(sorted(out.items(), key=lambda kv: number(kv[0])))


class Ssh:
    """One robot's SSH access (key first, then the registry password through an askpass helper)."""

    def __init__(self, rid, cfg):
        self.rid, self.cfg = rid, cfg
        self.target = f"{cfg.get('user', 'pinky')}@{cfg['host']}"
        self.env = dict(os.environ)
        self.askpass = None
        password = str(cfg.get('password') or '')
        if password:
            fd, self.askpass = tempfile.mkstemp(prefix='frybot_askpass_', suffix='.sh')
            os.write(fd, b'#!/bin/sh\nprintf "%s\\n" "$FRYBOT_SSH_PASSWORD"\n')
            os.close(fd)
            os.chmod(self.askpass, stat.S_IRWXU)
            self.env.update(FRYBOT_SSH_PASSWORD=password, SSH_ASKPASS=self.askpass, SSH_ASKPASS_REQUIRE='force')
        self.opts = ['-p', str(cfg.get('port', 22)), '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=6',
                     '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=6', '-o', 'TCPKeepAlive=yes', '-o', 'NumberOfPasswordPrompts=1',
                     '-o', 'PreferredAuthentications=publickey,password', '-o', 'LogLevel=ERROR']

    def cmd(self, script, tty=False):
        """ssh command line that runs `script` in a login-like bash on the robot (its ~/.bashrc is read)."""
        return [self.cfg.get('ssh_bin', 'ssh')] + (['-tt'] if tty else []) + self.opts + \
            [self.target, 'bash -ic ' + shlex.quote(script)]

    def run(self, script, timeout=30):
        return subprocess.run(self.cmd(script), env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=timeout)

    def close(self):
        if self.askpass and os.path.exists(self.askpass):
            os.remove(self.askpass)


# [수정 2026-11-18] T-38: peers 인자 추가. 값이 있으면 로봇의 탐색을
# 로봇 안 + 관제 PC 로 제한(로봇끼리 서로 탐색하지 않음)
def setup_lines(cfg, peers=''):
    """Shell lines that prepare ROS on the robot: same ROS domain and discovery settings as the central PC.

    Args:
        cfg: 등록부의 로봇 설정.
        peers: 관제 PC 주소. 주면 로봇은 자기 안과 그 주소만 탐색한다.

    Returns:
        로봇의 셸에서 실행할 줄의 목록.
    """
    ws = cfg.get('workspace', '~/frybot_robot_ws')
    lines = [f"source {cfg.get('ros_setup', '/opt/ros/jazzy/setup.bash')}",
             f'[ -f {ws}/install/setup.bash ] && source {ws}/install/setup.bash']
    domain = cfg.get('domain_id', 'auto')
    domain = os.environ.get('ROS_DOMAIN_ID', '') if str(domain) == 'auto' else str(domain)
    if domain:
        lines.append(f'export ROS_DOMAIN_ID={shlex.quote(domain)}')
    for key in ('RMW_IMPLEMENTATION', 'ROS_AUTOMATIC_DISCOVERY_RANGE', 'ROS_LOCALHOST_ONLY'):
        value = str(cfg.get(key.lower(), os.environ.get(key, '')))
        # [수정 2026-11-18] T-38: 등록부에 값이 없으면 LOCALHOST
        if peers and key == 'ROS_AUTOMATIC_DISCOVERY_RANGE':
            value = str(cfg.get(key.lower(), 'LOCALHOST'))
        if value:
            lines.append(f'export {key}={shlex.quote(value)}')
    # [수정 2026-11-18] T-38: 관제 PC 만 탐색 상대로 지정
    if peers:
        value = str(cfg.get('ros_static_peers', peers))
        lines.append(f'export ROS_STATIC_PEERS={shlex.quote(value)}')
    for key, value in (cfg.get('env') or {}).items():
        lines.append(f'export {key}={shlex.quote(str(value))}')
    return lines


# [수정 2026-11-18] T-38: 로봇에 알려 줄 관제 PC 주소를 찾음
def pc_address(host: str) -> str:
    """로봇 쪽에서 본 이 PC 의 주소를 돌려준다.

    Args:
        host: 로봇의 주소(등록부의 host).

    Returns:
        그 로봇으로 나가는 인터페이스의 IPv4 주소.

    Raises:
        OSError: 주소를 풀지 못하거나 그 로봇으로 가는 경로가 없을 때.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, 9))       # UDP: 패킷은 나가지 않고 경로만 정함
        return sock.getsockname()[0]


def stop_script():
    kill = lambda sig: ' ; '.join(f'pkill -{sig} -f {shlex.quote(p)}' for p in STACK)
    busy = ' || '.join(f'pgrep -f {shlex.quote(p)} >/dev/null' for p in STACK)
    return f'if {busy}; then {kill("INT")}; sleep 4; {kill("9")}; sleep 1; echo "stopped the old robot stack"; fi; true'


LOG = '~/.frybot/robot_launch.log'           # on the robot


# [수정 2026-11-18] map_yaml 인자(robot.launch.py 의 map:=)를 지움(사용자 결정).
# 다른 yaml 을 끼우면 roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에
# 새 map_id 로 추가
# [수정 2026-11-18] T-38: peers(관제 PC 주소)를 setup_lines 에 넘김
def launch_script(rid, cfg, map_id='', extra=(), peers=''):
    """Shell script that (re)starts the robot stack DETACHED from the SSH session, output to LOG. The stack then
    survives a dropped Wi-Fi link; without a heartbeat from the central PC the robot does not drive anyway."""
    args = {'robot_id': rid}
    if map_id:
        args['map_id'] = map_id
    if cfg.get('initial_pose'):
        args['initial_pose'] = str(cfg['initial_pose'])
    args.update({k: str(v) for k, v in (cfg.get('launch_args') or {}).items()})
    for item in extra:
        key, _, value = item.partition(':=')
        args[key] = value
    words = ' '.join(shlex.quote(f'{k}:={v}') for k, v in args.items())
    # "robot.launch''.py": the name must not appear in one piece in this shell's own command line, or the clean-up
    # at the start of the script (pkill -f robot.launch.py) would kill the shell that runs it
    return ' ; '.join([stop_script()] + setup_lines(cfg, peers) + [
        'mkdir -p ~/.frybot', f': > {LOG}',
        f"setsid -f nohup ros2 launch frybot_mobile robot.launch''.py {words} >> {LOG} 2>&1 < /dev/null",
        'sleep 1', 'echo FRYBOT_STARTED'])


def follow_script(first_line):
    """Print the robot's launch log from `first_line` on, until the launch is gone."""
    return (f'tail -n +{first_line} -F {LOG} 2>/dev/null & T=$! ; '
            'while pgrep -f "[r]obot.launch.py" >/dev/null; do sleep 2; done ; '
            'sleep 1 ; kill $T 2>/dev/null ; echo FRYBOT_LAUNCH_ENDED')


def up(rid, cfg, a):
    """Start the robot stack and show its log until Ctrl-C (which stops the stack). A lost SSH connection is
    re-opened; the stack keeps running meanwhile."""
    ssh = Ssh(rid, cfg)
    # [수정 2026-11-18] T-38: discovery=peers 면 로봇이 관제 PC 만 탐색.
    # PC 주소를 못 찾으면 예전 방식(subnet)으로 띄우고 알림
    peers = ''
    if a.discovery == 'peers':
        try:
            peers = pc_address(cfg['host'])
        except OSError as err:
            print(f'[{rid}] 관제 PC 주소를 찾지 못해 discovery=subnet 으로 '
                  f'띄웁니다: {err}', flush=True)
    script = launch_script(rid, cfg, a.map_id, a.arg, peers)
    if a.dry_run:
        print(f'[{rid}] {ssh.target}: {script}')
        ssh.close()
        return 0
    stopping = threading.Event()
    state = {'proc': None}

    def stop(*_):
        if not stopping.is_set():
            stopping.set()
            print(f'[{rid}] stopping the robot stack ...', flush=True)
            if state['proc'] is not None and state['proc'].poll() is None:
                state['proc'].terminate()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f'[{rid}] connecting to {ssh.target} ...', flush=True)
    started = False
    for attempt in range(5):
        if stopping.is_set():
            break
        try:
            out = ssh.run(script, timeout=60)
            started = 'FRYBOT_STARTED' in out.stdout
            if started:
                break
            tail = [ln for ln in out.stdout.strip().splitlines() if 'job control' not in ln and 'process group' not in ln]
            print(f'[{rid}] could not start (try {attempt + 1}/5): {tail[-1] if tail else "no answer"}', flush=True)
        except subprocess.TimeoutExpired:
            print(f'[{rid}] no answer from {ssh.target} (try {attempt + 1}/5)', flush=True)
        stopping.wait(5.0)
    code, seen, ended = 0, 0, False
    last = {'t': time.time()}

    def patience():                            # the Pinky is slow while Nav2 starts: say that we are still waiting
        while not stopping.wait(20.0) and not ended:
            if time.time() - last['t'] > 40.0:
                print(f'[{rid}] ... no output from the robot for {time.time() - last["t"]:.0f} s (busy starting, or '
                      f'Wi-Fi stalled); still connected and waiting', flush=True)
    threading.Thread(target=patience, daemon=True).start()
    if not started and not stopping.is_set():
        print(f'[{rid}] SSH failed: check that the robot is on, the address {cfg["host"]} and the password '
              f'in {registry_file(a.robots_file)}', flush=True)
        code = 1
    while started and not stopping.is_set() and not ended:
        proc = state['proc'] = subprocess.Popen(ssh.cmd(follow_script(seen + 1)), env=ssh.env, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in iter(proc.stdout.readline, b''):
            line = raw.decode(errors='replace').rstrip('\r\n')
            if line == 'FRYBOT_LAUNCH_ENDED':
                ended = True
            elif line and 'no job control' not in line and 'terminal process group' not in line \
                    and not (line.startswith('[') and line[1:2].isdigit() and len(line) < 14):   # bash job notice
                seen += 1
                last['t'] = time.time()
                print(f'[{rid}] {line}', flush=True)
        proc.wait()
        if ended:
            print(f'[{rid}] robot launch ended on the robot (see {LOG} there)', flush=True)
            code = 1
        elif not stopping.is_set():
            print(f'[{rid}] SSH connection lost; the robot stack keeps running, reconnecting ...', flush=True)
            stopping.wait(4.0)
    if stopping.is_set():
        for attempt in range(4):               # the robot may be out of reach for a moment: keep trying
            try:
                if ssh.run(stop_script() + ' ; echo FRYBOT_STOPPED', timeout=22).stdout.count('FRYBOT_STOPPED'):
                    print(f'[{rid}] robot stack stopped', flush=True)
                    break
            except subprocess.TimeoutExpired:
                pass
            if attempt == 3:
                print(f'[{rid}] could NOT reach the robot to stop it: run "robot_remote {rid} --stop" later '
                      f'(without the central PC it stands still)', flush=True)
        code = 0
    ssh.close()
    return code


def check(rid, cfg, a):
    ssh = Ssh(rid, cfg)
    ws = cfg.get('workspace', '~/frybot_robot_ws')
    script = ' ; '.join(setup_lines(cfg) + [
        'echo "host=$(hostname) ros=$ROS_DISTRO domain=$ROS_DOMAIN_ID range=$ROS_AUTOMATIC_DISCOVERY_RANGE"',
        f'[ -d {ws}/src ] && echo "workspace={ws} ok" || echo "workspace={ws} MISSING"',
        # [수정 2026-11-17] pinky_bringup 대신 내장 드라이버가 쓰는 것들을 점검
        'for p in frybot_interfaces frybot_control frybot_description frybot_mobile sllidar_ros2 '
        'joint_state_publisher nav2_bt_navigator nav2_amcl opennav_docking; do '
        'ros2 pkg prefix $p >/dev/null 2>&1 && echo "package $p ok" || echo "package $p MISSING"; done',
        'for m in dynamixel_sdk pinkylib tf_transformations; do '
        'python3 -c "import $m" >/dev/null 2>&1 && echo "python $m ok" || echo "python $m MISSING"; done',
        '(ros2 interface show frybot_interfaces/msg/FleetHeartbeat >/dev/null 2>&1 && echo "interfaces up to date") '
        '|| echo "interfaces OLD: run robot_remote --deploy"',
        'pgrep -fa "[r]obot.launch.py" >/dev/null && echo "robot stack RUNNING" || echo "robot stack not running"'])
    try:
        out = ssh.run(script, timeout=40)
        ok = out.returncode == 0
        text = out.stdout
    except subprocess.TimeoutExpired:
        ok, text = False, 'timed out'
    for line in text.splitlines():
        if line.strip() and 'cannot set terminal process group' not in line and 'no job control' not in line:
            print(f'[{rid}] {line.strip()}')
    print(f'[{rid}] {"OK" if ok else "FAILED"} ({ssh.target})', flush=True)
    ssh.close()
    return 0 if ok else 1


def stop(rid, cfg, a):
    ssh = Ssh(rid, cfg)
    try:
        out = ssh.run(stop_script() + ' ; echo done', timeout=30)
        print(f'[{rid}] ' + (out.stdout.strip().splitlines() or ['no answer'])[-1], flush=True)
        return out.returncode
    except subprocess.TimeoutExpired:
        print(f'[{rid}] timed out')
        return 1
    finally:
        ssh.close()


def deploy(rid, cfg, a):
    """Copy the robot-side packages of this PC's source tree to the robot and build them there."""
    ssh = Ssh(rid, cfg)
    src = os.path.expanduser(a.source)
    ws = cfg.get('workspace', '~/frybot_robot_ws')
    missing = [p for p in DEPLOY if not os.path.isdir(os.path.join(src, p))]
    if missing:
        print(f'[{rid}] {src} has no {missing}: pass --source <path of src/frybot>')
        ssh.close()
        return 1
    rsh = ' '.join(shlex.quote(w) for w in [cfg.get('ssh_bin', 'ssh')] + ssh.opts)
    # copy into the folder that already holds the packages on this robot (a second copy elsewhere in the workspace
    # would make colcon refuse to build), else into src/frybot
    try:
        found = ssh.run(f'mkdir -p {ws}/src ; d=$(find {ws}/src -maxdepth 3 -type d -name frybot_mobile | head -n 1) ; '
                        f'[ -n "$d" ] && echo "FRYBOT_SRC=$(dirname "$d")" || echo "FRYBOT_SRC={ws}/src/frybot"', timeout=30)
    except subprocess.TimeoutExpired:
        found = None
    where = [ln.split('=', 1)[1].strip() for ln in (found.stdout.splitlines() if found else []) if ln.startswith('FRYBOT_SRC=')]
    if not where:
        print(f'[{rid}] could not reach the robot ({ssh.target})')
        ssh.close()
        return 1
    folder = where[-1]
    dest = f'{ssh.target}:{folder[2:] if folder.startswith("~/") else folder}/'
    cmd = ['rsync', '-az', '--delete', '--exclude', '__pycache__', '--exclude', '*.pyc', '-e', rsh] + \
        [os.path.join(src, p) for p in DEPLOY] + [dest]
    print(f'[{rid}] copying {", ".join(DEPLOY)} to {dest}', flush=True)
    if a.dry_run:
        print(f'[{rid}] ' + ' '.join(cmd))
        ssh.close()
        return 0
    try:
        ssh.run(f'mkdir -p {folder}', timeout=20)
        code = subprocess.run(cmd, env=ssh.env, stdin=subprocess.DEVNULL).returncode
        if code == 0:
            print(f'[{rid}] building on the robot (the interfaces take a few minutes on a Pinky) ...', flush=True)
            # A workspace built earlier without --symlink-install cannot be rebuilt with it ("failed to create
            # symbolic link ... Is a directory"): the first deploy clears the build results of these packages.
            pkgs = ' '.join(DEPLOY)
            build = ' ; '.join([
                'set -o pipefail', f"source {cfg.get('ros_setup', '/opt/ros/jazzy/setup.bash')}", f'cd {ws}',
                f'if [ ! -f build/.frybot_symlink_install ]; then for p in {pkgs}; do rm -rf build/$p install/$p; done; '
                'echo "cleared old build results"; fi',
                'colcon build --symlink-install --packages-up-to frybot_mobile 2>&1 | tail -n 15 '
                '&& touch build/.frybot_symlink_install'])
            out = ssh.run(build, timeout=1800)
            for line in out.stdout.splitlines()[-15:]:
                if 'no job control' not in line and 'terminal process group' not in line:
                    print(f'[{rid}] {line}')
            code = out.returncode
        print(f'[{rid}] deploy {"finished" if code == 0 else "FAILED"}', flush=True)
        return code
    finally:
        ssh.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('robots', nargs='*', help='robot ids from the registry (or --all)')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--robots-file', default='', help='registry yaml (default: ~/.config/frybot/robots.yaml, else the packaged one)')
    ap.add_argument('--map-id', default='', help='measured map id for robot.launch.py')
    # [수정 2026-11-18] --map(로봇의 지도 yaml)을 지움. map_id 지도만 씀
    ap.add_argument('--arg', action='append', default=[], help='extra robot.launch.py argument, e.g. --arg speed:=0.06')
    # [수정 2026-11-18] T-38: 로봇의 DDS 탐색 범위
    ap.add_argument('--discovery', default='peers',
                    choices=('peers', 'subnet'),
                    help='peers: the robot discovers only itself and this '
                         'PC (default); subnet: everything on the LAN, as '
                         'before 2026-11-18')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--stop', action='store_true')
    ap.add_argument('--deploy', action='store_true')
    ap.add_argument('--source', default='~/frybot_ws/src/frybot', help='source tree to deploy')
    ap.add_argument('--dry-run', action='store_true', help='print what would run')
    a, _ = ap.parse_known_args(argv)          # ignore the --ros-args that a launch file may append
    # [수정 2026-11-18] T-30: 등록부가 없으면 traceback 대신 안내하고 1로 끝냄
    missing = registry_missing(a.robots_file)
    if missing:
        print(missing, file=sys.stderr)
        return 1
    reg = load_registry(a.robots_file)
    ids = list(reg) if a.all else a.robots
    unknown = [r for r in ids if r not in reg]
    if unknown or not ids:
        print(f'robots {unknown or "(none given)"} are not in {registry_file(a.robots_file)}; registered: {list(reg)}')
        return 2
    job = check if a.check else stop if a.stop else deploy if a.deploy else up
    if job is up and len(ids) > 1:
        print('bring-up runs one robot per process: use "ros2 launch frybot_bringup robots.launch.py" for the fleet')
        return 2
    return max(job(rid, reg[rid], a) for rid in ids)


if __name__ == '__main__':
    sys.exit(main())
