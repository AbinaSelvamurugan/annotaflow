# Troubleshooting

- **Missing configured dataset:** update `configs/dataset.yaml:path`, relative to repository root, or specify an absolute local file path. No external download is required.
- **`UnicodeDecodeError`:** supply the *actual* encoding in `dataset.yaml` after verifying provenance; invalid bytes are never silently replaced.
- **CSV malformed / JSONL invalid:** check `validation_report.json` malformed line numbers. CSV decoding/parsing is strict; repair upstream, preserving the raw snapshot.
- **API 401 with PAT:** set `LABEL_STUDIO_TOKEN_TYPE=pat`, use a PAT refresh token and check expiry/revocation. For legacy tokens specify `legacy` instead.
- **API 403 or incomplete task view:** confirm that the user has project manager/owner permissions; annotator-scoped task reads can hide peers' results, invalidating coverage and agreement.
- **Cannot import because source ID already exists:** the source text, metadata or guideline version differ. Use a separate versioned run/project, or explicitly inspect the remote record; never silently duplicate or overwrite.
- **Project config mismatch:** do not modify an active labeling project behind annotators' backs; create a versioned project.
- **Snapshot never finishes / wrong count:** check Label Studio background worker, storage, filters, permissions and export conversion availability. No export success is claimed before completion and remote task inventory validation.
- **Kappa `null`:** no eligible pairs or denominator zero. Check `exclusion_reasons`, marginal prevalence, rater IDs and label names. A pair with skipped or invalid choices is not a negative class.
- **`ruff`/`streamlit` module absent:** the optional dev/dashboard dependencies were not installed. Use `pip install -e '.[dev,dashboard]'` in a network-enabled environment.
- **Should I expose the dashboard?** Not directly. It is an internal local console with sensitive audit identifiers and no authentication layer.
