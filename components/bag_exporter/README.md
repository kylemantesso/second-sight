# Bag Exporter

Converts selected Autoware ROS 2 bag messages into the versioned,
ROS-independent JSONL stream consumed by the portable Python package. It runs
inside the pinned planning-control image so custom Autoware message definitions
do not need to be installed on macOS.

```bash
./scripts/export-bag.sh data/raw/openadkit-clean-20260716T112843Z
uv run second-sight inspect data/processed/openadkit-clean-20260716T112843Z.jsonl
```
