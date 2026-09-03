# Annotation Guidelines — Sentiment-v1

**Guideline version:** `sentiment-v1`; **task:** single-label document-level sentiment of the author's *expressed evaluation* about the content/service/product described. **Required orientation:** read the full text; determine one dominant evaluative tone, or skip where evidence is insufficient. Never guess private intent. **Do not see other annotators' responses** before submitting. Existing data labels are intentionally hidden.

| Label | Operational inclusion | Exclusion criteria | Positive example for this label | Negative example (not this label) |
|---|---|---|---|---|
| **Positive** | Explicit approval, satisfaction, praise, or favorable outcomes | Factual success updates with no evaluative language; clearly negative assessments | “The instructions were clear and very helpful.” | “The manual contains five chapters.” |
| **Negative** | Explicit criticism, dissatisfaction, failures described as adverse, or unfavorable evaluations | Neutral trouble-ticket metadata lacking a negative or positive evaluation; praise | “The application keeps crashing; it is frustrating.” | “The server update is scheduled at noon.” |
| **Neutral** | Factual/descriptive statement or genuinely balanced mixed feedback without a dominant evaluative polarity | A clearly dominant positive/negative evaluation | “The meeting starts at 10 AM.” | “The meeting was extremely useful.” |

These examples are **synthetic guideline examples**, not actual completed labeling outcomes.

## Decision order

1. Read the entire item; identify whether it expresses a clear evaluation rather than assuming “complaint” from a particular topic alone.
2. Choose **Positive** if approval dominates; choose **Negative** if disapproval dominates. If there are both, select the dominant sentiment *only* if reasonably clear from the text.
3. If no evaluative dominant sentiment exists, choose **Neutral**.
4. If the item is unreadable, refers to unavailable context, includes contradictory fragments with no interpretable meaning, or is in an unknown language you cannot reliably interpret, **skip** it and request review. A skipped task is not Negative or Neutral.
5. Where two categories seem applicable, reread the dominant evaluation; if still ambiguous, skip and flag for guideline clarification. Record questions separately for calibration/adjudication.

**Quality checks:** use version `sentiment-v1` for all raters; overlap the same hidden-label subset across two distinct people; do not copy a colleague's answers; refrain from inferring author intent beyond text. Review disagreement concentrations and adjust criteria with a *new* guideline version. An adjudicator may mark a record unresolved instead of forcing a label. At least two independent valid labels or explicit adjudication are needed to emit a resolved training label.

**Scope:** Nominal categories; no ordinal weighting. This file supports document-level classification, not named entity recognition or span annotation. A new task type needs a different Label Studio control tag, data mapping, normalization strategy and tests.
