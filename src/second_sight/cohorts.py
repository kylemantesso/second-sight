"""Versioned, route-aware selection of clean-data cohorts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

COHORT_NAMES = ("train", "validation", "final_test")


def load_cohort_manifest(path: Path, *, require_frozen: bool = False) -> dict[str, Any]:
    """Load and validate a clean-data cohort manifest.

    A route family may appear in exactly one cohort.  This is deliberately
    validated before any filenames are selected, preventing a final-test bag
    from being quietly included by a broad shell glob.
    """
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict) or content.get("schema_version") != 1:
        raise ValueError("cohort manifest must have schema_version: 1")
    if require_frozen and content.get("frozen") is not True:
        raise ValueError("cohort manifest must be frozen before it is used")
    cohorts = content.get("cohorts")
    if not isinstance(cohorts, dict) or set(cohorts) != set(COHORT_NAMES):
        raise ValueError("cohort manifest must define train, validation, and final_test")

    seen_routes: set[str] = set()
    for name in COHORT_NAMES:
        definition = cohorts[name]
        if not isinstance(definition, dict):
            raise ValueError(f"{name} cohort must be a mapping")
        route_ids = definition.get("route_ids")
        if not isinstance(route_ids, list) or not route_ids:
            raise ValueError(f"{name} cohort requires at least one route_id")
        for route_id in route_ids:
            if not isinstance(route_id, str) or not route_id:
                raise ValueError(f"{name} has an invalid route_id")
            if route_id in seen_routes:
                raise ValueError(f"route_id appears in more than one cohort: {route_id}")
            seen_routes.add(route_id)
    return content


def cohort_route_ids(manifest: dict[str, Any], cohort: str) -> tuple[str, ...]:
    """Return the explicit route IDs for one validated cohort."""
    if cohort not in COHORT_NAMES:
        raise ValueError(f"unknown cohort: {cohort}")
    return tuple(str(route_id) for route_id in manifest["cohorts"][cohort]["route_ids"])


def select_cohort_files(
    directory: Path,
    route_ids: tuple[str, ...],
    *,
    suffix: str,
) -> list[Path]:
    """Select files by exact route-ID prefix, preserving hyphenated IDs.

    Clean bag, stream, and feature names always begin with
    ``openadkit-clean-<route-id>-``.  Matching this explicit prefix avoids
    interpreting hyphens inside a route ID as field separators.
    """
    if not directory.is_dir():
        return []
    selected = []
    for route_id in route_ids:
        prefix = f"openadkit-clean-{route_id}-"
        matches = sorted(
            path
            for path in directory.iterdir()
            if path.name.startswith(prefix) and path.name.endswith(suffix)
        )
        selected.extend(matches)
    return selected


def select_manifest_cohort_files(
    manifest_path: Path,
    cohort: str,
    directory: Path,
    *,
    suffix: str,
    require_frozen: bool = True,
) -> list[Path]:
    """Select one frozen cohort's files from a local artifact directory."""
    manifest = load_cohort_manifest(manifest_path, require_frozen=require_frozen)
    return select_cohort_files(directory, cohort_route_ids(manifest, cohort), suffix=suffix)
