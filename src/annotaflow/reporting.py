"""Reports always derive their figures from run artifacts; no example scores."""
from pathlib import Path
from html import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .io import read_json, write_json


def draw_counts(counts, path: Path, title: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    if counts:
        keys = list(counts)
        ax.bar(keys, list(counts.values()))
        ax.tick_params(axis="x", rotation=25)
    else:
        ax.text(0.5, 0.5, "No empirical values available", ha="center", va="center")
        ax.set_xticks([])
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def quality_report(run: Path):
    validation = read_json(run / "validation_report.json") if (run / "validation_report.json").exists() else {}
    profile = read_json(run / "profile.json") if (run / "profile.json").exists() else {}
    annotation = read_json(run / "annotation_stats.json") if (run / "annotation_stats.json").exists() else {}
    agreement = read_json(run / "agreement.json") if (run / "agreement.json").exists() else None
    provenance = read_json(run / "annotation_provenance.json") if (run / "annotation_provenance.json").exists() else None
    cleaning = read_json(run / "cleaning_stats.json") if (run / "cleaning_stats.json").exists() else {}
    manifest = read_json(run / "manifest.json")
    if profile:
        draw_counts(profile.get("label_distribution", {}), run / "plots" / "source_labels.png",
                    "Original label distribution")
    if cleaning:
        draw_counts(cleaning.get("resolved_label_distribution", {}),
                    run / "plots" / "final_labels.png", "Final resolved label distribution")
    status = ("Computed" if agreement and agreement.get("joint_count", 0) else "Not computed")
    report = {"run_id": manifest["run_id"], "dataset_version": manifest["dataset_version"],
              "guideline_version": manifest["guideline_version"],
              "source_sha256": manifest["source_sha256"],
              "validation": validation, "profile": profile, "annotation": annotation,
              "annotation_provenance": provenance,
              "agreement_status": status, "agreement": agreement, "cleaning": cleaning,
              "limitations": ["Annotations and provenance require independent human verification.",
                  "Pairwise kappa is not label correctness or a universal quality threshold.",
                  "No ground-truth accuracy claim is made.",
                  "Near duplicates are candidates only; unresolved examples are not training labels."]}
    write_json(run / "quality_report.json", report)
    lines = ["# AnnotaFlow — Dataset Quality Report", "",
       f"Run: `{manifest['run_id']}` | Dataset version: `{manifest['dataset_version']}` | Guidelines: `{manifest['guideline_version']}`",
       f"Source SHA-256: `{manifest['source_sha256']}`", "",
       "## Input and validation", "",
       f"- Total input rows: {validation.get('input_rows', 'not measured')}",
       f"- Valid rows: {validation.get('valid_rows', 'not measured')}",
       f"- Invalid rows: {validation.get('invalid_rows', 'not measured')}",
       f"- Duplicate-content extra rows: {validation.get('duplicate_record_count', 'not measured')}",
       f"- Duplicate ID occurrences: {validation.get('duplicate_id_count', 'not measured')}",
       f"- Unknown label rows: {validation.get('unknown_label_count', 'not measured')}",
       "", "## Annotation and agreement", "",
       f"- Evaluation status: **{status}**",
       f"- Valid normalized annotations: {annotation.get('valid_annotations', 'not available')}",
       f"- Skipped: {annotation.get('skipped_annotations', 'not available')}",
       f"- Invalid: {annotation.get('invalid_annotations', 'not available')}",
       f"- Coverage: {annotation.get('annotation_coverage_rate', 'not available')}"]
    if agreement:
        lines += [f"- Comparison: {agreement['annotator_a']} versus {agreement['annotator_b']}",
            f"- Eligible pairs: {agreement['joint_count']}",
            f"- Excluded pairs: {agreement['excluded_count']}",
            f"- Raw agreement: {agreement['raw_agreement'] if agreement['raw_agreement'] is not None else 'undefined'}",
            f"- Cohen's kappa: {agreement['cohen_kappa'] if agreement['cohen_kappa'] is not None else 'undefined'}",
            f"- Disagreements: {agreement['disagreement_count']}",
            f"- Kappa warnings: {'; '.join(agreement['warnings'])}"]
    else:
        lines.append("- Cohen's kappa: **Not computed — requires two independent human annotators**")
    lines += ["", "## Cleaning and outcome", "",
              f"- Status counts: {cleaning.get('counts', 'not measured')}",
              f"- Resolved class coverage: {cleaning.get('resolved_label_distribution', 'not measured')}",
              f"- Exclusions by reason: {cleaning.get('excluded_by_reason', 'not measured')}",
              f"- Adjudicated decisions applied: {cleaning.get('adjudicated', 'not measured')}",
              f"- Final label revision count/rate: {cleaning.get('final_label_revision_count', 'not measured')} / {cleaning.get('final_label_revision_rate', 'not measured')}",
              f"- Final classes with no resolved records: {cleaning.get('missing_final_classes', 'not measured')}",
              f"- Resolved category distribution: {cleaning.get('resolved_category_distribution', 'not measured')}",
              "", "## Interpretation and limitations", "",
              *[f"- {msg}" for msg in report["limitations"]],
              "", "Run artifacts: `cleaning_ledger.json`, `review_queue.json`, `adjudication_history.json`."]
    (run / "quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    html_file = run / "quality_report.html"
    def cell(v):
        return escape("Not computed" if v is None else str(v))
    def section(title, data):
        return (f"<section><h2>{escape(title)}</h2><table><tbody>" +
                "".join(f"<tr><th>{escape(str(k).replace('_', ' ').title())}</th>"
                        f"<td>{cell(v)}</td></tr>" for k,v in data.items()) +
                "</tbody></table></section>")
    stat = {"Input rows": validation.get("input_rows"),
            "Valid rows": validation.get("valid_rows"),
            "Invalid rows": validation.get("invalid_rows"),
            "Duplicate-content rows": validation.get("duplicate_record_count"),
            "Annotation quality": status,
            "Eligible annotation pairs": agreement.get("joint_count") if agreement else None,
            "Raw agreement": agreement.get("raw_agreement") if agreement else None,
            "Cohen's kappa": agreement.get("cohen_kappa") if agreement else None,
            "Resolved records": cleaning.get("counts", {}).get("resolved", 0),
            "Unresolved records": cleaning.get("counts", {}).get("unresolved", 0),
            "Excluded records": cleaning.get("counts", {}).get("excluded", 0)}
    body = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>AnnotaFlow | Quality report</title><style>",
        "body{font-family:system-ui,sans-serif;margin:3rem auto;max-width:960px;"
        "padding:0 1.25rem;color:#182638;background:#f7f9fb}"
        "header{border-bottom:4px solid #315a80;padding-bottom:1rem}"
        "h1{font-size:2rem;letter-spacing:-.02em}h2{color:#244b71}"
        "section{background:white;border:1px solid #e2e9ef;border-radius:12px;"
        "padding:1rem 1.4rem;margin:1.4rem 0}"
        "table{width:100%;border-collapse:collapse;table-layout:fixed}"
        "td,th{border-bottom:1px solid #edf0f4;padding:.6rem;text-align:left;"
        "vertical-align:top;overflow-wrap:anywhere}th{width:38%;color:#4a5b69}"
        "figure{margin:1rem 0}figure img{max-width:100%}small{color:#697887}"
        "</style></head><body>",
        "<header><h1>AnnotaFlow — Quality & Lineage Report</h1>",
        f"<p>Dataset {cell(manifest['dataset_version'])} · Guideline {cell(manifest['guideline_version'])}</p>",
        f"<small>Run: {cell(manifest['run_id'])} · SHA-256: {cell(manifest['source_sha256'])}</small></header>",
        section("Measured summary", stat),
        section("Missing source values", validation.get("missing_values", {})),
        section("Original class distribution", profile.get("label_distribution", {})),
        section("Resolved class distribution", cleaning.get("resolved_label_distribution", {})),
        section("Reasons for exclusions", cleaning.get("excluded_by_reason", {})),
        section("Validation issues", validation.get("issue_counts", {})),
        "<section><h2>Class coverage and limitations</h2>",
        f"<p>Classes without resolved training examples: {cell(cleaning.get('missing_final_classes', []))}</p>",
        "<ul>" + "".join(f"<li>{escape(msg)}</li>" for msg in report["limitations"]) + "</ul></section>",
        "<section><h2>Distribution figures</h2>",
        "<figure><img src='plots/source_labels.png' alt='Source labels'><figcaption>Existing label distribution (if present)</figcaption></figure>"
        "<figure><img src='plots/final_labels.png' alt='Final resolved labels'><figcaption>Resolved class distribution</figcaption></figure></section>",
        "<footer><p><small>Generated from the saved run artifacts for this run.</small></p></footer>",
        "</body></html>"]
    html_file.write_text("\n".join(body), encoding="utf-8")
    return report
