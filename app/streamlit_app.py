"""Streamlit read/write QA console. Run: streamlit run app/streamlit_app.py"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from annotaflow.cli import load_stage
from annotaflow.io import read_json
from annotaflow.label_studio import LabelStudioAPI

ROOT = Path(__file__).resolve().parents[1]
CFG, RUN, RAW, STORE = load_stage(ROOT)


def file(name, default=None):
    path = RUN / name
    return read_json(path) if path.exists() else default


st.set_page_config(page_title="AnnotaFlow — Quality Console", page_icon="📋", layout="wide")
st.title("AnnotaFlow — Annotation Quality Console")
st.caption(f"Run: {RUN.name} | Dataset {CFG.dataset.version} | Guidelines {CFG.annotation.version}")
st.info("Local administrative dashboard: may show sensitive source text and internal annotation IDs. "
        "Do not expose without access controls. Blank metrics are not yet computed, not zero.")

tabs = st.tabs(["Dataset Overview", "Annotation Management", "Agreement Analysis",
                "Disagreement Review", "Cleaning & Adjudication", "Quality Report"])
val = file("validation_report.json", {})
prof = file("profile.json", {})
ann = file("annotation_stats.json", {})
agr = file("agreement.json")
clean = file("cleaning_stats.json", {})
queue = file("review_queue.json", [])
ledger = file("cleaning_ledger.json", [])

with tabs[0]:
    st.subheader("Dataset overview")
    x, y, z, w = st.columns(4)
    x.metric("Input rows", val.get("input_rows", "Not measured"))
    y.metric("Valid rows", val.get("valid_rows", "Not measured"))
    z.metric("Invalid rows", val.get("invalid_rows", "Not measured"))
    w.metric("Duplicate content", val.get("duplicate_record_count", "Not measured"))
    st.write("Missing values", val.get("missing_values", {}))
    if prof.get("label_distribution"):
        st.bar_chart(pd.Series(prof["label_distribution"], name="Count"))
    else:
        st.caption("No existing source labels. This is not an annotation agreement result.")
    if prof:
        st.json({k: v for k,v in prof.items() if k not in {"near_duplicate_candidates"}})
        with st.expander("Near-duplicate review candidates (not automatic exclusions)"):
            st.dataframe(prof.get("near_duplicate_candidates", []))

with tabs[1]:
    st.subheader("Annotation management")
    project = file("project.json")
    st.write("Configured project", project or "Not connected to a Label Studio project")
    st.write("Last local export statistics", ann or "No annotation export synchronized")
    st.write("Last imported tasks", file("prepared_tasks.json", []) and
             len(file("prepared_tasks.json", [])) or "No prepared tasks")
    if st.button("Check live Label Studio status"):
        try:
            api = LabelStudioAPI()
            result = api.connect()
            st.success("Authenticated and connected")
            if project:
                tasks = api.list_tasks(project["id"])
                st.write("Remote task count", len(tasks))
                st.write("Tasks with at least one annotation",
                         sum(bool(t.get("annotations")) for t in tasks))
                st.write("Submitted annotation total", sum(len(t.get("annotations") or []) for t in tasks))
        except Exception as exc:
            st.error(f"Live status check failed: {type(exc).__name__}: {exc}")

with tabs[2]:
    st.subheader("Inter-annotator agreement")
    if agr is None:
        st.warning("Run `analyze --a ID --b ID` after normalizing an export to compute agreement.")
    else:
        a, b, c = st.columns(3)
        a.metric("Eligible task pairs", agr["joint_count"])
        b.metric("Raw agreement", f"{agr['raw_agreement']:.1%}" if agr["raw_agreement"] is not None else "Undefined")
        c.metric("Cohen's κ", f"{agr['cohen_kappa']:.3f}" if agr["cohen_kappa"] is not None else "Undefined")
        st.write("Excluded pair reasons", agr["exclusion_reasons"])
        st.write("Warnings", agr["warnings"])
        st.dataframe(pd.DataFrame(agr["confusion_matrix"], index=agr["labels"],
                                  columns=agr["labels"]))
        st.write("Per class", agr["per_class"])
        with st.expander("Per-category pairwise metrics"):
            st.json(agr.get("by_category", {}))

with tabs[3]:
    st.subheader("Disagreement / review queue")
    if not queue:
        st.write("No review queue exported yet, or none flagged.")
    else:
        options = ["Any"] + sorted({reason for r in queue for reason in r["reasons"]})
        selected_reason = st.selectbox("Flag reason", options)
        selected_source = st.selectbox("Source", ["Any"] + sorted({str(r["source"]) for r in queue}))
        selected_category = st.selectbox("Category", ["Any"] + sorted({str(r["category"]) for r in queue}))
        all_labels = sorted({e["label"] for r in queue for e in r["annotation_history"] if e["label"]})
        selected_label = st.selectbox("Annotation label", ["Any"] + all_labels)
        all_annotators = sorted({e["annotator_id"] for r in queue for e in r["annotation_history"]
                                 if e["annotator_id"]})
        selected_annotator = st.selectbox("Annotator ID (restricted)", ["Any"] + all_annotators)
        filtered = [r for r in queue if (selected_reason == "Any" or selected_reason in r["reasons"])
                    and (selected_source == "Any" or str(r["source"]) == selected_source)
                    and (selected_category == "Any" or str(r["category"]) == selected_category)
                    and (selected_label == "Any" or any(e["label"] == selected_label for e in r["annotation_history"]))
                    and (selected_annotator == "Any" or any(e["annotator_id"] == selected_annotator
                                                    for e in r["annotation_history"]))]
        st.dataframe(pd.DataFrame([{k:v for k,v in r.items() if k!="annotation_history"}
                                   for r in filtered]), use_container_width=True)
        if filtered:
            rid = st.selectbox("Inspect source ID", [r["record_id"] for r in filtered])
            row = next(r for r in filtered if r["record_id"] == rid)
            st.write("Original content", row["text"])
            st.write("Annotation history (internal use only)")
            st.json(row["annotation_history"])
            project = file("project.json")
            if project and row["task_id"]:
                base = os.environ.get("LABEL_STUDIO_URL", project.get("base_url", ""))
                st.markdown(f"[Open Label Studio task]({base}/projects/{project['id']}/data?task={row['task_id']})")

with tabs[4]:
    st.subheader("Cleaning and adjudication")
    st.write("Active rules", CFG.cleaning.model_dump())
    st.write("Cleaning outcomes", clean if clean else "Not yet generated")
    st.dataframe(pd.DataFrame(ledger), use_container_width=True)
    st.markdown("### Record a new adjudication decision")
    if not queue:
        st.caption("Generate a review queue first. Adjudication always stores a new revision.")
    else:
        valid_ids = sorted({r["record_id"] for r in queue})
        with st.form("decision"):
            rid = st.selectbox("Source ID", valid_ids)
            choice = st.selectbox("Decision", ["Unresolved"] + CFG.annotation.labels)
            reviewer = st.text_input("Reviewer identifier")
            rationale = st.text_area("Rationale (required)")
            submitted = st.form_submit_button("Save adjudication revision")
        if submitted:
            if not reviewer.strip() or not rationale.strip():
                st.error("Reviewer identifier and rationale are required")
            else:
                STORE.decide(rid, None if choice == "Unresolved" else choice, rationale,
                             reviewer, CFG.annotation.version)
                st.success("Adjudication revision recorded. Re-run clean and report to refresh derived exports.")
    with st.expander("Adjudication history"):
        st.dataframe(pd.DataFrame(STORE.decision_history()))

with tabs[5]:
    st.subheader("Final quality report")
    report = RUN / "quality_report.md"
    if report.exists():
        content = report.read_text(encoding="utf-8")
        st.markdown(content)
        st.download_button("Download quality report", content,
                           file_name="quality_report.md", mime="text/markdown")
        json_path = RUN / "quality_report.json"
        if json_path.exists():
            st.download_button("Download JSON findings", json_path.read_bytes(),
                               file_name="quality_report.json", mime="application/json")
    else:
        st.write("No computed report yet. Run `python -m annotaflow report`.")
