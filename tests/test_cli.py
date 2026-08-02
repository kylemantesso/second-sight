from second_sight import __version__
from second_sight.cli import build_parser, environment_report


def test_environment_report_contains_package_version() -> None:
    assert environment_report()["second-sight"] == __version__


def test_doctor_command_parses() -> None:
    assert build_parser().parse_args(["doctor"]).command == "doctor"
