# Deterministic Cleaning and Resolution Policy

- **Validation** never silently changes source or drops malformed rows. Invalid parsed records have issue codes. Unreadable source files fail. Bad JSONL lines count as invalid and are visible in `validation_report.json`; their raw bytes are retained in the source snapshot.
- **Normalization** optional whitespace contraction and strip for document classification. No lowercasing, spell correction, diacritic removal, or semantic category merging. `label_aliases` only maps explicit known aliases to canonical classes. Original text and source label are retained for comparison. Whitespace normalization must be disabled for span annotation.
- **Duplicate detection** exact equality on configurable key (default cleaned text); more similar texts from TF-IDF are **not** automatically merged. When original label, source, category or resolved label differ, mark *all members* of the group for review. If completely identical, the lexicographically smallest source ID is retained; other rows are excluded with `exact_duplicate_identical_metadata`. Set `duplicate_policy: review_only` to retain duplicate candidates.
- **Resolution** default: designated independent annotators must each submit exactly one valid answer for a record and agree on the same class. A reviewer may override with a versioned, reasoned label or mark unresolved. This decision never modifies the underlying annotation rows. Unknown labels, skips, duplicates, and missing peers are not agreement.
- **Exclusions** structural invalidity excludes with a validation code. Identical duplicates may be excluded as above. Unresolved/ambiguous records are kept in `unresolved` unless the configured `exclude_unresolved: true` explicitly excludes them with the exact policy reason. Minority categories never disappear by rule alone.
- **Ledger** every parsed record gets a stable `input_row_key`, operation list (`no_change` when appropriate), and final status. Duplicate source IDs remain flagged invalid; original IDs are *not* rewritten to hide the defect.

Example **illustrative** ledger entry, not a measured outcome:

```json
{"record_id":"row-2","input_row_key":"2:row-2","operations":[{"operation":"exclude","reason":"exact_duplicate_identical_metadata"}],"status":"excluded","exclusion_reason":"exact_duplicate_identical_metadata"}
```

The final resolved exports are schema-checked, their source IDs unique, labels in ontology, and text nonempty. All row partitions are round-trip checked after JSONL writing. Annotator identifiers are withheld from the resolved/unresolved/excluded public views, while secure `normalized_annotations` retains per-rater identity for audits.
