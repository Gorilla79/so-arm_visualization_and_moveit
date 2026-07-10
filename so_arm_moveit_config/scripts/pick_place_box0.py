#!/usr/bin/env python3
import argparse
import copy
import math
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import Pose, PoseStamped, Quaternion
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (
    AttachedCollisionObject,
    CollisionObject,
    Constraints,
    JointConstraint,
    MoveItErrorCodes,
    PlanningScene,
    PlanningSceneComponents,
)
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene, GetPositionIK
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from trajectory_msgs.msg import JointTrajectoryPoint


ARM_JOINTS = ["Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll"]
TOUCH_LINKS = ["gripper", "jaw", "wrist"]


def quaternion_from_euler(roll, pitch, yaw):
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    q = Quaternion()
    q.w = cr * cp * cy + sr * sp * sy
    q.x = sr * cp * cy - cr * sp * sy
    q.y = cr * sp * cy + sr * cp * sy
    q.z = cr * cp * sy - sr * sp * cy
    return q


class PickPlaceBox0(Node):
    def __init__(self, args):
        super().__init__("pick_place_box0")
        self.args = args
        self.current_joint_state = None
        self.object_in_world = False

        self.create_subscription(JointState, "/joint_states", self._joint_state_cb, 10)
        self.get_scene = self.create_client(GetPlanningScene, "/get_planning_scene")
        self.apply_scene = self.create_client(ApplyPlanningScene, "/apply_planning_scene")
        self.compute_ik = self.create_client(GetPositionIK, "/compute_ik")
        self.move_group = ActionClient(self, MoveGroup, "/move_action")
        self.arm = ActionClient(
            self, FollowJointTrajectory, "/arm_controller/follow_joint_trajectory"
        )
        self.gripper = ActionClient(
            self, FollowJointTrajectory, "/gripper_controller/follow_joint_trajectory"
        )

    def _joint_state_cb(self, msg):
        self.current_joint_state = msg

    def wait_ready(self):
        for name, client in [
            ("/get_planning_scene", self.get_scene),
            ("/apply_planning_scene", self.apply_scene),
            ("/compute_ik", self.compute_ik),
        ]:
            self.get_logger().info(f"Waiting for {name}...")
            if not client.wait_for_service(timeout_sec=10.0):
                raise RuntimeError(f"{name} service is not available")

        self.get_logger().info("Waiting for /move_action...")
        if not self.move_group.wait_for_server(timeout_sec=15.0):
            raise RuntimeError("/move_action action server is not available")

        self.get_logger().info("Waiting for /arm_controller/follow_joint_trajectory...")
        if not self.arm.wait_for_server(timeout_sec=15.0):
            raise RuntimeError("arm FollowJointTrajectory action server is not available")

        self.get_logger().info("Waiting for /gripper_controller/follow_joint_trajectory...")
        if not self.gripper.wait_for_server(timeout_sec=15.0):
            raise RuntimeError("gripper FollowJointTrajectory action server is not available")

        deadline = time.time() + 10.0
        while rclpy.ok() and self.current_joint_state is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if self.current_joint_state is None:
            raise RuntimeError("No /joint_states message received")

    def call(self, client, request, timeout=10.0):
        future = client.call_async(request)
        deadline = time.time() + timeout
        while rclpy.ok() and not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if not future.done():
            raise RuntimeError(f"Service call timed out: {client.srv_name}")
        return future.result()

    def get_or_create_box(self):
        req = GetPlanningScene.Request()
        req.components.components = PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
        scene = self.call(self.get_scene, req).scene
        for obj in scene.world.collision_objects:
            if obj.id == self.args.object_id:
                self.object_in_world = True
                return obj

        self.get_logger().warn(
            f"{self.args.object_id} was not found in PlanningScene. Creating it at "
            f"({self.args.start_x:.3f}, {self.args.start_y:.3f}, {self.args.start_z:.3f})."
        )
        box = CollisionObject()
        box.id = self.args.object_id
        box.header.frame_id = self.args.frame
        box.operation = CollisionObject.ADD
        primitive = SolidPrimitive()
        primitive.type = SolidPrimitive.BOX
        primitive.dimensions = [self.args.cube_size, self.args.cube_size, self.args.cube_size]
        box.primitives.append(primitive)
        pose = Pose()
        pose.orientation.w = 1.0
        pose.position.x = self.args.start_x
        pose.position.y = self.args.start_y
        pose.position.z = self.args.start_z
        box.primitive_poses.append(pose)
        self.apply_world_objects([box])
        self.object_in_world = True
        return box

    def object_center_and_size(self, obj):
        pose = Pose()
        pose.orientation.w = 1.0
        pose.position.x = obj.pose.position.x
        pose.position.y = obj.pose.position.y
        pose.position.z = obj.pose.position.z
        if obj.primitive_poses:
            pose.position.x += obj.primitive_poses[0].position.x
            pose.position.y += obj.primitive_poses[0].position.y
            pose.position.z += obj.primitive_poses[0].position.z
            pose.orientation = obj.primitive_poses[0].orientation
        size = self.args.cube_size
        if obj.primitives and obj.primitives[0].dimensions:
            size = max(obj.primitives[0].dimensions)
        return pose, size

    def apply_world_objects(self, objects):
        scene = PlanningScene()
        scene.is_diff = True
        scene.world.collision_objects = objects
        req = ApplyPlanningScene.Request()
        req.scene = scene
        res = self.call(self.apply_scene, req)
        if not res.success:
            raise RuntimeError("Failed to apply planning scene diff")

    def remove_world_object(self, object_id):
        obj = CollisionObject()
        obj.id = object_id
        obj.header.frame_id = self.args.frame
        obj.operation = CollisionObject.REMOVE
        self.apply_world_objects([obj])
        self.object_in_world = False

    def attach_box(self, obj):
        attached = AttachedCollisionObject()
        attached.link_name = self.args.attach_link
        attached.touch_links = TOUCH_LINKS
        attached.object.id = obj.id
        attached.object.header.frame_id = self.args.attach_link
        attached.object.operation = CollisionObject.ADD
        if obj.primitives:
            attached.object.primitives = copy.deepcopy(obj.primitives)
        else:
            primitive = SolidPrimitive()
            primitive.type = SolidPrimitive.BOX
            primitive.dimensions = [self.args.cube_size, self.args.cube_size, self.args.cube_size]
            attached.object.primitives = [primitive]
        attached_pose = Pose()
        attached_pose.orientation.w = 1.0
        attached_pose.position.x = self.args.attached_offset_x
        attached_pose.position.y = self.args.attached_offset_y
        attached_pose.position.z = self.args.attached_offset_z
        attached.object.primitive_poses = [attached_pose]

        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [attached]
        req = ApplyPlanningScene.Request()
        req.scene = scene
        res = self.call(self.apply_scene, req)
        if not res.success:
            raise RuntimeError("Failed to attach object")
        self.object_in_world = False

    def place_box(self, obj):
        detach = AttachedCollisionObject()
        detach.link_name = self.args.attach_link
        detach.object.id = obj.id
        detach.object.operation = CollisionObject.REMOVE

        placed = copy.deepcopy(obj)
        placed.header.frame_id = self.args.frame
        placed.pose = Pose()
        placed.pose.orientation.w = 1.0
        placed.primitive_poses = [Pose()]
        placed.primitive_poses[0].orientation.w = 1.0
        placed.primitive_poses[0].position.x = self.args.place_x
        placed.primitive_poses[0].position.y = self.args.place_y
        placed.primitive_poses[0].position.z = self.args.place_z
        placed.operation = CollisionObject.ADD

        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [detach]
        scene.world.collision_objects = [placed]
        req = ApplyPlanningScene.Request()
        req.scene = scene
        res = self.call(self.apply_scene, req)
        if not res.success:
            raise RuntimeError("Failed to detach/place object")
        self.object_in_world = True

    def pose_stamped(self, x, y, z, orientation):
        ps = PoseStamped()
        ps.header.frame_id = self.args.frame
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.pose.position.x = x
        ps.pose.position.y = y
        ps.pose.position.z = z
        ps.pose.orientation = orientation
        return ps

    def ik_for_pose(self, pose_stamped):
        req = GetPositionIK.Request()
        req.ik_request.group_name = self.args.arm_group
        req.ik_request.ik_link_name = self.args.ik_link
        req.ik_request.pose_stamped = pose_stamped
        req.ik_request.avoid_collisions = False
        req.ik_request.robot_state.joint_state = self.current_joint_state
        req.ik_request.timeout = Duration(sec=2)
        res = self.call(self.compute_ik, req, timeout=5.0)
        if res.error_code.val != MoveItErrorCodes.SUCCESS:
            return None
        positions = dict(zip(res.solution.joint_state.name, res.solution.joint_state.position))
        if not all(name in positions for name in ARM_JOINTS):
            return None
        return {name: positions[name] for name in ARM_JOINTS}

    def solve_pose(self, x, y, z):
        candidates = [
            quaternion_from_euler(0.0, 0.0, 0.0),
            quaternion_from_euler(math.pi, 0.0, 0.0),
            quaternion_from_euler(0.0, math.pi / 2.0, 0.0),
            quaternion_from_euler(0.0, -math.pi / 2.0, 0.0),
            quaternion_from_euler(math.pi / 2.0, 0.0, 0.0),
            quaternion_from_euler(-math.pi / 2.0, 0.0, 0.0),
        ]
        for orientation in candidates:
            ps = self.pose_stamped(x, y, z, orientation)
            joints = self.ik_for_pose(ps)
            if joints is not None:
                return joints
        raise RuntimeError(f"No IK solution for {self.args.ik_link} at ({x:.3f}, {y:.3f}, {z:.3f})")

    def move_to_joints(self, label, joints):
        goal = MoveGroup.Goal()
        goal.request.group_name = self.args.arm_group
        goal.request.num_planning_attempts = 10
        goal.request.allowed_planning_time = 5.0
        goal.request.max_velocity_scaling_factor = self.args.velocity_scale
        goal.request.max_acceleration_scaling_factor = self.args.acceleration_scale
        goal.request.start_state.joint_state = self.current_joint_state
        goal.request.workspace_parameters.header.frame_id = self.args.frame
        goal.request.workspace_parameters.min_corner.x = -0.5
        goal.request.workspace_parameters.min_corner.y = -0.5
        goal.request.workspace_parameters.min_corner.z = -0.1
        goal.request.workspace_parameters.max_corner.x = 0.5
        goal.request.workspace_parameters.max_corner.y = 0.5
        goal.request.workspace_parameters.max_corner.z = 0.6

        constraints = Constraints()
        constraints.name = label
        for name in ARM_JOINTS:
            jc = JointConstraint()
            jc.joint_name = name
            jc.position = joints[name]
            jc.tolerance_above = 0.03
            jc.tolerance_below = 0.03
            jc.weight = 1.0
            constraints.joint_constraints.append(jc)
        goal.request.goal_constraints = [constraints]
        goal.planning_options.plan_only = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 2
        goal.planning_options.replan_delay = 0.2

        self.get_logger().info(f"Planning/executing arm move: {label}")
        send_future = self.move_group.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future)
        handle = send_future.result()
        if handle is None or not handle.accepted:
            raise RuntimeError(f"MoveGroup rejected goal: {label}")
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result
        if result.error_code.val != MoveItErrorCodes.SUCCESS:
            if not self.args.allow_controller_fallback:
                raise RuntimeError(f"MoveGroup failed {label}: error_code={result.error_code.val}")
            self.get_logger().warn(
                f"MoveGroup failed {label}: error_code={result.error_code.val}. "
                "Falling back to arm_controller joint execution."
            )
            self.execute_arm_joints(joints, label)

    def execute_arm_joints(self, joints, label):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = ARM_JOINTS
        point = JointTrajectoryPoint()
        point.positions = [joints[name] for name in ARM_JOINTS]
        point.time_from_start.sec = 3
        goal.trajectory.points = [point]

        send_future = self.arm.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future)
        handle = send_future.result()
        if handle is None or not handle.accepted:
            raise RuntimeError(f"arm_controller rejected goal: {label}")
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result
        if result.error_code != FollowJointTrajectory.Result.SUCCESSFUL:
            raise RuntimeError(f"arm_controller failed {label}: {result.error_string}")

    def set_gripper(self, position, label):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = ["Jaw"]
        point = JointTrajectoryPoint()
        point.positions = [position]
        point.time_from_start.sec = 1
        goal.trajectory.points = [point]
        self.get_logger().info(f"Moving gripper {label}: Jaw={position:.3f}")
        send_future = self.gripper.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future)
        handle = send_future.result()
        if handle is None or not handle.accepted:
            raise RuntimeError(f"Gripper rejected goal: {label}")
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result
        if result.error_code != FollowJointTrajectory.Result.SUCCESSFUL:
            raise RuntimeError(f"Gripper failed {label}: {result.error_string}")

    def current_arm_joints(self):
        positions = dict(zip(self.current_joint_state.name, self.current_joint_state.position))
        if not all(name in positions for name in ARM_JOINTS):
            missing = [name for name in ARM_JOINTS if name not in positions]
            raise RuntimeError(f"Current joint state is missing arm joints: {missing}")
        return {name: positions[name] for name in ARM_JOINTS}

    def run(self):
        self.wait_ready()
        home_joints = self.current_arm_joints()
        obj = self.get_or_create_box()
        center, size = self.object_center_and_size(obj)
        grasp_z = center.position.z + max(self.args.grasp_clearance, size * 0.5)
        pregrasp_z = grasp_z + self.args.approach_height
        place_pre_z = self.args.place_z + self.args.approach_height

        self.get_logger().info(
            f"Using {obj.id} at ({center.position.x:.3f}, {center.position.y:.3f}, "
            f"{center.position.z:.3f}), size~{size:.3f}"
        )
        self.get_logger().info(
            f"{obj.id} is visible in the world scene. Waiting {self.args.scene_settle_time:.1f}s "
            "before moving."
        )
        time.sleep(self.args.scene_settle_time)

        if self.args.remove_object_during_approach:
            self.get_logger().info(
                f"Temporarily removing {obj.id} from world collision during approach."
            )
            self.remove_world_object(obj.id)

        self.set_gripper(self.args.open_jaw, "open")
        pregrasp = self.solve_pose(center.position.x, center.position.y, pregrasp_z)
        self.move_to_joints("pre_grasp", pregrasp)

        # In the fake controller demo, grasp contact is represented by attaching the object.
        self.set_gripper(self.args.close_jaw, "close")
        self.attach_box(obj)

        place_above = self.solve_pose(self.args.place_x, self.args.place_y, place_pre_z)
        self.move_to_joints("place_above", place_above)

        self.set_gripper(self.args.open_jaw, "release")
        self.place_box(obj)
        if self.args.return_home:
            self.get_logger().info("Returning arm to the captured start posture.")
            self.execute_arm_joints(home_joints, "home")
        self.get_logger().info(
            f"Done. {obj.id} placed at ({self.args.place_x:.3f}, "
            f"{self.args.place_y:.3f}, {self.args.place_z:.3f})."
        )


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-id", default="Box_0")
    parser.add_argument("--frame", default="base")
    parser.add_argument("--arm-group", default="arm")
    parser.add_argument("--ik-link", default="gripper")
    parser.add_argument("--attach-link", default="gripper")
    parser.add_argument("--cube-size", type=float, default=0.05)
    parser.add_argument("--start-x", type=float, default=0.0)
    parser.add_argument("--start-y", type=float, default=-0.24)
    parser.add_argument("--start-z", type=float, default=0.06)
    parser.add_argument("--place-x", type=float, default=0.17)
    parser.add_argument("--place-y", type=float, default=-0.24)
    parser.add_argument("--place-z", type=float, default=0.06)
    parser.add_argument("--approach-height", type=float, default=0.10)
    parser.add_argument("--grasp-clearance", type=float, default=0.04)
    parser.add_argument("--open-jaw", type=float, default=0.8)
    parser.add_argument("--close-jaw", type=float, default=0.0)
    parser.add_argument("--attached-offset-x", type=float, default=0.0)
    parser.add_argument("--attached-offset-y", type=float, default=0.0)
    parser.add_argument("--attached-offset-z", type=float, default=0.0)
    parser.add_argument("--velocity-scale", type=float, default=0.25)
    parser.add_argument("--acceleration-scale", type=float, default=0.25)
    parser.add_argument("--scene-settle-time", type=float, default=1.5)
    parser.add_argument(
        "--no-return-home",
        dest="return_home",
        action="store_false",
        help="Do not return the arm to the joint posture captured at script start.",
    )
    parser.add_argument(
        "--remove-object-collision-during-approach",
        dest="remove_object_during_approach",
        action="store_true",
        help="Hide/remove Box_0 before moving to pre-grasp. Default keeps it visible.",
    )
    parser.add_argument(
        "--no-controller-fallback",
        dest="allow_controller_fallback",
        action="store_false",
        help="Fail instead of sending IK joint targets directly to controllers when MoveGroup planning fails.",
    )
    parser.set_defaults(
        remove_object_during_approach=False,
        allow_controller_fallback=True,
        return_home=True,
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rclpy.init()
    node = PickPlaceBox0(args)
    try:
        node.run()
    except Exception as exc:
        node.get_logger().error(str(exc))
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
