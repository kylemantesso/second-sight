import pytest

from second_sight.liveness import DetectionLiveness


def test_liveness_arms_after_first_detection_and_reports_once() -> None:
    liveness = DetectionLiveness(300)

    assert not liveness.timed_out(1_000_000_000)
    liveness.record_detection(1_000_000_000)
    assert not liveness.timed_out(1_299_999_999)
    assert liveness.timed_out(1_300_000_000)
    assert not liveness.timed_out(1_600_000_000)


def test_new_detection_clears_a_prior_liveness_report() -> None:
    liveness = DetectionLiveness(100)
    liveness.record_detection(1)
    assert liveness.timed_out(100_000_001)
    liveness.record_detection(200_000_000)
    assert not liveness.timed_out(250_000_000)
    assert liveness.timed_out(300_000_000)


def test_liveness_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="positive"):
        DetectionLiveness(0)
