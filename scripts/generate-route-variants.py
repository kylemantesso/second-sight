#!/usr/bin/env python3
"""Create versioned Second Sight route variants from the pinned Open AD Kit scenario."""

from __future__ import annotations

import argparse
from pathlib import Path

from second_sight.scenarios import generate_route_variants


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for output in generate_route_variants(args.base, args.variants, args.output_dir):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
