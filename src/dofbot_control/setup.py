import os
from glob import glob
from setuptools import setup

package_name = 'dofbot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'calibration'), glob('calibration/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='朱玉贺',
    maintainer_email='zhuyuhe@example.com',
    description='机械臂控制模块：pick_place/task_command 服务、task_event 上报、分拣闭环、标定工具与动作组',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'dofbot_control_server = dofbot_control.control_server:main',
            'dofbot_sorter = dofbot_control.sorter_node:main',
            'dofbot_event_bridge = dofbot_control.event_bridge:main',
            'hand_eye_calibrate = dofbot_control.hand_eye_calibrate:main',
            'validate_calibration = dofbot_control.validate_calibration:main',
            'pick_place_client = dofbot_control.pick_place_client:main',
            'task_command_client = dofbot_control.task_command_client:main',
            'fake_detect = dofbot_control.fake_detect_publisher:main',
            'f2_test = dofbot_control.f2_test_runner:main',
        ],
    },
)
