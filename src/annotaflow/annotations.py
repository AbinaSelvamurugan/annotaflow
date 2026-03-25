"""Lossless task/annotation identity normalization for native Label Studio JSON exports."""
from collections import Counter


def normalize_annotations(tasks, records, annotation_cfg, aliases=None):
    aliases = aliases or {}
    source = {r["record_id"]: r for r in records if r["valid"]}
    seen_ids = set()
    entries = []
    mismatches = []
    task_to_id = {}
    missing_guidelines = 0
    for task in tasks:
        tid = task.get("id")
        data = task.get("data") or {}
        rid = data.get("source_id")
        if tid is None or rid not in source or tid in task_to_id or rid in seen_ids:
            mismatches.append({"task_id": tid, "record_id": rid, "reason": "missing_or_duplicate_mapping"})
            continue
        original = source[rid]
        if data.get("text") != original["text"]:
            mismatches.append({"task_id": tid, "record_id": rid, "reason": "source_text_mismatch"})
            continue
        guideline = (task.get("meta") or {}).get("guideline_version")
        if not guideline:
            missing_guidelines += 1
        if guideline and guideline != annotation_cfg.version:
            mismatches.append({"task_id": tid, "record_id": rid, "reason": "guideline_version_mismatch"})
            continue
        seen_ids.add(rid)
        task_to_id[tid] = rid
        annotations = task.get("annotations") or []
        if not annotations:
            annotations = [None]
        for ann in annotations:
            skipped = bool(ann and ann.get("was_cancelled"))
            results = (ann.get("result") or []) if ann else []
            values = []
            for result in results:
                if (result.get("from_name") == annotation_cfg.result_from_name and
                    result.get("to_name") == annotation_cfg.result_to_name and
                    result.get("type") == "choices"):
                    values.extend((result.get("value") or {}).get("choices") or [])
            candidate = values[0] if len(values) == 1 else None
            label = aliases.get(candidate, candidate)
            # A missing annotation is distinct from a submitted invalid/empty response.
            status = ("missing" if ann is None else "skipped" if skipped else
                      "valid" if len(values) == 1 and label in annotation_cfg.labels else "invalid")
            annotator = ann.get("completed_by") if ann else None
            if isinstance(annotator, dict):
                annotator = annotator.get("id")
            entries.append({"record_id": rid, "task_id": tid,
                "annotation_id": ann.get("id") if ann else None,
                "annotator_id": str(annotator) if annotator is not None else None,
                "label": label if status == "valid" else None,
                "raw_label": candidate, "raw_choices": values, "status": status,
                "created_at": (ann.get("created_at") or ann.get("updated_at")) if ann else None,
                "guideline_version": guideline,
                "category": original["category"], "source": original["source"],
                "was_cancelled": skipped})
    # A full export must retain unimported or otherwise absent source IDs as missing.
    for rid, original in source.items():
        if rid not in seen_ids:
            entries.append({"record_id": rid, "task_id": None, "annotation_id": None,
                "annotator_id": None, "label": None, "raw_label": None, "raw_choices": [],
                "status": "missing", "created_at": None,
                "guideline_version": None,
                "category": original["category"], "source": original["source"],
                "was_cancelled": False})
    ids = Counter((r["record_id"], r["annotator_id"]) for r in entries
                  if r["annotator_id"] is not None)
    for r in entries:
        r["duplicate_annotator_submission"] = (r["annotator_id"] is not None and
            ids[(r["record_id"], r["annotator_id"])] > 1)
    by_id = {}
    for e in entries:
        by_id.setdefault(e["record_id"], []).append(e)
    submitted = [e for e in entries if e["annotation_id"] is not None]
    complete_task_ids = [rid for rid, group in by_id.items() if len({e["annotator_id"]
        for e in group if e["status"] == "valid" and not e["duplicate_annotator_submission"]
        and e["annotator_id"]}) >= 2]
    stats = {"guideline_metadata_missing_tasks": missing_guidelines,
             "tasks_in_export": len(tasks), "mapped_tasks": len(seen_ids),
             "completed_two_rater_tasks": len(complete_task_ids),
             "two_rater_completion_rate": len(complete_task_ids)/len(source) if source else None,
             "submitted_annotations": len(submitted),
             "skipped_task_rate": sum(any(e["status"] == "skipped" for e in by_id.get(rid, []))
                  for rid in source)/len(source) if source else None,
             "invalid_label_rate": sum(e["status"] == "invalid" for e in submitted)/len(submitted)
                  if submitted else None,
             "duplicate_annotation_rate": sum(e["duplicate_annotator_submission"]
                  for e in submitted)/len(submitted) if submitted else None,
             "valid_annotations": sum(r["status"]=="valid" for r in entries),
             "skipped_annotations": sum(r["status"]=="skipped" for r in entries),
             "invalid_annotations": sum(r["status"]=="invalid" for r in entries),
             "missing_tasks": sum(r["status"]=="missing" for r in entries),
             "duplicate_annotation_rows": sum(r["duplicate_annotator_submission"] for r in entries),
             "mapping_errors": mismatches,
             "annotation_coverage_rate": sum(any(e["status"] == "valid" for e in by_id.get(rid, []))
                                               for rid in source)/len(source) if source else None}
    return entries, stats
