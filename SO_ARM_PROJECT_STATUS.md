# SO-ARM MoveIt 통합 진행 현황 정리 (Codex 전달용)

작성일: 2026-07-09  
환경: Ubuntu + ROS 2 Humble  
워크스페이스: `~/soarm_ws`  
주요 패키지:
- `SO-ARM_ROS2_URDF` (URDF/Xacro 및 메쉬)
- `so_arm_moveit_config` (MoveIt Setup Assistant 생성)

---

## 1) 목표 (User Intent)

최종 목표:
1. SO-ARM 로봇 모델을 ROS2/MoveIt2에서 정상 로드
2. RViz MotionPlanning에서 `arm`, `gripper` 그룹 계획/실행 가능 상태 확보
3. 추후 Pick & Place 자동화 (블록 잡기/이동/놓기) 구현
4. 필요 시 fake/sim 기반 검증 후 실제 하드웨어 연동으로 확장

---

## 2) 지금까지 진행한 내용

### 2.1 MoveIt Setup Assistant 설정
- Planning Groups:
  - `arm` 생성
  - `gripper` 생성 (`Jaw` 조인트 포함)
- End Effector:
  - `gripper_eef` 설정
  - parent link = `wrist`
  - parent group = `arm`
- Passive Joints:
  - 별도 없음 (기본 Active 유지)
- ros2_control URDF interfaces:
  - command: `position`
  - state: `position`, `velocity`
- ROS 2 Controllers:
  - `arm_controller` (JointTrajectoryController)
  - `gripper_controller` (JointTrajectoryController)
- MoveIt Controllers:
  - 위 2개를 FollowJointTrajectory로 매핑
- Config 패키지 생성:
  - `~/soarm_ws/src/so_arm_moveit_config`

---

## 3) 발생 이슈 및 해결 히스토리

### 이슈 A: `package.xml` maintainer/email 누락으로 빌드 실패
증상:
- `Invalid email "" for person ""`
- `Maintainers must have an email address`

조치:
- `so_arm_moveit_config/package.xml`에서 maintainer/author name,email 채움
- 이후 빌드 성공

---

### 이슈 B: RViz에서 로봇이 안 보이거나 MotionPlanning 빨간 에러
원인 복합:
1. `/joint_states` 중복 퍼블리셔 (jitter/튀는 현상)
   - `joint_state_broadcaster` + `joint_state_publisher` 동시 publish
2. `robot_state_publisher` 중복 실행
3. MoveIt 실행 모드와 수동(JSP GUI) 모드 혼용

조치:
- `pkill`로 중복 노드 정리
- 모드 분리:
  - 수동 시각화 모드: `robot_state_publisher + joint_state_publisher_gui + rviz2`
  - MoveIt 모드: `demo.launch.py` 단독 중심

---

### 이슈 C: `Wrist_Roll` 누락으로 TF/그룹 불일치
관찰:
- 어떤 `/joint_states`에는 `Wrist_Roll` 포함, 어떤 경우 누락
- RViz에 `No transform from [gripper]/[jaw] to [base]` 발생
- 설정 파일 grep에서 `Wrist_Roll` 누락 확인

핵심 원인:
- MoveIt/Controller 설정이 5축처럼 구성되어 Wrist_Roll 미반영
- SRDF arm group chain tip이 `wrist`여서 roll이 arm 그룹 밖으로 빠질 가능성

필수 수정 방향:
1. `so101_new_calib.srdf` arm chain tip을 `gripper`로 변경
2. `moveit_controllers.yaml` arm joints에 `Wrist_Roll` 추가
3. `ros2_controllers.yaml` arm joints에 `Wrist_Roll` 추가

---

## 4) 현재 상태 요약 (중요)

작동 확인:
- URDF 파싱 및 robot_state_publisher 동작 가능
- RViz RobotModel 표시 가능
- Controller manager에서 컨트롤러 active 확인 가능 (`arm_controller`, `gripper_controller`, `joint_state_broadcaster`)
- `/move_group` 노드가 뜨는 시점도 확인됨

남은 핵심 정리:
- 구성 파일에서 `Wrist_Roll` 완전 일치 반영
- MoveIt 실행 시 MotionPlanning 상태 안정화 (`No Planning Scene Loaded` 제거)
- Planning Group 드롭다운에서 정상 선택/Plan/Execute 검증

---

## 5) Codex에게 요청할 작업 (명확 지시)

Codex가 수행할 것:
1. 아래 3개 파일을 일관성 있게 수정
   - `~/soarm_ws/src/so_arm_moveit_config/config/so101_new_calib.srdf`
   - `~/soarm_ws/src/so_arm_moveit_config/config/moveit_controllers.yaml`
   - `~/soarm_ws/src/so_arm_moveit_config/config/ros2_controllers.yaml`
2. 수정 후 빌드/런치 절차 제시
3. 검증 명령 결과 기준으로 Pass/Fail 체크리스트 제공
4. 최종적으로 Pick & Place 데모 실행 가능한 최소 Python 예제 제공
   - arm + gripper 그룹 사용
   - pre-grasp / grasp / lift / place / release 순서

---

## 6) 참고 로그 포인트

- `ros2 topic info /joint_states -v`에서 중복 퍼블리셔 확인 경험 있음
- `/move_group` 없을 때 `ros2 param get /move_group ...` => Node not found
- `kdl_parser` root inertia warning은 경고이며 치명적 원인은 아님

---

## 7) 최종 성공 기준 (Definition of Done)

아래를 모두 만족하면 완료:
1. `ros2 launch so_arm_moveit_config demo.launch.py` 실행 시 RViz MotionPlanning green/정상
2. Planning Group에서 `arm`, `gripper` 선택 가능
3. arm 계획/실행 + gripper open/close 실행 가능
4. `/joint_states` 흐름 안정 (의도한 모드에서 publisher 단일/정상)
5. Pick & Place 데모 스크립트 1회 성공 실행