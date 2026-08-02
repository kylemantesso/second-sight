# macOS Development Setup

The Mac workflow covers model training, analysis, deterministic replay, and
containerized ROS 2 node development. It does not replace the Ubuntu Open AD
Kit environment or the final Graviton benchmark environment.

## Verified Host

- Apple Silicon (`arm64`)
- macOS 26
- 32 GB memory
- Homebrew
- Docker Desktop using Linux `aarch64` containers
- `uv` with Python 3.12

## Bootstrap

Install the required tools if they are not already present:

```bash
brew install uv python@3.12
brew install --cask docker-desktop
```

Start Docker Desktop, then initialize the project environment:

```bash
uv sync
uv run second-sight doctor
uv run pytest
uv run ruff check .
```

`uv` reads `.python-version` and creates an isolated `.venv`. Do not install
project packages into Homebrew's global Python.

## ROS 2 On macOS

ROS 2 Humble and Open AD Kit target Ubuntu 22.04. Rather than maintaining a
fragile native ROS installation, use the official Linux ROS image through
Docker Desktop:

```bash
./scripts/ros-smoke.sh
```

This starts publisher and subscriber containers on one Compose network and
verifies DDS discovery by receiving one `/second_sight/smoke` message. Application
components should join this network when they are added.

## Open AD Kit Demo

The upstream demo publishes native `linux/arm64` images. The project launcher
pins a tested upstream revision and clones it into the ignored
`.cache/openadkit_demo.autoware/` directory:

```bash
./scripts/openadkit.sh pull
./scripts/openadkit.sh start
```

The initial image download is several gigabytes. Once the containers are
running, open <http://localhost:6080/vnc.html>, click **Connect**, and enter the
password `openadkit`. Autoware can take a few minutes to initialize.

Useful controls:

```bash
./scripts/openadkit.sh status
./scripts/openadkit.sh topics
./scripts/openadkit.sh record 45
./scripts/openadkit.sh logs
./scripts/openadkit.sh stop
```

`start` runs the passing obstacle-avoidance configuration in the background
with a one-hour scenario timeout. `run` performs one foreground run instead.
Set `OPENADKIT_TIMEOUT` to override the timeout in seconds.

`record` starts a fresh scenario and captures the selected perception and
planning streams for the requested number of seconds. Bags are written under
`data/raw/` and ignored by Git.

The local clone is disposable. Remove `.cache/openadkit_demo.autoware/` if a
clean bootstrap is needed; the next launcher command recreates it at the pinned
revision.

Docker Desktop runs containers in a Linux VM. Host networking and multicast
behavior differ from native Linux, so multi-machine DDS discovery and latency
results from this setup are not representative. Keep all Mac ROS components
inside the same Compose project unless a DDS discovery server is configured.

## Data And Artifacts

Keep local generated files in these ignored locations:

- `data/raw/`: source ROS bags; never commit large recordings
- `data/processed/`: extracted feature tables
- `models/`: generated `.joblib` and `.onnx` models
- `reports/benchmarks/`: raw local benchmark runs

Small fixtures needed by tests may be committed under `tests/fixtures/`.
Before sharing larger bags or models, use object storage or Git LFS and record
their checksum and provenance.

## Environment Responsibilities

| Work | Mac | Ubuntu/Open AD Kit | Arm Linux |
| --- | --- | --- | --- |
| Python unit tests | Yes | Yes | Yes |
| Feature/model iteration | Yes | Yes | Yes |
| Bag replay node development | Docker | Yes | Yes |
| Full Autoware simulation | No | Yes | Optional |
| DDS isolation integration | Limited | Yes | Yes |
| Submission performance claims | No | No | Yes |

## Next Development Step

Use the clean bag to implement a ROS-independent tick schema and deterministic
replay reader. The selected topics, types, rates, and stop service are recorded
in [`interfaces.md`](interfaces.md).
