# Methodology, Design Decisions, Reproducibility

1. **Acquire** consented/licensed user data; track origin and restrictions outside the bundle. Source is copied by bytes with a SHA-256 fingerprint. `manifest.json` includes frozen YAML configuration and dataset/guideline versions.
2. **Validate** record schema and optional canonical field mappings. Reject malformed lines from preparation, but *count and retain their raw text* in the validation report. Issue codes identify duplicate IDs, empty/nonstring/near-empty text, nonfinite numbers, unknown labels and inconsistent allowed categorical values. All parsed records, including invalid ones, remain in `validated_records.json`.
3. **Profile** source distributions, lengths, exact duplicates, minimum class frequency, unusual characters, optional char-ngram TF-IDF near-duplicate candidates. Similarity is a review aid only; cosine similarity is not semantic equivalence.
4. **Prepare** stable `data.source_id` and `data.text` per record. Existing labels are not in the annotation payload. Guidelines/project version and source/category go in task `meta`.
5. **Import and export** with response-checked, authenticated HTTP API. Validate the Label Studio XML with the server, configure two completions per task, verify existing IDs/content, poll snapshot completion, and compare the resulting export's task IDs with the remote inventory. Snapshot exports preserve uncompleted work *if the deployment's filter behavior returns it*; a mismatch raises an error.
6. **Normalize** each native JSON annotation into a row. `task_id` is not `source_id`; both are maintained. Ignore unknown/invalid labels for kappa but **retain them** in the annotation archive and review queue.
7. **Evaluate** two specified annotator IDs after exact source-ID alignment. Exclude missing/duplicate/skipped/invalid pairs with breakdowns. Report prevalence and confusion matrix next to kappa. Optional bootstrap uses a fixed random seed and estimates raw-agreement uncertainty, not correctness.
8. **Review and adjudicate** the original text, both independent annotations and versioned guideline definitions. Append new decisions to SQLite instead of replacing original annotations; explicit unresolved decisions override any prior auto-resolution.
9. **Clean** with configurable, replayable transformations. Structural invalidity leads to documented exclusion, and exact content duplicates are only excluded when metadata and labels match. Conflicts trigger review. No balancing or arbitrary majority vote. `resolved` requires agreement by both designated raters or a human reviewer decision.
10. **Export and report** class coverage and unresolved/exclusion rates with all file subsets round-trip validated against JSONL before asserting success. Public files omit annotator identifiers. Retain raw data and restricted annotation archives separately.

## Constraints / bias risks

Source categories can correlate with annotator behavior; compare by category/source only where there are jointly eligible pairs. Small groups may give undefined kappa. A high agreement can still be consistently wrong. Missingness is often non-random. This pipeline reports these issues but cannot correct them without research design and independent ground truth.

Deterministic transformations exclude timestamps: `cleaning_ledger.json`, `cleaned_all.jsonl` and task-preparation payloads are stable for identical raw/config/annotation/decision inputs. Event, import and adjudication timestamps are intentionally not deterministic but persist for audit. The source file remains immutable.
