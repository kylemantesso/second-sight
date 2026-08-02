import numpy as np

from second_sight.model import (
    GUARDRAIL_FEATURES,
    MODEL_FEATURE_NAMES,
    learn_guardrails,
    score_guardrails,
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
