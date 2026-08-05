# Dashboard V2 fixture

`dashboard-v2-final.jsonl` is a compact 12-second slice of the clean,
untouched `straight-through-exit` route used in the final V2 Arm validation.
It contains all detection ticks and one trajectory sample per 100 ms, which is
enough to drive the real ROS 2 model and its direct-perception monitors in the
interactive dashboard without distributing a multi-hundred-megabyte simulator
recording.

The fixture is for local interaction only. It is not a benchmark input and
must not be used to derive latency, throughput, or detection-rate claims. Those
claims remain scoped to the full frozen validation protocol in
[`../../reports/v2-final-arm-route-validation.md`](../../reports/v2-final-arm-route-validation.md).
