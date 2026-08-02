import numpy as np

from second_sight.model import (
    GUARDRAIL_FEATURES,
    MODEL_FEATURE_NAMES,
    learn_guardrails,
    score_guardrails,
    select_guardrail_violations,
)


def test_guardrails_accept_clean_values_and_flag_safety_feature_violations() -> None:
    clean = np.zeros((3, len(MODEL_FEATURE_NAMES)), dtype=np.float64)
    clean[:, MODEL_FEATURE_NAMES.index("source_age_ms")] = [10.0, 20.0, 30.0]
    clean[:, MODEL_FEATURE_NAMES.index("min_classification_probability")] = [0.8, 0.9, 1.0]
    bounds = learn_guardrails(clean)

    clean_scores, _ = score_guardrails(clean, bounds)
    assert clean_scores[1] == 0

    faulty = clean[:1].copy()
    faulty[0, MODEL_FEATURE_NAMES.index("source_age_ms")] = 1000.0
    faulty[0, MODEL_FEATURE_NAMES.index("min_classification_probability")] = 0.05
    scores, violations = score_guardrails(faulty, bounds)

    assert scores[0] > 0
    assert violations[0, GUARDRAIL_FEATURES.index("source_age_ms")] > 0
    assert violations[0, GUARDRAIL_FEATURES.index("min_classification_probability")] > 0


def test_can_exclude_trajectory_dependent_guardrails_from_a_decision() -> None:
    violations = np.zeros((1, len(GUARDRAIL_FEATURES)), dtype=np.float64)
    violations[0, GUARDRAIL_FEATURES.index("max_relative_object_displacement_m")] = 4.0
    violations[0, GUARDRAIL_FEATURES.index("object_count_delta")] = 2.0

    scores, selected = select_guardrail_violations(
        violations, ("object_count_delta", "source_age_ms")
    )

    assert scores.tolist() == [2.0]
    assert selected.tolist() == [[2.0, 0.0]]
