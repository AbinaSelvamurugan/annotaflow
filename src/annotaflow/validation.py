"""Record validation. Invalid rows are retained with issues, not silently removed."""
import hashlib
import json
import math
from collections import Counter

import pandas as pd

from .io import load_rows
from .schemas import CanonicalRecord
from pydantic import ValidationError


def missing(value) -> bool:
    try:
        return value is None or (isinstance(value, str) and not value.strip()) or bool(pd.isna(value))
    except (ValueError, TypeError):
        return False


def scalar(value) -> bool:
    return isinstance(value, str) or (isinstance(value, (int, float))
                                       and not isinstance(value, bool))


def stable_id(row: dict, id_field: str) -> str:
    payload = {k: v for k, v in row.items() if k not in {id_field, "__source_line"}}
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return "sha256-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def validate(path, dataset_cfg, labels: list[str], aliases: dict[str, str] | None = None):
    source_rows, malformed = load_rows(path, dataset_cfg.format, dataset_cfg.encoding)
    columns = dataset_cfg.columns.model_dump()
    required = [columns.get(k, k) for k in dataset_cfg.required]
    available = set().union(*(set(r) for r in source_rows)) if source_rows else set()
    if not source_rows and not malformed:
        raise ValueError("Empty dataset")
    absent = set(required) - available
    if absent:
        raise ValueError(f"Missing mandatory columns: {sorted(absent)}")
    aliases = aliases or {}
    id_counts = Counter()
    text_counts = Counter()
    records = []
    missing_counts = Counter()
    for index, original in enumerate(source_rows, 1):
        row = {k: v for k, v in original.items() if k != "__source_line"}
        source_line = original.get("__source_line", index + 1)
        raw_id = row.get(columns["id"])
        record_id = str(raw_id).strip() if not missing(raw_id) else ""
        if not record_id and dataset_cfg.auto_generate_ids:
            record_id = stable_id(row, columns["id"])
        text = row.get(columns["text"])
        label = row.get(columns["label"])
        source = row.get(columns["source"])
        category = row.get(columns["category"])
        issues = []
        for name, v in row.items():
            if missing(v):
                missing_counts[name] += 1
            if isinstance(v, float) and not math.isfinite(v):
                issues.append(f"non_finite:{name}")
        if not record_id:
            issues.append("missing_record_id")
        if missing(text):
            issues.append("empty_text")
        elif not isinstance(text, str):
            issues.append("invalid_text_type")
        elif len(text.strip()) < dataset_cfg.min_text_chars:
            issues.append("near_empty_text")
        if not missing(label) and (not scalar(label) or str(label) not in labels + list(aliases)):
            issues.append("unknown_label")
        if not missing(source) and dataset_cfg.allowed_sources and source not in dataset_cfg.allowed_sources:
            issues.append("unexpected_source")
        if not missing(category) and dataset_cfg.allowed_categories and category not in dataset_cfg.allowed_categories:
            issues.append("unexpected_category")
        try:
            CanonicalRecord(record_id=record_id, text=text,
                            existing_label=None if missing(label) else str(label),
                            source=None if missing(source) else str(source),
                            category=None if missing(category) else str(category))
        except ValidationError:
            if "pydantic_schema_validation" not in issues:
                issues.append("pydantic_schema_validation")
        if record_id:
            id_counts[record_id] += 1
        if isinstance(text, str) and text.strip():
            text_counts[text] += 1
        records.append({"record_id": record_id, "text": text,
                        "existing_label": None if missing(label) else str(label),
                        "source": None if missing(source) else str(source),
                        "category": None if missing(category) else str(category),
                        "original": row, "source_line": source_line, "issues": issues})
    for r in records:
        if id_counts[r["record_id"]] > 1:
            r["issues"].append("duplicate_id")
        r["valid"] = not r["issues"]
    duplicate_content = sum(n-1 for n in text_counts.values() if n > 1)
    issues = Counter(i for r in records for i in r["issues"])
    valid = sum(r["valid"] for r in records)
    recommendations = []
    if issues.get("duplicate_id"): recommendations.append("Resolve duplicate IDs before import")
    if issues.get("unknown_label"): recommendations.append("Review unknown labels or add explicit aliases")
    if malformed: recommendations.append("Fix malformed JSONL lines in source; no lines were silently repaired")
    if duplicate_content: recommendations.append("Inspect duplicate content and metadata conflicts")
    report = {"input_rows": len(source_rows) + len(malformed), "parsed_rows": len(records),
              "valid_rows": valid, "invalid_rows": len(records)-valid+len(malformed),
              "missing_values": dict(missing_counts), "duplicate_record_count": duplicate_content,
              "duplicate_id_count": sum(n-1 for n in id_counts.values() if n>1),
              "unknown_label_count": issues.get("unknown_label", 0),
              "invalid_record_count": len(records)-valid+len(malformed),
              "issue_counts": dict(issues), "malformed_lines": malformed,
              "warnings": recommendations,
              "errors": [f"{len(malformed)} malformed JSONL lines"] if malformed else [],
              "recommended_actions": recommendations}
    return records, report
