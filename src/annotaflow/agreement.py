"""Paired-task agreement statistics, never positional or majority-vote matching."""
from collections import Counter, defaultdict
import math
import warnings

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix


def _by_annotator(entries, annotator):
    groups = defaultdict(list)
    for e in entries:
        if e.get("annotator_id") == str(annotator):
            groups[e["record_id"]].append(e)
    return groups


def evaluate_pair(entries, records, labels, annotator_a, annotator_b, weights=None,
                  bootstrap_iterations=0):
    if str(annotator_a) == str(annotator_b):
        raise ValueError("Agreement requires two DISTINCT annotators")
    if weights not in (None, "linear", "quadratic"):
        raise ValueError("Weights must be None, linear, or quadratic")
    a = _by_annotator(entries, annotator_a)
    b = _by_annotator(entries, annotator_b)
    valid_records = {r["record_id"]: r for r in records if r["valid"]}
    xs, ys, paired_ids, excluded = [], [], [], []
    reasons = Counter()
    for rid in sorted(valid_records):
        ea, eb = a.get(rid, []), b.get(rid, [])
        reason = None
        if len(ea) > 1 or len(eb) > 1:
            reason = "duplicate_annotation"
        elif not ea or not eb:
            reason = "missing_pair"
        elif ea[0]["status"] != "valid" or eb[0]["status"] != "valid":
            reason = "skipped_or_invalid"
        elif ea[0]["label"] not in labels or eb[0]["label"] not in labels:
            reason = "unknown_label"
        if reason:
            reasons[reason] += 1
            excluded.append({"record_id": rid, "reason": reason})
            continue
        xs.append(ea[0]["label"])
        ys.append(eb[0]["label"])
        paired_ids.append(rid)
    n = len(xs)
    cm = confusion_matrix(xs, ys, labels=labels).tolist() if n else [[0]*len(labels) for _ in labels]
    raw = sum(x == y for x, y in zip(xs, ys))/n if n else None
    ka = None
    expected = None
    warning_list = []
    if n:
        pa = Counter(xs)
        pb = Counter(ys)
        expected = sum(pa[l]*pb[l] for l in labels)/(n*n)
        if math.isclose(expected, 1.0):
            warning_list.append("Cohen's kappa undefined: expected agreement is 1.0")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                k = cohen_kappa_score(xs, ys, labels=labels, weights=weights)
            if math.isfinite(k):
                ka = float(k)
            else:
                warning_list.append("Cohen's kappa undefined (numeric degeneracy)")
        if min([pa[l] + pb[l] for l in labels]) == 0:
            warning_list.append("At least one class is absent; per-class results may be undefined")
    else:
        pa, pb = Counter(), Counter()
        warning_list.append("No eligible independently annotated pairs")
    per_class = {}
    for label in labels:
        total_involving = sum(x == label or y == label for x,y in zip(xs,ys))
        agreements = sum(x == label and y == label for x,y in zip(xs,ys))
        per_class[label] = {"both_selected": agreements, "at_least_one_selected": total_involving,
                            "disagreements": total_involving-agreements,
                            "agreement_when_mentioned": agreements/total_involving if total_involving else None}
    disagreement_records = [{"record_id": rid, "annotator_a_label": x, "annotator_b_label": y}
                            for rid,x,y in zip(paired_ids,xs,ys) if x != y]
    ci = None
    if bootstrap_iterations and n > 1:
        rng = np.random.default_rng(2026)
        samples = []
        for _ in range(bootstrap_iterations):
            ix = rng.integers(0, n, size=n)
            samples.append(np.mean([xs[i] == ys[i] for i in ix]))
        ci = [float(z) for z in np.quantile(samples, [0.025, 0.975])]
    return {"annotator_a": str(annotator_a), "annotator_b": str(annotator_b),
            "weighting": weights or "nominal_unweighted", "joint_count": n,
            "eligible_record_count": len(valid_records), "excluded_count": len(excluded),
            "excluded_pct": len(excluded)/len(valid_records)*100 if valid_records else None,
            "exclusion_reasons": dict(reasons), "excluded_records": excluded,
            "raw_agreement": raw, "cohen_kappa": ka,
            "expected_agreement": expected, "labels": labels,
            "confusion_matrix": cm, "annotator_a_distribution": dict(pa),
            "annotator_b_distribution": dict(pb), "per_class": per_class,
            "disagreement_count": len(disagreement_records),
            "disagreement_rate": len(disagreement_records)/n if n else None,
            "disagreement_records": disagreement_records,
            "raw_agreement_bootstrap_95pct": ci,
            "warnings": warning_list + ["Agreement measures consistency, not correctness; "
                        "inspect prevalence, individual categories and disagreements."]}


def evaluate_all_pairs(entries, records, labels, weights=None, bootstrap_iterations=0):
    from itertools import combinations
    annotators = sorted({e["annotator_id"] for e in entries if e["annotator_id"]})
    return {f"{a}__{b}": evaluate_pair(entries, records, labels, a, b,
            weights, bootstrap_iterations) for a,b in combinations(annotators, 2)}


def agreement_by_group(entries, records, labels, a, b, field="category"):
    groups = sorted({r.get(field) for r in records if r["valid"]}, key=str)
    return {str(group): evaluate_pair(entries, [r for r in records if r.get(field) == group],
            labels, a, b) for group in groups}
