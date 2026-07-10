# SO-ARM ROS 2 MoveIt Workspace Source

This repository contains the source packages and notes for running SO-ARM with ROS 2 Humble, MoveIt 2, RViz MotionPlanning, fake ros2_control, and an automatic Box_0 pick/place demo.

## Packages

- `SO-ARM_ROS2_URDF`: URDF, meshes, and robot description resources.
- `so_arm_moveit_config`: MoveIt configuration, RViz config, controllers, launch files, and pick/place script.

## Main Docs

- `SO_ARM_MOVEIT_FULL_WORKFLOW.md`: Full setup, configuration, RViz integration, execution, and pick/place workflow.
- `SO_ARM_EXECUTION_CHECKLIST.md`: Operational checklist.
- `SO_ARM_PROJECT_STATUS.md`: Project status and issue history.

## Quick Start

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source ~/soarm_ws/install/setup.bash
```

Launch MoveIt/RViz:

```bash
ros2 launch so_arm_moveit_config demo.launch.py
```

Run the automatic pick/place demo in a second terminal:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash

ros2 run so_arm_moveit_config pick_place_box0.py
```

Default pick/place target:

```text
Box_0 start: 0.00, -0.24, 0.06
Box_0 place: 0.17, -0.24, 0.06
```

## Notes

Do not run `joint_state_publisher_gui` together with `demo.launch.py`; use one mode at a time to avoid duplicate `/joint_states` publishers.
