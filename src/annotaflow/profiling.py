"""Profiling and candidate-only near-duplicate review."""
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def profile(records: list[dict], cfg):
    lengths = [len(r["text"]) for r in records if isinstance(r["text"], str)]
    texts = [r for r in records if isinstance(r["text"], str) and r["text"].strip()]
    counts = Counter(r["text"] for r in texts)
    categories = Counter(str(r["category"]) for r in records)
    sources = Counter(str(r["source"]) for r in records)
    labels = Counter(str(r["existing_label"]) for r in records if r["existing_label"])
    anomalies = [r["record_id"] for r in records if isinstance(r["text"], str) and
                 ("\ufffd" in r["text"] or "\x00" in r["text"])]
    candidates = []
    if cfg.near_duplicates and 2 <= len(texts) <= cfg.near_duplicate_max_rows:
        # Character-level TF-IDF review aid; no automatic deduplication from this result.
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        try:
            sim = cosine_similarity(vec.fit_transform([r["text"] for r in texts]))
            for i in range(len(texts)):
                for j in range(i+1, len(texts)):
                    if texts[i]["text"] != texts[j]["text"] and sim[i,j] >= cfg.near_duplicate_threshold:
                        candidates.append({"record_a": texts[i]["record_id"],
                                           "record_b": texts[j]["record_id"],
                                           "similarity": round(float(sim[i,j]), 4),
                                           "status": "candidate_not_confirmed"})
        except ValueError:  # e.g. no lexical tokens
            pass
    numeric = np.asarray(lengths)
    nonzero = [v for v in labels.values() if v > 0]
    return {"rows": len(records), "source_columns": sorted(set().union(*[
        set(r["original"]) for r in records]) if records else []),
        "valid_rows": sum(r["valid"] for r in records),
        "label_distribution": dict(labels), "source_distribution": dict(sources),
        "category_distribution": dict(categories),
        "text_length": {"min": int(numeric.min()) if numeric.size else None,
                        "median": float(np.median(numeric)) if numeric.size else None,
                        "p95": float(np.percentile(numeric, 95)) if numeric.size else None,
                        "max": int(numeric.max()) if numeric.size else None},
        "empty_text_count": sum(not isinstance(r["text"], str) or not r["text"].strip() for r in records),
        "exact_duplicate_groups": sum(v>1 for v in counts.values()),
        "exact_duplicate_extra_rows": sum(v-1 for v in counts.values() if v>1),
        "encoding_anomaly_record_ids": anomalies,
        "existing_annotation_completeness": round(sum(bool(r["existing_label"]) for r in records)/len(records),4) if records else None,
        "class_imbalance_max_min": max(nonzero)/min(nonzero) if len(nonzero)>1 else None,
        "near_duplicate_candidates": candidates}
