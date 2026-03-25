"""Stable, explainable cleaning policy with per-record ledger and exclusion reasons."""
import re
from collections import defaultdict, Counter

from .review import annotation_groups, resolution


def clean_dataset(records, entries, decisions, cfg, annotator_a=None, annotator_b=None):
    groups = annotation_groups(entries)
    rows, ledger = [], []
    for row_no, r in enumerate(records, 1):
        row_key = f"{row_no}:{r['record_id']}"
        label, policy, status = resolution(r["record_id"], groups, decisions,
                                           annotator_a, annotator_b)
        previous = r["text"]
        text = (re.sub(r"\s+", " ", previous).strip() if cfg.cleaning.normalize_whitespace
                and isinstance(previous, str) else previous)
        rec = {"record_id": r["record_id"], "input_row_key": row_key, "original_text": previous,
            "cleaned_text": text, "original_label": r["existing_label"],
            "normalized_existing_label": cfg.cleaning.label_aliases.get(r["existing_label"], r["existing_label"]),
            "annotator_labels": {a["annotator_id"]: a["label"] for a in groups.get(r["record_id"], [])
                                  if a["annotator_id"] and a["status"]=="valid"
                                  and not a["duplicate_annotator_submission"]},
            "final_label": label, "annotation_status": policy,
            "review_status": status, "source": r["source"], "category": r["category"],
            "dataset_version": cfg.dataset.version, "guideline_version": cfg.annotation.version,
            "cleaning_status": "resolved" if label is not None else "unresolved",
            "exclusion_reason": None, "validation_issues": r["issues"],
            "source_line": r["source_line"]}
        actions = []
        if previous != text:
            actions.append({"operation": "whitespace_normalization", "reason": "configured_whitespace_rule",
                            "prior_value": previous, "new_value": text})
        if not r["valid"] and cfg.cleaning.exclude_invalid:
            rec["cleaning_status"] = "excluded"
            rec["exclusion_reason"] = "validation:" + ",".join(r["issues"])
            actions.append({"operation": "exclude", "reason": rec["exclusion_reason"]})
        rows.append(rec)
        ledger.append({"record_id": r["record_id"], "input_row_key": row_key, "operations": actions,
                       "status": rec["cleaning_status"], "exclusion_reason": rec["exclusion_reason"]})
    by_key = defaultdict(list)
    for r in rows:
        if r["cleaning_status"] != "excluded":
            key = tuple(r["cleaned_text"] if col == "text" else r[col]
                        for col in cfg.cleaning.duplicate_key)
            by_key[key].append(r)
    conflicts = set()
    ledger_by_id = {r["input_row_key"]: r for r in ledger}
    for group in by_key.values():
        if len(group) < 2:
            continue
        # Metadata conflict (including differing source labels) never implicitly merges.
        signature = lambda r: (r["source"], r["category"], r["normalized_existing_label"], r["final_label"])
        if len({signature(r) for r in group}) > 1:
            for r in group:
                conflicts.add(r["record_id"])
                if r["cleaning_status"] != "excluded":
                    r["cleaning_status"] = "unresolved"
                    r["review_status"] = "duplicate_conflict"
                ledger_by_id[r["input_row_key"]]["operations"].append({
                    "operation": "hold_for_review", "reason": "duplicate_metadata_or_label_conflict"})
        elif cfg.cleaning.duplicate_policy == "exclude_identical":
            for r in sorted(group, key=lambda x: x["record_id"])[1:]:
                r["cleaning_status"] = "excluded"
                r["exclusion_reason"] = "exact_duplicate_identical_metadata"
                ledger_by_id[r["input_row_key"]]["operations"].append({"operation": "exclude",
                    "reason": "exact_duplicate_identical_metadata"})
        else:
            for r in group:
                ledger_by_id[r["input_row_key"]]["operations"].append({"operation": "duplicate_review_aid",
                    "reason": "duplicate_policy_review_only"})
    if cfg.cleaning.exclude_unresolved:
        for r in rows:
            if r["cleaning_status"] == "unresolved":
                r["cleaning_status"] = "excluded"
                r["exclusion_reason"] = "unresolved_label_or_duplicate_conflict"
                ledger_by_id[r["input_row_key"]]["operations"].append({"operation": "exclude",
                    "reason": r["exclusion_reason"]})
    for r in rows:
        ledger_by_id[r["input_row_key"]]["status"] = r["cleaning_status"]
        ledger_by_id[r["input_row_key"]]["exclusion_reason"] = r["exclusion_reason"]
        if not ledger_by_id[r["input_row_key"]]["operations"]:
            ledger_by_id[r["input_row_key"]]["operations"] = [{"operation": "no_change",
                                                         "reason": "no_cleaning_rule_triggered"}]
    counts = Counter(r["cleaning_status"] for r in rows)
    eligible_revisions = [r for r in rows if r["original_label"] is not None and
                          r["cleaning_status"] == "resolved"]
    revised = sum(r["normalized_existing_label"] != r["final_label"] for r in eligible_revisions)
    return rows, ledger, sorted(conflicts), {"counts": dict(counts),
        "final_label_revision_rate": revised / len(eligible_revisions) if eligible_revisions else None,
        "final_label_revision_count": revised,
        "existing_label_comparison_count": len(eligible_revisions),
        "resolved_category_distribution": dict(Counter(str(r["category"]) for r in rows
                    if r["cleaning_status"] == "resolved")),
        "original_label_distribution": dict(Counter(str(r["normalized_existing_label"])
                    for r in rows if r["normalized_existing_label"] is not None)),
        "missing_final_classes": [label for label in cfg.annotation.labels if not any(
                    r["cleaning_status"] == "resolved" and r["final_label"] == label for r in rows)],
        "resolved_label_distribution": dict(Counter(r["final_label"] for r in rows
                    if r["cleaning_status"]=="resolved" and r["final_label"] is not None)),
        "excluded_by_reason": dict(Counter(r["exclusion_reason"] for r in rows
                    if r["cleaning_status"]=="excluded")),
        "adjudicated": sum(r["annotation_status"]=="adjudicated" for r in rows),
        "agreed": sum(r["annotation_status"]=="agreed" for r in rows),
        "duplicate_conflicts": len(conflicts)}


def validate_exports(rows, labels):
    if len({r["input_row_key"] for r in rows}) != len(rows):
        raise ValueError("Input row keys must be unique")
    resolved_ids = [r["record_id"] for r in rows if r["cleaning_status"] == "resolved"]
    if len(set(resolved_ids)) != len(resolved_ids):
        raise ValueError("Resolved record IDs must be unique")
    for r in rows:
        if r["cleaning_status"] == "resolved" and (r["final_label"] not in labels or
                                                      not isinstance(r["cleaned_text"], str) or
                                                      not r["cleaned_text"].strip()):
            raise ValueError(f"Invalid resolved output for {r['record_id']}")
        if r["cleaning_status"] == "excluded" and not r["exclusion_reason"]:
            raise ValueError("Excluded row is missing reason")
    return True
