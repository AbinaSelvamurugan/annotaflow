"""Review queue and transparent final-label eligibility policy."""
from collections import defaultdict


def annotation_groups(entries):
    groups = defaultdict(list)
    for e in entries:
        groups[e["record_id"]].append(e)
    return groups


def resolution(record_id, groups, decisions, a, b):
    dec = decisions.get(record_id)
    if dec:
        if dec["status"] == "resolved":
            return dec["label"], "adjudicated", "resolved"
        return None, "adjudicated_unresolved", "unresolved"
    ann = groups.get(record_id, [])
    arows = [e for e in ann if e["annotator_id"] == str(a)] if a is not None else []
    brows = [e for e in ann if e["annotator_id"] == str(b)] if b is not None else []
    if (a != b and a is not None and b is not None and len(arows) == len(brows) == 1 and
        arows[0]["status"] == brows[0]["status"] == "valid" and
        arows[0]["label"] == brows[0]["label"]):
        return arows[0]["label"], "agreed", "resolved"
    return None, "insufficient_or_conflicting", "unresolved"


def review_queue(records, entries, decisions=None, annotator_a=None, annotator_b=None,
                 duplicate_conflicts=None, low_groups=None, aliases=None):
    decisions = decisions or {}
    groups = annotation_groups(entries)
    result = []
    duplicate_conflicts = set(duplicate_conflicts or [])
    low_groups = set(low_groups or [])
    aliases = aliases or {}
    for row_no, r in enumerate(records, 1):
        rid = r["record_id"]
        ann = groups.get(rid, [])
        reasons = []
        if not r["valid"]:
            reasons.extend(r["issues"])
        valid = [a for a in ann if a["status"]=="valid"]
        annotator_ids = [a["annotator_id"] for a in ann if a["annotator_id"]]
        if len(set(annotator_ids)) < 2:
            reasons.append("missing_independent_pair")
        if len(annotator_ids) != len(set(annotator_ids)):
            reasons.append("duplicate_annotation")
        if any(a["status"] in ("invalid", "skipped") for a in ann):
            reasons.append("invalid_or_skipped")
        if len({a["label"] for a in valid}) > 1:
            reasons.append("label_disagreement")
        if r["existing_label"] is not None and valid and any(
            a["label"] != aliases.get(r["existing_label"], r["existing_label"]) for a in valid):
            reasons.append("existing_label_conflict")
        if rid in duplicate_conflicts:
            reasons.append("duplicate_metadata_or_label_conflict")
        if ("category", str(r["category"])) in low_groups or ("source", str(r["source"])) in low_groups:
            reasons.append("low_group_agreement_review_aid")
        _, _, status = resolution(rid, groups, decisions, annotator_a, annotator_b)
        if status != "resolved":
            reasons.append("unresolved")
        if reasons:
            result.append({"record_id": rid, "input_row_key": f"{row_no}:{rid}", "task_id": next(
                (a["task_id"] for a in ann if a["task_id"] is not None), None),
                "text": r["text"], "source": r["source"], "category": r["category"],
                "existing_label": r["existing_label"], "reasons": sorted(set(reasons)),
                "annotation_history": ann, "review_status": status,
                "latest_decision": decisions.get(rid)})
    return result
