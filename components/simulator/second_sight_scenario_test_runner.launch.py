"""Open AD Kit scenario runner with detections routed through the fault injector."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    arguments = {
        "record": LaunchConfiguration("record"),
        "scenario": LaunchConfiguration("scenario"),
        "sensor_model": LaunchConfiguration("sensor_model"),
        "vehicle_model": LaunchConfiguration("vehicle_model"),
        "initialize_duration": LaunchConfiguration("initialize_duration"),
        "global_timeout": LaunchConfiguration("global_timeout"),
        "global_frame_rate": LaunchConfiguration("global_frame_rate"),
        "launch_autoware": "false",
        "launch_rviz": "false",
    }
    original_launch = PathJoinSubstitution(
        [FindPackageShare("scenario_test_runner"), "launch", "scenario_test_runner.launch.py"]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("record", default_value="false"),
            DeclareLaunchArgument("scenario"),
            DeclareLaunchArgument("sensor_model", default_value="sample_sensor_kit"),
            DeclareLaunchArgument("vehicle_model", default_value="sample_vehicle"),
            DeclareLaunchArgument("initialize_duration", default_value="90"),
            DeclareLaunchArgument("global_timeout", default_value="3600"),
            DeclareLaunchArgument("global_frame_rate", default_value="20"),
            GroupAction(
                [
                    SetRemap(
                        src="/perception/object_recognition/detection/objects",
                        dst="/second_sight/perception/raw",
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(original_launch),
                        launch_arguments=arguments.items(),
                    ),
                ]
            ),
        ]
    )
