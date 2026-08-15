from annotaflow.agreement import evaluate_pair, evaluate_all_pairs, agreement_by_group
from annotaflow.annotations import normalize_annotations
import copy
import pytest


def pair(cfg, synthetic_records, simulated_export, **kw):
    entries, _ = normalize_annotations(simulated_export, synthetic_records, cfg.annotation)
    return evaluate_pair(entries, synthetic_records, cfg.annotation.labels, "101", "202", **kw)


def test_manually_checked_kappa_and_matrix(cfg, synthetic_records, simulated_export):
    r = pair(cfg, synthetic_records, simulated_export)
    assert r["joint_count"] == 4
    assert r["raw_agreement"] == 0.5
    assert r["cohen_kappa"] == pytest.approx(0.0)
    assert r["disagreement_count"] == 2
    assert r["confusion_matrix"] == [[1, 1, 0], [1, 1, 0], [0, 0, 0]]
    assert r["labels"] == ["Positive", "Negative", "Neutral"]


def test_order_invariance(cfg, synthetic_records, simulated_export):
    expected = pair(cfg, synthetic_records, simulated_export)
    actual = pair(cfg, synthetic_records[::-1], simulated_export[::-1])
    assert expected["cohen_kappa"] == actual["cohen_kappa"]
    assert expected["confusion_matrix"] == actual["confusion_matrix"]


def test_exclusions_and_missing_pairs(cfg, synthetic_records, simulated_export):
    changed = copy.deepcopy(simulated_export)
    changed[0]["annotations"] = changed[0]["annotations"][:1]
    changed[1]["annotations"][1]["was_cancelled"] = True
    r = pair(cfg, synthetic_records, changed)
    assert r["joint_count"] == 2
    assert r["excluded_count"] == 2
    assert r["exclusion_reasons"] == {"missing_pair": 1, "skipped_or_invalid": 1}


def test_undefined_when_every_label_constant(cfg, synthetic_records, simulated_export):
    changed = copy.deepcopy(simulated_export)
    for t in changed:
        for ann in t["annotations"]:
            ann["result"][0]["value"]["choices"] = ["Positive"]
    r = pair(cfg, synthetic_records, changed)
    assert r["raw_agreement"] == 1.0
    assert r["cohen_kappa"] is None
    assert "undefined" in r["warnings"][0]


def test_explicit_weighting_only(cfg, synthetic_records, simulated_export):
    with pytest.raises(ValueError):
        pair(cfg, synthetic_records, simulated_export, weights="exponential")
    weighted = pair(cfg, synthetic_records, simulated_export, weights="linear")
    assert weighted["weighting"] == "linear"


def test_multiple_raters_pairwise(cfg, synthetic_records, simulated_export):
    entries, _ = normalize_annotations(simulated_export, synthetic_records, cfg.annotation)
    more = [dict(e, annotator_id="303", annotation_id=1000 + i)
            for i,e in enumerate(entries) if e["annotator_id"] == "101"]
    results = evaluate_all_pairs(entries + more, synthetic_records, cfg.annotation.labels)
    assert len(results) == 3
    assert results["101__303"]["raw_agreement"] == 1
    by_group = agreement_by_group(entries, synthetic_records, cfg.annotation.labels, "101", "202")
    assert by_group["feedback"]["joint_count"] == 4


def test_no_pair_yields_no_score(cfg, synthetic_records):
    r = evaluate_pair([], synthetic_records, ["Positive", "Negative"], "101", "202")
    assert r["joint_count"] == 0
    assert r["raw_agreement"] is None and r["cohen_kappa"] is None
