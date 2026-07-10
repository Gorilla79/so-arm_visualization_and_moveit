# SO-ARM MoveIt/RViz 전체 구축 및 실행 정리

이 문서는 `~/soarm_ws` 워크스페이스에서 SO-ARM URDF를 MoveIt 2와 연동하고, RViz MotionPlanning으로 계획/실행한 뒤, `Box_0` 큐브를 자동으로 집어서 지정 위치에 놓는 과정까지 정리한 문서입니다.

검증 환경:

- OS/ROS: Ubuntu + ROS 2 Humble
- Workspace: `~/soarm_ws`
- 주요 패키지:
  - `src/SO-ARM_ROS2_URDF`
  - `src/so_arm_moveit_config`

## 1. 워크스페이스 구조

```text
~/soarm_ws/src
├── SO-ARM_ROS2_URDF
│   ├── config
│   ├── meshes
│   ├── urdf
│   ├── CMakeLists.txt
│   └── package.xml
├── so_arm_moveit_config
│   ├── config
│   ├── launch
│   ├── scripts
│   ├── CMakeLists.txt
│   └── package.xml
├── SO_ARM_EXECUTION_CHECKLIST.md
├── SO_ARM_PROJECT_STATUS.md
└── SO_ARM_MOVEIT_FULL_WORKFLOW.md
```

## 2. MoveIt 패키지 생성 개요

MoveIt 설정 패키지는 MoveIt Setup Assistant를 기준으로 생성했습니다.

기본 절차:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash

ros2 launch moveit_setup_assistant setup_assistant.launch.py
```

Setup Assistant에서 수행한 핵심 설정:

- URDF/Xacro 로드
  - SO-ARM URDF: `SO-ARM_ROS2_URDF/urdf/so101_new_calib.urdf`
- Planning Groups
  - `arm`
  - `gripper`
- End Effector
  - name: `gripper_eef`
  - parent link: `wrist`
  - group: `gripper`
  - parent group: `arm`
- ros2_control
  - fake controller용 `mock_components/GenericSystem`
  - command interface: `position`
  - state interfaces: `position`, `velocity`
- Controllers
  - `arm_controller`
  - `gripper_controller`
  - `joint_state_broadcaster`

생성된 MoveIt config 패키지:

```text
~/soarm_ws/src/so_arm_moveit_config
```

## 3. Wrist_Roll 누락 문제 수정

초기 설정에서는 `Wrist_Roll`이 일부 controller 설정에서 빠져 있어 RViz TF/MoveIt planning group/controller 간 불일치가 발생했습니다.

### 3.1 SRDF arm group

파일:

```text
src/so_arm_moveit_config/config/so101_new_calib.srdf
```

`arm` chain tip은 `wrist`가 아니라 `gripper`여야 합니다.

```xml
<group name="arm">
    <chain base_link="base" tip_link="gripper"/>
</group>
```

이렇게 해야 `wrist -> gripper` 사이의 `Wrist_Roll` 조인트가 arm chain에 포함됩니다.

### 3.2 MoveIt controller joints

파일:

```text
src/so_arm_moveit_config/config/moveit_controllers.yaml
```

최종 설정:

```yaml
moveit_controller_manager: moveit_simple_controller_manager/MoveItSimpleControllerManager

moveit_simple_controller_manager:
  controller_names:
    - arm_controller
    - gripper_controller

  arm_controller:
    type: FollowJointTrajectory
    action_ns: follow_joint_trajectory
    default: true
    joints:
      - Rotation
      - Pitch
      - Elbow
      - Wrist_Pitch
      - Wrist_Roll
  gripper_controller:
    type: FollowJointTrajectory
    action_ns: follow_joint_trajectory
    default: true
    joints:
      - Jaw
```

중요한 점:

- `Wrist_Roll` 포함
- `action_ns: follow_joint_trajectory` 포함
- MoveIt controller와 ros2_control controller의 joint 순서/목록 일치

### 3.3 ros2_control controller joints

파일:

```text
src/so_arm_moveit_config/config/ros2_controllers.yaml
```

최종 arm controller joints:

```yaml
arm_controller:
  ros__parameters:
    joints:
      - Rotation
      - Pitch
      - Elbow
      - Wrist_Pitch
      - Wrist_Roll
    command_interfaces:
      - position
    state_interfaces:
      - position
      - velocity
```

### 3.4 fake ros2_control xacro

파일:

```text
src/so_arm_moveit_config/config/so101_new_calib.ros2_control.xacro
```

`Wrist_Roll` fake hardware interface를 추가했습니다.

```xml
<joint name="Wrist_Roll">
    <command_interface name="position"/>
    <state_interface name="position">
      <param name="initial_value">${initial_positions['Wrist_Roll']}</param>
    </state_interface>
    <state_interface name="velocity"/>
</joint>
```

### 3.5 initial positions

파일:

```text
src/so_arm_moveit_config/config/initial_positions.yaml
```

```yaml
initial_positions:
  Elbow: 0
  Jaw: 0
  Pitch: 0
  Rotation: 0
  Wrist_Pitch: 0
  Wrist_Roll: 0
