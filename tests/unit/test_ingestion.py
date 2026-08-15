import json
import pytest

from annotaflow.io import load_rows
from annotaflow.validation import validate


def test_csv_and_null_detection(tmp_path, cfg):
    p = tmp_path / "input.csv"
    p.write_text("record_id,text,existing_label,source,category\na,Hello,,synthetic,feedback\n"
                 "b,,INVALID,synthetic,feedback\n", encoding="utf-8")
    records, report = validate(p, cfg.dataset, cfg.annotation.labels)
    assert report["valid_rows"] == 1
    assert report["invalid_rows"] == 1
    assert report["unknown_label_count"] == 1
    assert "empty_text" in records[1]["issues"]
    assert records[0]["original"]["text"] == "Hello"


def test_duplicate_ids_all_flagged(tmp_path, cfg):
    p = tmp_path / "data.csv"
    p.write_text("record_id,text\nabc,Hello one\nabc,Hello two\n")
    recs, rep = validate(p, cfg.dataset, cfg.annotation.labels)
    assert rep["duplicate_id_count"] == 1
    assert all("duplicate_id" in r["issues"] for r in recs)


def test_content_duplicate_is_candidate_not_invalid(tmp_path, cfg):
    p = tmp_path / "data.csv"
    p.write_text("record_id,text\na,Hello\nb,Hello\n")
    recs, rep = validate(p, cfg.dataset, cfg.annotation.labels)
    assert rep["duplicate_record_count"] == 1
    assert rep["valid_rows"] == 2


def test_generated_ids_stable_and_collision_flagged(tmp_path, cfg):
    p = tmp_path / "rows.jsonl"
    row = '{"text":"Identical words","source":"synthetic"}'
    p.write_text(row + "\n" + row + "\n")
    r1, rep = validate(p, cfg.dataset, cfg.annotation.labels)
    r2, _ = validate(p, cfg.dataset, cfg.annotation.labels)
    assert r1[0]["record_id"] == r2[0]["record_id"]
    assert rep["duplicate_id_count"] == 1


def test_malformed_jsonl_counted(tmp_path, cfg):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"text":"Valid text"}\nnot-json\n')
    records, report = validate(p, cfg.dataset, cfg.annotation.labels)
    assert len(records) == 1
    assert report["input_rows"] == 2
    assert report["invalid_rows"] == 1
    assert report["malformed_lines"][0]["source_line"] == 2


def test_invalid_utf8(tmp_path, cfg):
    p = tmp_path / "rows.csv"
    p.write_bytes(b"record_id,text\na,Hi \xff\n")
    with pytest.raises(UnicodeDecodeError):
        validate(p, cfg.dataset, cfg.annotation.labels)


def test_unsupported_format(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("something")
    with pytest.raises(ValueError, match="Unsupported"):
        load_rows(p)


def test_missing_column(tmp_path, cfg):
    p = tmp_path / "input.csv"
    p.write_text("record_id,other\na,b\n")
    with pytest.raises(ValueError, match="Missing mandatory"):
        validate(p, cfg.dataset, cfg.annotation.labels)


def test_infinite_numeric_jsonl(tmp_path, cfg):
    p = tmp_path / "inf.jsonl"
    # Python's JSON decoder handles Infinity; validator must explicitly flag it.
    p.write_text('{"record_id":"z","text":"Valid text","metric":Infinity}\n')
    recs, report = validate(p, cfg.dataset, cfg.annotation.labels)
    assert "non_finite:metric" in recs[0]["issues"]
    assert report["invalid_rows"] == 1


def test_unexpected_category(tmp_path, cfg):
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps({"text": "Valid example text", "category": "unexpected"}))
    recs, _ = validate(p, cfg.dataset, cfg.annotation.labels)
    assert "unexpected_category" in recs[0]["issues"]
