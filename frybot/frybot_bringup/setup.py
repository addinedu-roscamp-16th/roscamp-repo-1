from glob import glob
from setuptools import setup
package_name = 'frybot_bringup'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/launch', glob('launch/*.py')),
                ('share/' + package_name + '/config', glob('config/*.yaml')),
                ('share/' + package_name + '/rviz', glob('rviz/*.rviz'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot bringup',
    # [수정 2026-11-19] T-40: wait_online 추가(로봇 온라인 뒤 RViz 시작)
    entry_points={'console_scripts': [
        'fleet_rviz = frybot_bringup.fleet_rviz:main',
        'robot_remote = frybot_bringup.robot_remote:main',
        'wait_online = frybot_bringup.wait_online:main']},
    license='Apache-2.0',
)
