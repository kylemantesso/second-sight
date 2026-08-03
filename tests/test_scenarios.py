from pathlib import Path

import yaml

from second_sight.scenarios import generate_route_variants


def test_route_variant_generator_replaces_only_ego_start_and_goal(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "OpenSCENARIO": {
                    "Storyboard": {
                        "Init": {
                            "Actions": {
                                "Private": [
                                    {
                                        "entityRef": "ego",
                                        "PrivateAction": [
                                            {
                                                "TeleportAction": {
                                                    "Position": {
                                                        "LanePosition": {
                                                            "laneId": "1", "s": 1.0, "offset": 0.0
                                                        }
                                                    }
                                                }
                                            },
                                            {
                                                "RoutingAction": {
                                                    "AcquirePositionAction": {
                                                        "Position": {
                                                            "LanePosition": {
                                                                "laneId": "2",
                                                                "s": 2.0,
                                                                "offset": 0.0,
                                                            }
                                                        }
                                                    }
                                                }
                                            },
                                        ],
                                    },
                                    {"entityRef": "npc", "PrivateAction": []},
                                ]
                            }
                        }
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    variants = tmp_path / "variants.yaml"
    variants.write_text(
        yaml.safe_dump(
            {
                "variants": [
                    {
                        "id": "test-route",
                        "ego_start": {"lane_id": "10", "s": 3.0, "offset": -0.1},
                        "ego_goal": {"lane_id": "20", "s": 4.0, "offset": 0.2},
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    outputs = generate_route_variants(base, variants, tmp_path / "output")

    assert outputs == [tmp_path / "output" / "second-sight-test-route.yaml"]
    result = yaml.safe_load(outputs[0].read_text(encoding="utf-8"))
    actions = result["OpenSCENARIO"]["Storyboard"]["Init"]["Actions"]["Private"][0][
        "PrivateAction"
    ]
    assert actions[0]["TeleportAction"]["Position"]["LanePosition"] == {
        "laneId": "10",
        "s": 3.0,
        "offset": -0.1,
    }
    assert actions[1]["RoutingAction"]["AcquirePositionAction"]["Position"]["LanePosition"] == {
        "laneId": "20",
        "s": 4.0,
        "offset": 0.2,
    }
