# AWS Cost Ledger

This ledger records the measured AWS cost of Second Sight development in the
Sydney region. It is an estimate before tax: AWS Cost Explorer can take up to
24 hours to show current-day usage, so its `2026-08-02` result was still $0 at
the time of this update.

## Compute used

The benchmark host is `i-0cbb864101d450172`, a Linux `c8g.4xlarge` in
`ap-southeast-2`. AWS's public price catalogue returned an on-demand price of
**US$0.8304/hour** (US$0.000230667/second). Linux on-demand instances are
billed per second with a 60-second minimum; every recorded session exceeded
that minimum.

| Start (AEST) | Stop (AEST) | Runtime | Estimated compute cost |
| --- | --- | ---: | ---: |
| 2026-08-02 12:17:29 | 12:19:49 | 2m 20s | $0.03229 |
| 2026-08-02 13:33:39 | 13:35:18 | 1m 39s | $0.02284 |
| 2026-08-02 13:37:17 | 13:45:33 | 8m 16s | $0.11441 |
| 2026-08-02 14:28:19 | 14:32:16 | 3m 57s | $0.05467 |
| 2026-08-02 15:07:14 | 15:14:42 | 7m 28s | $0.10334 |
| 2026-08-02 18:05:29 | 18:20:49 | 15m 20s | $0.21221 |
| 2026-08-02 18:45:33 | 19:06:55 | 21m 22s | $0.29571 |
| 2026-08-02 19:20:06 | 19:34:41 | 14m 35s | $0.20183 |
| 2026-08-02 19:55:37 | 20:12:37 | 17m 00s | $0.23528 |
| 2026-08-02 20:37:42 | 20:43:11 | 5m 29s | $0.07589 |
| **Total** |  | **1h 37m 26s** | **$1.34848** |

The instance is currently **stopped**, so this compute charge is no longer
increasing. Re-starting it costs about **$0.01384 per minute** while it runs.

## Continuing storage cost

Stopping an EC2 instance does not stop EBS charges. The host retains encrypted
100 GB gp3 volume `vol-0981a48f080ac3c16`. Sydney gp3 storage is listed at
US$0.096 per GB-month:

- about **$9.60/month** while the volume exists;
- about **$0.3156/day**; and
- about **$0.01315/hour**.

From volume creation at 12:17:29 until the latest confirmed stop at 20:43:11,
its pro-rated storage cost is about **$0.11238**. It continues to accrue at the
rate above even though the instance is stopped. Do not delete the volume
without first preserving or intentionally discarding its cached Arm64 images
and artifacts.

## Artifact storage and total to date

The private benchmark bucket holds 166 objects totaling 40,782,410 bytes
(about 40.8 MB). It includes the repeated fast-path artifacts plus the causal
portable teleport traces, source logs, provenance, summaries, and checksums.
Storage and request charges remain below one cent at this scale; same-region
EC2-to-S3 transfers do not materially change this estimate.

| Category | Estimated cost through 2026-08-02 19:34 AEST |
| --- | ---: |
| EC2 compute | $1.34848 |
| Pro-rated 100 GB gp3 EBS | ~$0.11238 |
| S3 storage and requests | < $0.01 |
| **Total before tax** | **about $1.47** |

Check Cost Explorer the following day for the settled invoice value. Keep the
instance stopped whenever it is not actively benchmarking; the EBS volume is
the only meaningful ongoing charge in the current setup.
