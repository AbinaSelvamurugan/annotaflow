# Project report outline

**Title:** AnnotaFlow — A Reproducible Data Annotation and Quality Assurance Pipeline

1. **Introduction:** motivating label quality, bias, provenance, business impact and scientific reproducibility; scope text classification with extensibility boundaries.
2. **Related work:** annotation platform design, manual guidelines, inter-annotator agreement, ambiguity, data cleaning, research ethics, prevalence paradox.
3. **Requirements and design:** functional/nonfunctional requirements, versioned ontology, traceability, REST integration, independent rating design, permissions, architectural flowchart, issue/decision state diagrams.
4. **Methodology:** description/source/license of *user-chosen real dataset*; schema validation; controlled dual-annotation subset and recruitment; guideline calibration; kappa assumptions; review and adjudication; deterministic cleaning rules.
5. **Implementation:** module overview, sample data and metadata schemas, Label Studio XML, snapshots, idempotent imports, SQLite tables, CLI and dashboard, security limitations.
6. **Evaluation:** actual input counts and class proportions; annotated task coverage; exclusion breakdown; annotation provenance; empirical raw agreement + confusion matrix + kappa **only if human results were obtained**; per-class/category disagreement analysis; unresolved and exclusion counts; reproducibility test (hashes/ledger).
7. **Results and interpretation:** tables/figures generated from `quality_report.json` and annotation history recorded by human annotators; separate synthetic software testing numbers from human study results; do not present test fixture scores as findings.
8. **Limitations and ethical considerations:** no proof of correctness from kappa; prevalence, sample size, language, privacy, workforce consent, role control, downstream model bias, lack of external validation.
9. **Conclusion and future extensions:** blind adjudication, optional multi-rater alpha, difficult-case sampling, role-based UI, partial asynchronous API retries, span/image task support, secure deployments.
10. **Appendices:** frozen configs/guidelines, reproducible commands, pytest evidence, data dictionary, architecture diagram, annotated cleaning-ledger excerpts with PII removed.
