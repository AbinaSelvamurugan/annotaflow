import copy
from annotaflow.annotations import normalize_annotations


def test_preserves_alignment_and_provenance(cfg, synthetic_records, simulated_export):
    entries, stats = normalize_annotations(simulated_export[::-1], synthetic_records, cfg.annotation)
    assert stats["valid_annotations"] == 8
    assert stats["mapped_tasks"] == 4
    assert {e["record_id"] for e in entries} == {r["record_id"] for r in synthetic_records}
    assert {e["annotator_id"] for e in entries} == {"101", "202"}
    assert all(e["annotation_id"] is not None for e in entries)


def test_missing_skipped_invalid_distinct(cfg, synthetic_records, simulated_export):
    export = copy.deepcopy(simulated_export)
    export[0]["annotations"] = []
    export[1]["annotations"][0]["was_cancelled"] = True
    export[2]["annotations"][1]["result"][0]["value"]["choices"] = ["Unknown"]
    entries, stats = normalize_annotations(export, synthetic_records, cfg.annotation)
    assert stats["missing_tasks"] == 1
    assert stats["skipped_annotations"] == 1
    assert stats["invalid_annotations"] == 1
    assert not any(e["status"] == "valid" and e["record_id"] == "s1" for e in entries)


def test_duplicate_annotator_submission(cfg, synthetic_records, simulated_export):
    export = copy.deepcopy(simulated_export)
    export[0]["annotations"].append(copy.deepcopy(export[0]["annotations"][0]))
    export[0]["annotations"][-1]["id"] = 999
    entries, stats = normalize_annotations(export, synthetic_records, cfg.annotation)
    assert stats["duplicate_annotation_rows"] == 2
    assert sum(e["duplicate_annotator_submission"] for e in entries) == 2


def test_export_source_tampering_is_rejected(cfg, synthetic_records, simulated_export):
    export = copy.deepcopy(simulated_export)
    export[0]["data"]["text"] = "changed"
    _, stats = normalize_annotations(export, synthetic_records, cfg.annotation)
    assert stats["mapping_errors"][0]["reason"] == "source_text_mismatch"


def test_missing_entire_task_retained(cfg, synthetic_records, simulated_export):
    entries, stats = normalize_annotations(simulated_export[:-1], synthetic_records, cfg.annotation)
    assert stats["missing_tasks"] == 1
    assert any(e["record_id"] == "s4" and e["status"] == "missing" for e in entries)
