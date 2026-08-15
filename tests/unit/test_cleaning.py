import copy
from annotaflow.annotations import normalize_annotations
from annotaflow.cleaning import clean_dataset, validate_exports
from annotaflow.review import review_queue
from annotaflow.storage import Store
import pytest


def test_agreed_vs_unresolved_and_ledger(cfg, synthetic_records, simulated_export):
    entries, _ = normalize_annotations(simulated_export, synthetic_records, cfg.annotation)
    rows, ledger, conflicts, stats = clean_dataset(synthetic_records, entries, {}, cfg, "101", "202")
    assert stats["counts"] == {"resolved": 2, "unresolved": 2}
    assert len(ledger) == len(rows) == 4
    assert all(l["operations"] for l in ledger)
    assert rows[0]["final_label"] == "Positive"
    assert rows[1]["final_label"] is None
    assert all(r["original_text"] == f"Text example {i+1}" for i,r in enumerate(rows))
    assert validate_exports(rows, cfg.annotation.labels)
    queue = review_queue(synthetic_records, entries, {}, "101", "202")
    assert {r["record_id"] for r in queue} >= {"s2", "s4"}


def test_review_conflict_dup_metadata(cfg, synthetic_records):
    recs = copy.deepcopy(synthetic_records[:2])
    recs[1]["text"] = recs[0]["text"]
    recs[1]["source"] = "other"
    rows, ledger, conflicts, _ = clean_dataset(recs, [], {}, cfg)
    assert set(conflicts) == {"s1", "s2"}
    assert all(row["review_status"] == "duplicate_conflict" for row in rows)


def test_identical_duplicates_can_exclude(cfg, synthetic_records):
    recs = copy.deepcopy(synthetic_records[:2])
    recs[1]["text"] = recs[0]["text"]
    rows, ledger, conflicts, _ = clean_dataset(recs, [], {}, cfg)
    assert not conflicts
    assert rows[1]["exclusion_reason"] == "exact_duplicate_identical_metadata"


def test_adjudication_revision_history(tmp_path):
    store = Store(tmp_path / "a.sqlite")
    store.decide("r1", "Positive", "evidence", "reviewer", "v1")
    store.decide("r1", None, "new guideline unclear", "reviewer2", "v2")
    history = store.decision_history()
    assert len(history) == 2
    assert store.latest_decisions()["r1"]["status"] == "unresolved"
    assert history[0]["label"] == "Positive"


def test_adjudication_overrides_without_mutating_annotations(cfg, synthetic_records, simulated_export):
    entries, _ = normalize_annotations(simulated_export, synthetic_records, cfg.annotation)
    original = copy.deepcopy(entries)
    decisions = {"s2": {"label": "Negative", "status": "resolved"}}
    rows, _, _, _ = clean_dataset(synthetic_records, entries, decisions, cfg, "101", "202")
    assert rows[1]["final_label"] == "Negative"
    assert rows[1]["annotation_status"] == "adjudicated"
    assert entries == original


def test_invalid_export_fails(cfg, synthetic_records):
    recs = copy.deepcopy(synthetic_records)
    recs[0]["valid"] = False
    recs[0]["issues"] = ["empty_text"]
    rows, _, _, _ = clean_dataset(recs, [], {}, cfg)
    assert rows[0]["cleaning_status"] == "excluded"
    assert "empty_text" in rows[0]["exclusion_reason"]
    assert validate_exports(rows, cfg.annotation.labels)
    rows[0]["exclusion_reason"] = None
    with pytest.raises(ValueError): validate_exports(rows, cfg.annotation.labels)
