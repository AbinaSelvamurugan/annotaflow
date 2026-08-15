"""Synthetic software fixtures; no fixture represents a real human's work."""
from pathlib import Path
import pytest

from annotaflow.config import load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    return load_config(ROOT)


@pytest.fixture
def synthetic_records():
    return [{"record_id": f"s{i}", "text": f"Text example {i}",
             "existing_label": None, "source": "synthetic", "category": "feedback",
             "original": {"text": f"Text example {i}"}, "valid": True,
             "issues": [], "source_line": i} for i in range(1, 5)]


@pytest.fixture
def simulated_export(synthetic_records):
    """Simulated JSON resembling Label Studio, never real human annotation evidence."""
    label_a = ["Positive", "Positive", "Negative", "Negative"]
    label_b = ["Positive", "Negative", "Negative", "Positive"]
    tasks = []
    for i, rec in enumerate(synthetic_records):
        annotations = []
        for rater, label in [(101, label_a[i]), (202, label_b[i])]:
            annotations.append({"id": i*2 + (rater==202) + 1, "completed_by": rater,
                "created_at": "2025-01-01T00:00:00Z", "was_cancelled": False,
                "result": [{"from_name": "sentiment", "to_name": "text", "type": "choices",
                            "value": {"choices": [label]}}]})
        tasks.append({"id": i+100, "data": {"source_id": rec["record_id"],
            "text": rec["text"]}, "meta": {"guideline_version": "sentiment-v1"},
            "annotations": annotations})
    return tasks