```

### 3.6 joint limits

파일:

```text
src/so_arm_moveit_config/config/joint_limits.yaml
```

MoveIt parameter type 오류를 피하기 위해 정수형 `10`, `0` 대신 실수형 `10.0`, `0.0`으로 정리했습니다.

예:

```yaml
Wrist_Roll:
  has_velocity_limits: true
  max_velocity: 10.0
  has_acceleration_limits: false
  max_acceleration: 0.0
```

## 4. 빌드

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash

colcon build --symlink-install --packages-select so_arm_moveit_config

source ~/soarm_ws/install/setup.bash
```

전체 워크스페이스를 다시 빌드하려면:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash

colcon build --symlink-install

source ~/soarm_ws/install/setup.bash
```

## 5. RViz/MoveIt 실행

중복 publisher 충돌을 피하기 위해 MoveIt 모드에서는 `demo.launch.py` 단독 실행을 기준으로 합니다.

터미널 1:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash

ros2 launch so_arm_moveit_config demo.launch.py
```

주의:

- `demo.launch.py` 실행 중에는 `joint_state_publisher_gui`를 따로 실행하지 않습니다.
- `robot_state_publisher`, `joint_state_broadcaster`, `move_group`, `rviz2`가 launch에서 함께 올라옵니다.

## 6. 실행 상태 확인

새 터미널:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash
```

노드 확인:

```bash
ros2 node list | grep -E "move_group|controller_manager|joint_state_broadcaster|robot_state_publisher|rviz"
```

기대 예:

```text
/controller_manager
/joint_state_broadcaster
/move_group
/moveit_simple_controller_manager
/robot_state_publisher
/rviz
```

컨트롤러 확인:

```bash
ros2 control list_controllers
```

기대 예:

```text
joint_state_broadcaster active
arm_controller active
gripper_controller active
```

joint state 확인:

```bash
ros2 topic echo /joint_states --once
```

기대 joint 목록:

```text
Rotation
Pitch
Elbow
Wrist_Pitch
Wrist_Roll
Jaw
```

## 7. RViz MotionPlanning 사용법

RViz가 뜨면 MotionPlanning 패널에서 다음을 확인합니다.

### 7.1 arm 계획/실행

1. `Planning` 탭 선택
2. `Planning Group`을 `arm`으로 선택
3. interactive marker로 목표 자세 조정
4. `Plan`
5. 계획이 정상 생성되면 `Execute` 또는 `Plan & Execute`

### 7.2 gripper 계획/실행

1. `Planning Group`을 `gripper`로 선택
2. joint target 또는 interactive marker 기준으로 조정
3. `Plan`
4. `Execute`

## 8. RViz에서 큐브 생성

RViz MotionPlanning 패널의 `Scene Objects` 탭에서 collision object를 만들 수 있습니다.

예:

- object type: `Box`
- size: `0.05`, `0.05`, `0.05`
- object id: RViz 기본 생성 시 보통 `Box_0`

위치를 수정한 후에는 반드시 `Publish`를 눌러야 MoveIt PlanningScene에 반영됩니다.

다만 자동 pick/place 스크립트는 `Box_0`가 없으면 기본 위치에 자동 생성합니다.

## 9. 자동 Pick & Place 스크립트

파일:

```text
src/so_arm_moveit_config/scripts/pick_place_box0.py
```

설치 등록:

```cmake
install(
  PROGRAMS scripts/pick_place_box0.py
  DESTINATION lib/${PROJECT_NAME}
)
```

실행:

```bash
cd ~/soarm_ws
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash

ros2 run so_arm_moveit_config pick_place_box0.py
```

기본 동작:

- 대상 object: `Box_0`
- 시작 위치: `(0.00, -0.24, 0.06)`
- 목표 위치: `(0.17, -0.24, 0.06)`
- 큐브 크기: `0.05m`
- arm group: `arm`
- IK link: `gripper`
- attach link: `gripper`

전체 동작 순서:

```text
1. /get_planning_scene, /apply_planning_scene, /compute_ik, /move_action 대기
2. /arm_controller/follow_joint_trajectory 대기
3. /gripper_controller/follow_joint_trajectory 대기
4. Box_0가 있으면 사용, 없으면 생성
5. Box_0를 world scene에 보이게 둔 상태로 대기
6. gripper open
7. MoveIt IK로 pre_grasp 자세 계산
8. MoveGroup으로 pre_grasp 계획/실행
9. gripper close
10. Box_0를 gripper에 attach
11. 목표 위치 위 pose 계산
12. MoveGroup으로 place_above 계획/실행
13. gripper release
14. Box_0 detach 후 목표 위치에 world object로 배치
15. arm을 시작 joint 자세로 복귀
```

목표 위치를 명시해서 실행:

```bash
ros2 run so_arm_moveit_config pick_place_box0.py \
  --place-x 0.17 \
  --place-y -0.24 \
  --place-z 0.06
