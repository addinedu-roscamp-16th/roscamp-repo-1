"""Packaged maps and the graph stored in each map's ROS coordinate frame."""
import base64
import json
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import yaml

MAP_ROOT = Path(__file__).with_name('maps')
# [수정 2026-11-17] 가상 매장 도면(layout.py 의 200x100 cm)도 maps/proto 에
# 저장하고 지도 이름 'proto' 로 고름. 주행 그래프와 테이블 정보는 계속
# layout.py 가 만들므로, 'proto' 는 코드 안에서 실측 지도가 아닌 것('')으로 봄
PROTO_MAP_ID = 'proto'
PROTO_LABEL = '가상 매장 도면 · proto'


def selected_map_id() -> str:
    """실행에 고른 지도 이름을 돌려준다.

    Returns:
        환경 변수 FRYBOT_MAP_ID 의 값. 비어 있으면 'proto'.
    """
    return os.environ.get('FRYBOT_MAP_ID', '') or PROTO_MAP_ID


# [수정 2026-11-18] P1(D1): 지도를 쓰는 ROS 노드는 지도 이름 없이 뜨지 않음.
# 예전에는 FRYBOT_MAP_ID 가 없으면 조용히 가상 매장 도면(proto)으로 떴음.
# 오프라인 도구(fleet_bench, replay_run, pytest)는 selected_map_id·active_map_id
# 로 빈 값을 proto 로 읽는 지금 동작을 그대로 씀
def require_map_id(node_name: str) -> str:
    """ROS 노드가 쓸 지도 이름을 돌려준다. 없으면 노드를 멈춘다.

    Args:
        node_name: 오류 안내에 쓸 노드 이름.

    Returns:
        환경 변수 FRYBOT_MAP_ID 의 값('proto' 또는 실측 지도 이름).

    Raises:
        RuntimeError: FRYBOT_MAP_ID 가 없거나 비었을 때.
    """
    map_id = os.environ.get('FRYBOT_MAP_ID', '')
    if not map_id:
        raise RuntimeError(
            f'{node_name}: 지도 이름(FRYBOT_MAP_ID)이 없습니다. 런치'
            f'(real.launch.py map_id:=..., sim.launch.py)로 띄우거나 '
            f'FRYBOT_MAP_ID 를 지정하세요. 쓸 수 있는 값: '
            f'{[PROTO_MAP_ID] + map_ids()}')
    return map_id


def active_map_id() -> str:
    """실행 중인 실측 지도의 이름을 돌려준다.

    Returns:
        실측 지도 이름. 가상 매장 도면(proto)이면 빈 문자열.
    """
    map_id = os.environ.get('FRYBOT_MAP_ID', '')
    return '' if map_id == PROTO_MAP_ID else map_id


def map_ids():
    """실측 지도 이름 목록(가상 매장 도면 proto 는 넣지 않음)."""
    return sorted(path.name for path in MAP_ROOT.iterdir()
                  if path.is_dir() and path.name != PROTO_MAP_ID
                  and (path / 'roadmap.json').is_file())


@lru_cache
def profile(map_id):
    if map_id != PROTO_MAP_ID and map_id not in map_ids():
        raise ValueError(f'Unknown FryBot map: {map_id}')
    folder = MAP_ROOT / map_id
    with (folder / 'roadmap.json').open() as stream:
        graph = json.load(stream)
    graph['id'] = map_id
    graph['yaml'] = str(folder / graph['map_yaml'])
    return graph


@lru_cache
def map_display(map_id):
    from PIL import Image

    graph = profile(map_id)
    yaml_path = Path(graph['yaml'])
    with yaml_path.open() as stream:
        metadata = yaml.safe_load(stream)
    with Image.open(yaml_path.parent / metadata['image']) as image:
        width, height = image.size
        png = BytesIO()
        image.convert('L').save(png, format='PNG')
    return {
        'id': map_id, 'label': graph['label'], 'nodes': graph['nodes'], 'edges': graph['edges'],
        'origin': metadata['origin'], 'resolution': metadata['resolution'],
        'width': width, 'height': height, 'homes': graph['homes'],
        'image': 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode('ascii'),
    }
