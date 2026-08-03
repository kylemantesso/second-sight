"""Generate deterministic OpenSCENARIO route variants from a pinned base."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def ego_lane_positions(scenario: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the ego teleport and goal lane positions in an OpenSCENARIO mapping."""
    private_actions = scenario["OpenSCENARIO"]["Storyboard"]["Init"]["Actions"]["Private"]
    ego = next(action for action in private_actions if action["entityRef"] == "ego")
    actions = ego["PrivateAction"]
    start = next(action for action in actions if "TeleportAction" in action)
    goal = next(action for action in actions if "RoutingAction" in action)
    return (
        start["TeleportAction"]["Position"]["LanePosition"],
        goal["RoutingAction"]["AcquirePositionAction"]["Position"]["LanePosition"],
    )


def apply_lane_position(position: dict[str, Any], replacement: dict[str, Any]) -> None:
    """Replace only the lane and longitudinal placement fields of one position."""
    for key in ("lane_id", "s", "offset"):
        if key not in replacement:
            raise ValueError(f"route variant is missing {key}")
    position["laneId"] = str(replacement["lane_id"])
    position["s"] = float(replacement["s"])
    position["offset"] = float(replacement["offset"])


def generate_route_variants(
    base_path: Path, variants_path: Path, output_dir: Path
) -> list[Path]:
    """Write named ego-start/goal variants without modifying the pinned base file."""
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    config = yaml.safe_load(variants_path.read_text(encoding="utf-8"))
    variants = config.get("variants", [])
    if not variants:
        raise ValueError("route variant configuration contains no variants")

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for variant in variants:
        try:
            variant_id = str(variant["id"])
            start_replacement = variant["ego_start"]
            goal_replacement = variant["ego_goal"]
        except KeyError as error:
            raise ValueError("route variant requires id, ego_start, and ego_goal") from error
        if not variant_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid route variant id: {variant_id}")
        scenario = deepcopy(base)
        start, goal = ego_lane_positions(scenario)
        apply_lane_position(start, start_replacement)
        apply_lane_position(goal, goal_replacement)
        output = output_dir / f"second-sight-{variant_id}.yaml"
        output.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        outputs.append(output)
    return outputs
