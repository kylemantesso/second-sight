from pathlib import Path

import pytest
import yaml

from second_sight.cohorts import load_cohort_manifest, select_manifest_cohort_files


def write_manifest(path: Path, *, frozen: bool = True) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "frozen": frozen,
                "cohorts": {
                    "train": {"route_ids": ["north-approach-right-turn"]},
                    "validation": {"route_ids": ["npc1-crossing-route"]},
                    "final_test": {"route_ids": ["npc2-crossing-route"]},
                },
            }
        ),
        encoding="utf-8",
    )


def test_select_manifest_cohort_files_uses_complete_hyphenated_route_id(tmp_path: Path) -> None:
    manifest = tmp_path / "cohorts.yaml"
    write_manifest(manifest)
    selected = tmp_path / "openadkit-clean-north-approach-right-turn-pass-20260804.jsonl"
    selected.write_text("{}\n", encoding="utf-8")
    (tmp_path / "openadkit-clean-north-approach-other-pass-20260804.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "openadkit-clean-npc1-crossing-route-pass-20260804.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )

    paths = select_manifest_cohort_files(
        manifest, "train", tmp_path, suffix=".jsonl", require_frozen=True
    )

    assert paths == [selected]


def test_manifest_rejects_overlap_and_unfrozen_use(tmp_path: Path) -> None:
    manifest = tmp_path / "cohorts.yaml"
    write_manifest(manifest, frozen=False)

    with pytest.raises(ValueError, match="must be frozen"):
        load_cohort_manifest(manifest, require_frozen=True)

    write_manifest(manifest)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["cohorts"]["validation"]["route_ids"] = ["north-approach-right-turn"]
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValueError, match="more than one cohort"):
        load_cohort_manifest(manifest)
