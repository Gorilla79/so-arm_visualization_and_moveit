# SO-ARM MoveIt 실행 및 점검 체크리스트

작성일: 2026-07-09  
목적: 설정 일관성 확보 + MoveIt 동작 안정화 + Pick&Place 준비

---

## A. 사전 정리 (중복 노드 제거)

```bash
pkill -f joint_state_publisher
pkill -f joint_state_broadcaster
pkill -f robot_state_publisher
pkill -f move_group
pkill -f ros2_control_node
pkill -f rviz2
```

환경 소스:
```bash
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash
```

---

## B. 필수 설정 수정

## B-1) SRDF 수정
파일: `~/soarm_ws/src/so_arm_moveit_config/config/so101_new_calib.srdf`

기존:
```xml
<group name="arm">
    <chain base_link="base" tip_link="wrist"/>
</group>
```

수정:
```xml
<group name="arm">
    <chain base_link="base" tip_link="gripper"/>
</group>
```

---

## B-2) MoveIt controller joints 수정
파일: `~/soarm_ws/src/so_arm_moveit_config/config/moveit_controllers.yaml`

`arm_controller.joints`를 아래처럼 5축(+roll)으로:
```yaml
arm_controller:
  type: FollowJointTrajectory
  joints:
    - Rotation
    - Pitch
    - Elbow
    - Wrist_Pitch
    - Wrist_Roll
```

---

## B-3) ros2_control controller joints 수정
파일: `~/soarm_ws/src/so_arm_moveit_config/config/ros2_controllers.yaml`

`arm_controller.ros__parameters.joints`:
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

---

## C. 빌드

```bash
cd ~/soarm_ws
colcon build --symlink-install --packages-select so_arm_moveit_config
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash
```

---

## D. MoveIt 단독 실행 (중요: 수동 JSP GUI와 혼용 금지)

```bash
ros2 launch so_arm_moveit_config demo.launch.py
```

---

## E. 필수 검증 명령

새 터미널에서:

```bash
source /opt/ros/humble/setup.bash
source ~/soarm_ws/install/setup.bash
ros2 node list | grep -E "move_group|controller_manager|joint_state_broadcaster|robot_state_publisher|rviz"
```

기대:
- `/move_group`
- `/controller_manager`
- `/joint_state_broadcaster`
- `/robot_state_publisher`
- `/rviz` 또는 `/rviz2`

컨트롤러 상태:
```bash
ros2 control list_controllers
```
기대:
- `arm_controller ... active`
- `gripper_controller ... active`
- `joint_state_broadcaster ... active`

조인트 상태:
```bash
ros2 topic echo /joint_states --once
```
기대:
- `name` 목록에 반드시 `Wrist_Roll` 포함

---

## F. RViz 점검

1. MotionPlanning 패널에서 Status 확인
2. Planning Group 드롭다운:
   - `arm`
   - `gripper`
3. `arm` 선택 후 Plan/Execute
4. `gripper` 선택 후 open/close Plan/Execute

---

## G. 실패 시 즉시 점검 포인트

1. `/move_group` 미존재:
```bash
ros2 node list | grep move_group
```
없으면 launch 터미널 에러 로그 확인

2. Planning Scene 미로드:
- MotionPlanning Status 탭 에러 문자열 확인

3. 조인트 누락:
```bash
grep -R "Wrist_Roll" -n ~/soarm_ws/src/so_arm_moveit_config/config
```
결과 없으면 설정 누락

4. 중복 퍼블리셔:
```bash
ros2 topic info /joint_states -v
```
필요 이상 publisher면 충돌

---

## H. 운용 모드 규칙 (중요)

- **수동 시각화 모드**
  - `robot_state_publisher + joint_state_publisher_gui + rviz2`
- **MoveIt 계획 모드**
  - `demo.launch.py` 중심
  - 수동 JSP GUI 동시 사용 지양

---

## I. 다음 단계 (Pick & Place)

MoveIt 정상화 완료 후 진행:
1. PlanningScene에 박스 객체 추가
2. Pre-grasp 접근
3. Gripper close
4. Attach object
5. Place pose로 이동
6. Gripper open
7. Detach object

(별도 `pick_place_demo.py` 작성 권장)