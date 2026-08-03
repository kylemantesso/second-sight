"""Generate deterministic OpenSCENARIO route and traffic variants from a pinned base."""

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


def apply_npc_speed(scenario: dict[str, Any], entity_ref: str, speed: float) -> None:
    """Set one NPC's target and controller speed without altering its route."""
    if speed <= 0:
        raise ValueError("NPC speed must be positive")

    private_actions = scenario["OpenSCENARIO"]["Storyboard"]["Init"]["Actions"]["Private"]
    npc = next((action for action in private_actions if action["entityRef"] == entity_ref), None)
    if npc is None:
        raise ValueError(f"NPC is not present in the base scenario: {entity_ref}")

    target_updated = False
    controller_updated = False
    for action in npc["PrivateAction"]:
        speed_action = action.get("LongitudinalAction", {}).get("SpeedAction")
        if speed_action is not None:
            speed_action["SpeedActionTarget"]["AbsoluteTargetSpeed"]["value"] = float(speed)
            target_updated = True
        controller = action.get("ControllerAction", {}).get("AssignControllerAction", {}).get(
            "Controller"
        )
        if controller is not None:
            properties = controller.get("Properties", {}).get("Property", [])
            for property_ in properties:
                if property_.get("name") == "maxSpeed":
                    property_["value"] = f"{speed:g}"
                    controller_updated = True
    if not target_updated or not controller_updated:
        raise ValueError(f"NPC lacks a target or controller speed action: {entity_ref}")


def apply_npc_start_position(
    scenario: dict[str, Any], entity_ref: str, replacement: dict[str, Any]
) -> None:
    """Move one NPC's initial teleport position without changing its route."""
    private_actions = scenario["OpenSCENARIO"]["Storyboard"]["Init"]["Actions"]["Private"]
    npc = next((action for action in private_actions if action["entityRef"] == entity_ref), None)
    if npc is None:
        raise ValueError(f"NPC is not present in the base scenario: {entity_ref}")
    teleport = next(
        (
            action.get("TeleportAction")
            for action in npc["PrivateAction"]
            if "TeleportAction" in action
        ),
        None,
    )
    if teleport is None:
        raise ValueError(f"NPC lacks an initial teleport action: {entity_ref}")
    apply_lane_position(teleport["Position"]["LanePosition"], replacement)


def replace_matching_lane_positions(
    value: Any, original: dict[str, Any], replacement: dict[str, Any]
) -> int:
    """Replace LanePositions equal to ``original`` below an OpenSCENARIO subtree."""
    replacements = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "LanePosition" and child == original:
                apply_lane_position(child, replacement)
                replacements += 1
            else:
                replacements += replace_matching_lane_positions(child, original, replacement)
    elif isinstance(value, list):
        for child in value:
            replacements += replace_matching_lane_positions(child, original, replacement)
    return replacements


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
        original_goal = deepcopy(goal)
        apply_lane_position(start, start_replacement)
        apply_lane_position(goal, goal_replacement)
        replace_matching_lane_positions(
            scenario["OpenSCENARIO"]["Storyboard"].get("Story", []), original_goal, goal_replacement
        )
        npc_speeds = variant.get("npc_speeds", {})
        if not isinstance(npc_speeds, dict):
            raise ValueError("npc_speeds must be a mapping of NPC name to positive speed")
        for entity_ref, speed in npc_speeds.items():
            apply_npc_speed(scenario, str(entity_ref), float(speed))
        npc_start_positions = variant.get("npc_start_positions", {})
        if not isinstance(npc_start_positions, dict):
            raise ValueError("npc_start_positions must map NPC names to lane positions")
        for entity_ref, position in npc_start_positions.items():
            if not isinstance(position, dict):
                raise ValueError("NPC start position must be a lane-position mapping")
            apply_npc_start_position(scenario, str(entity_ref), position)
        output = output_dir / f"second-sight-{variant_id}.yaml"
        output.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        outputs.append(output)
    return outputs
