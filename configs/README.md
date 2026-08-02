# Configuration

Versioned fault scenarios, feature definitions, model parameters, and
evaluation thresholds belong here. Runtime secrets and machine-specific paths
do not.

`scenarios/latency/` contains one-fault scenarios for repeatable live latency
measurements. They use the same fault transformations as `all-faults.yaml`, but
each run starts with a fresh watchdog so its intentionally latched safe-stop
state does not suppress later timing records.
