"""Regression tests for data-integrity edge cases and export integrity."""
from pathlib import Path
import copy
import shutil

from annotaflow.annotations import normalize_annotations
from annotaflow.cli import do_clean, do_validate, load_stage
from annotaflow.cleaning import clean_dataset, validate_exports
from annotaflow.io import read_json


def sandbox_repo(tmp_path, cfg, raw_contents, suffix="jsonl"):
    source = Path(__file__).resolve().parents[2]
    shutil.copytree(source / "configs", tmp_path / "configs")
    p = tmp_path / "source" / f"test.{suffix}"
    p.parent.mkdir(parents=True)
    p.write_text(raw_contents, encoding="utf-8")
    config = tmp_path / "configs" / "dataset.yaml"
    config.write_text(config.read_text().replace("data/examples/synthetic_unlabeled.csv",
                                                  f"source/test.{suffix}"))
    return load_stage(tmp_path)


def test_malformed_jsonl_gets_exclusion_ledger(tmp_path):
    cfg, run, raw, store = sandbox_repo(tmp_path, None,
        '{"record_id":"ok","text":"An adequate example"}\nBAD JSON\n')
    rows, rep = do_validate(cfg, run, raw, store)
    assert rep["invalid_rows"] == 1
    result = do_clean(cfg, run, raw, store)
    assert result["counts"] == {"unresolved": 1, "excluded": 1}
    ledger = read_json(run / "cleaning_ledger.json")
    assert any(r["exclusion_reason"] == "malformed_jsonl" for r in ledger)
    assert "BAD JSON" in (run / "excluded.jsonl").read_text()


def test_duplicate_source_id_kept_but_not_resolved(tmp_path):
    cfg, run, raw, store = sandbox_repo(tmp_path, None,
        "record_id,text\nabc,First text\nabc,Second text\n", "csv")
    do_validate(cfg, run, raw, store)
    out = do_clean(cfg, run, raw, store)
    assert out["counts"]["excluded"] == 2
    ledger = read_json(run / "cleaning_ledger.json")
    assert len({r["input_row_key"] for r in ledger}) == 2
    assert all(r["record_id"] == "abc" for r in ledger)


def test_nonfinite_serializes_tag_and_raw_copy_preserved(tmp_path):
    cfg, run, raw, store = sandbox_repo(tmp_path, None,
        '{"record_id":"x","text":"Valid words", "metric":Infinity}\n')
    input_data = raw.read_bytes()
    _, rep = do_validate(cfg, run, raw, store)
    assert rep["invalid_rows"] == 1
    assert raw.read_bytes() == input_data
    assert read_json(run / "validated_records.json")[0]["original"]["metric"] == {
        "__source_non_finite_float__": "inf"}


def test_alias_only_normalizes_known_values(cfg, synthetic_records, simulated_export):
    ex = copy.deepcopy(simulated_export)
    ex[0]["annotations"][0]["result"][0]["value"]["choices"] = ["pos"]
    entries, stats = normalize_annotations(ex, synthetic_records, cfg.annotation,
                                           aliases={"pos": "Positive"})
    assert stats["valid_annotations"] == 8
    assert entries[0]["raw_label"] == "pos"
    assert entries[0]["label"] == "Positive"


def test_decision_cannot_turn_duplicate_invalid_id_into_valid(cfg, synthetic_records):
    records = copy.deepcopy(synthetic_records[:2])
    records[1]["record_id"] = records[0]["record_id"]
    for rec in records:
        rec["valid"] = False
        rec["issues"] = ["duplicate_id"]
    dec = {records[0]["record_id"]: {"status": "resolved", "label": "Positive"}}
    rows, ledger, _, _ = clean_dataset(records, [], dec, cfg)
    assert all(r["cleaning_status"] == "excluded" for r in rows)
    assert validate_exports(rows, cfg.annotation.labels)


def test_report_metrics_not_computed_with_no_paired_annotations(tmp_path):
    cfg, run, raw, store = sandbox_repo(tmp_path, None,
        '{"record_id":"ok","text":"An example with no annotations"}\n')
    do_validate(cfg, run, raw, store)
    do_clean(cfg, run, raw, store)
    from annotaflow.reporting import quality_report
    assert quality_report(run)["agreement_status"] == "Not computed"