```

시작 위치도 바꾸고 싶을 때:

```bash
ros2 run so_arm_moveit_config pick_place_box0.py \
  --start-x 0.00 \
  --start-y -0.24 \
  --start-z 0.06 \
  --place-x 0.17 \
  --place-y -0.24 \
  --place-z 0.06
```

arm 복귀를 하지 않으려면:

```bash
ros2 run so_arm_moveit_config pick_place_box0.py --no-return-home
```

## 10. 자동 Pick & Place 검증 결과

검증된 최종 실행 로그 요약:

```text
Box_0 was not found in PlanningScene. Creating it at (0.000, -0.240, 0.060).
Using Box_0 at (0.000, -0.240, 0.060), size~0.050
Box_0 is visible in the world scene. Waiting 2.0s before moving.
Moving gripper open: Jaw=0.800
Planning/executing arm move: pre_grasp
Moving gripper close: Jaw=0.000
Planning/executing arm move: place_above
Moving gripper release: Jaw=0.800
Returning arm to the captured start posture.
Done. Box_0 placed at (0.170, -0.240, 0.060).
```

최종 PlanningScene:

```text
Box_0
frame_id: base
position:
  x: 0.17
  y: -0.24
  z: 0.06
size:
  0.05 x 0.05 x 0.05
```

최종 joint state:

```text
Rotation: 0.0
Pitch: 0.0
Elbow: 0.0
Wrist_Pitch: 0.0
Wrist_Roll: 0.0
Jaw: 0.8
```

즉, 큐브 생성, 접근, grasp 표현, 이동, 목표 위치 place, arm home 복귀까지 정상 동작을 확인했습니다.

## 11. 자주 발생한 문제와 해결

### 11.1 Wrist_Roll 누락

증상:

- `/joint_states`에 `Wrist_Roll`이 없거나 controller/MoveIt 간 joint mismatch
- RViz에서 gripper/jaw TF가 불안정

해결:

- SRDF arm chain tip을 `gripper`로 설정
- MoveIt controller joints와 ros2_control controller joints에 `Wrist_Roll` 포함
- ros2_control xacro와 `initial_positions.yaml`에도 `Wrist_Roll` 포함

### 11.2 MoveGroup이 controller를 못 찾음

증상:

```text
No action namespace specified for controller
Returned 0 controllers in list
```

해결:

`moveit_controllers.yaml`에 추가:

```yaml
action_ns: follow_joint_trajectory
default: true
```

### 11.3 joint_limits type 오류

증상:

```text
parameter 'robot_description_planning.joint_limits.Rotation.max_velocity'
has invalid type: expected [double] got [integer]
```

해결:

`joint_limits.yaml`의 숫자 값을 실수형으로 작성:

```yaml
max_velocity: 10.0
max_acceleration: 0.0
```

### 11.4 중복 publisher 충돌

증상:

- RViz RobotModel 흔들림
- `/joint_states` 값 튐
- TF 불안정

해결:

MoveIt 실행 모드에서는 아래만 사용:

```bash
ros2 launch so_arm_moveit_config demo.launch.py
```

다음 조합과 혼용하지 않기:

```bash
robot_state_publisher + joint_state_publisher_gui + rviz2
```

### 11.5 RViz Scene Objects에서 만든 큐브가 스크립트에서 안 보임

증상:

```text
Box_0 was not found in PlanningScene. Creating it...
```

원인:

- RViz에서 object를 만들었지만 `Publish`를 누르지 않음

해결:

- `Scene Objects` 탭에서 위치/크기 조정 후 `Publish`
- 또는 스크립트 기본 자동 생성 기능 사용

## 12. GitHub 업로드 전 확인

업로드 대상은 `~/soarm_ws/src` 내부입니다.

권장 포함:

- `SO-ARM_ROS2_URDF/`
- `so_arm_moveit_config/`
- `SO_ARM_EXECUTION_CHECKLIST.md`
- `SO_ARM_PROJECT_STATUS.md`
- `SO_ARM_MOVEIT_FULL_WORKFLOW.md`
- `README.md`
- `.gitignore`

권장 제외:

- `build/`
- `install/`
- `log/`
- Python cache
- ROS log
- RViz 임시 백업 파일

주의:

현재 `SO-ARM_ROS2_URDF` 폴더는 별도 git repository입니다. `src` 전체를 하나의 GitHub repository로 올릴 경우, 이 nested `.git`을 어떻게 처리할지 결정해야 합니다.

선택지:

1. monorepo로 올리기
   - `SO-ARM_ROS2_URDF/.git`을 제거하거나 별도 백업 후 `src` 루트에서 새 git repo 생성
   - 모든 소스가 하나의 GitHub repo에 포함됨
2. submodule로 유지
   - `SO-ARM_ROS2_URDF`를 Git submodule로 등록
   - upstream 히스토리를 유지할 수 있음
   - clone 시 `--recursive` 또는 `git submodule update --init --recursive` 필요

개인 프로젝트 백업/공유 목적이면 monorepo 방식이 단순합니다.

