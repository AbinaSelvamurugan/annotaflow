# Configurable Label Ontology and Schema

`configs/dataset.yaml` maps user field names into canonical fields: `record_id` (string; unique or SHA-256 derived), `text` (nonempty UTF-8 string), `existing_label` (optional, original unmodified), `source` (optional), `category` (optional). Unknown labels/categories and duplicate IDs are recorded as invalid; duplicate content is not automatically invalid. Source bytes remain unchanged.

`configs/annotation.yaml` lists `Positive`, `Negative`, `Neutral`, operational definitions, guideline version, and Label Studio result control `sentiment` targeting `text`. `needs_review` is a **review status**, not a substantive fourth classification label. `None` (no annotation), `skipped`, and `invalid` are distinct.

Example **synthetic task payload** (not a preannotation):

```json
{"data":{"source_id":"s001","text":"Example text."},"meta":{"source":"synthetic-fixture","category":"feedback","guideline_version":"sentiment-v1","dataset_version":"demo-synthetic-v1"}}
```

Example **native Label Studio-compatible annotation shape** (illustration only, *not a human observation*):

```json
{"id": 22, "data": {"source_id": "s001", "text": "Example text."}, "annotations": [{"id": 81, "completed_by": 101, "created_at": "2025-01-01T00:00:00Z", "was_cancelled": false, "result": [{"from_name": "sentiment", "to_name": "text", "type": "choices", "value": {"choices": ["Positive"]}}]}]}
```

The actual JSON may include additional task and annotation fields. The normalizer uses safe optional access and preserves the original full export; it **does not** ingest flattened `JSON_MIN`/CSV as if they contained all annotation identity fields. Only valid single-label responses matching the configured result control and ontology count toward agreement.

To extend to multi-label, ordinal scoring, entity spans or image bounding boxes, create a new `annotation.version`, interface XML, parser for the appropriate `result.type`, agreement definition, and tests. Do not treat multi-label `choices` arrays as invalid single-label observations or apply sentiment's cleaning normalization to character offsets.
