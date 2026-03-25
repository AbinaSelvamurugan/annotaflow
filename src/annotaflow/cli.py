"""Executable, independently replayable AnnotaFlow stages."""
import argparse
import json
from pathlib import Path

from .agreement import evaluate_pair, agreement_by_group
from .annotations import normalize_annotations
from .cleaning import clean_dataset, validate_exports
from .config import load_config
from .io import read_json, run_context, utc_now, write_csv, write_json, write_jsonl
from .label_studio import LabelStudioAPI, label_xml, task_payload
from .profiling import profile
from .reporting import quality_report
from .review import review_queue
from .storage import Store
from .validation import validate


def load_stage(root):
    root = Path(root).resolve()
    cfg = load_config(root)
    run, raw = run_context(root, cfg)
    return cfg, run, raw, Store(run / "audit.sqlite")


def do_validate(cfg, run, raw, store=None):
    records, summary = validate(raw, cfg.dataset, cfg.annotation.labels, cfg.cleaning.label_aliases)
    write_json(run / "validated_records.json", records)
    write_json(run / "validation_report.json", summary)
    if store: store.event("validate", payload={"valid": summary["valid_rows"],
                                          "invalid": summary["invalid_rows"]})
    return records, summary


def get_records(cfg, run, raw, store=None):
    return read_json(run / "validated_records.json") if (run / "validated_records.json").exists() else do_validate(cfg, run, raw, store)[0]


def do_profile(cfg, run, raw, store=None):
    p = profile(get_records(cfg, run, raw, store), cfg.quality)
    write_json(run / "profile.json", p)
    return p


def do_prepare(cfg, run, raw, store):
    records = get_records(cfg, run, raw, store)
    tasks = [task_payload(r, cfg) for r in records if r["valid"]]
    write_json(run / "prepared_tasks.json", tasks)
    (run / "label_config.xml").write_text(label_xml(cfg.annotation), encoding="utf-8")
    store.event("prepare", payload={"tasks": len(tasks)})
    return len(tasks)


def do_normalize(cfg, run, raw, store, export_path, live_api=False):
    tasks = read_json(export_path)
    records = get_records(cfg, run, raw, store)
    entries, stats = normalize_annotations(tasks, records, cfg.annotation, cfg.cleaning.label_aliases)
    if stats["mapping_errors"]:
        write_json(run / "annotation_mapping_errors.json", stats["mapping_errors"])
        raise ValueError("Export has invalid task mapping; inspect annotation_mapping_errors.json")
    write_json(run / "normalized_annotations.json", entries)
    write_csv(run / "normalized_annotations.csv", entries)
    write_json(run / "annotation_stats.json", stats)
    write_json(run / "annotation_provenance.json", {"origin": "verified_live_api_export" if live_api else
               "user_provided_export_file", "source_path": str(export_path),
               "human_identity_independence_verified": False})
    store.event("normalize_annotations", payload=stats)
    return stats


def get_annotations(run):
    return read_json(run / "normalized_annotations.json") if (run / "normalized_annotations.json").exists() else []


def do_clean(cfg, run, raw, store, a=None, b=None):
    records = get_records(cfg, run, raw, store)
    entries = get_annotations(run)
    decisions = store.latest_decisions()
    for rid, decision in decisions.items():
        if decision["label"] is not None and decision["label"] not in cfg.annotation.labels:
            raise ValueError(f"Adjudicated label {decision['label']} no longer in ontology for {rid}")
    rows, ledger, conflicts, stats = clean_dataset(records, entries, decisions, cfg, a, b)
    validation_report = read_json(run / "validation_report.json")
    # Malformed lines are excluded input items too; don't erase them from the ledger.
    for malformed in validation_report.get("malformed_lines", []):
        line_no = malformed["source_line"]
        row_key = f"malformed-line:{line_no}"
        rows.append({"record_id": None, "input_row_key": row_key,
             "original_text": malformed["raw"], "cleaned_text": None,
             "original_label": None, "normalized_existing_label": None,
             "annotator_labels": {}, "final_label": None,
             "annotation_status": "not_annotatable", "review_status": "unresolved",
             "source": None, "category": None, "dataset_version": cfg.dataset.version,
             "guideline_version": cfg.annotation.version, "cleaning_status": "excluded",
             "exclusion_reason": "malformed_jsonl", "validation_issues": ["malformed_jsonl"],
             "source_line": line_no})
        ledger.append({"record_id": None, "input_row_key": row_key,
              "operations": [{"operation": "exclude", "reason": "malformed_jsonl",
                              "error": malformed["reason"]}],
              "status": "excluded", "exclusion_reason": "malformed_jsonl"})
    if validation_report.get("malformed_lines"):
        from collections import Counter
        stat_counts = Counter(r["cleaning_status"] for r in rows)
        stats["counts"] = dict(stat_counts)
        excluded_counts = Counter(r["exclusion_reason"] for r in rows
                                  if r["cleaning_status"] == "excluded")
        stats["excluded_by_reason"] = dict(excluded_counts)
    validate_exports(rows, cfg.annotation.labels)
    groups_to_review = set()
    if (run / "agreement.json").exists():
        agreement = read_json(run / "agreement.json")
        if str(a) == agreement.get("annotator_a") and str(b) == agreement.get("annotator_b"):
            for kind, prop in (("category", "by_category"), ("source", "by_source")):
                for group_name, measured in agreement.get(prop, {}).items():
                    if (measured["joint_count"] >= cfg.quality.min_group_pairs and
                        measured["raw_agreement"] is not None and
                        measured["raw_agreement"] < cfg.quality.review_group_agreement_below):
                        groups_to_review.add((kind, group_name))
    queue = review_queue(records, entries, decisions, a, b, conflicts,
                         groups_to_review, cfg.cleaning.label_aliases)
    # The resolved export intentionally never contains annotator identities.
    public = []
    for r in rows:
        copy = {k: v for k,v in r.items() if k != "annotator_labels"}
        copy["independent_labels_without_identity"] = sorted(r["annotator_labels"].values())
        public.append(copy)
    resolved = [r for r in public if r["cleaning_status"] == "resolved"]
    unresolved = [r for r in public if r["cleaning_status"] == "unresolved"]
    excluded = [r for r in public if r["cleaning_status"] == "excluded"]
    for name, part in (("cleaned_all", public), ("resolved", resolved),
                       ("unresolved", unresolved), ("excluded", excluded)):
        write_jsonl(run / f"{name}.jsonl", part)
        write_csv(run / f"{name}.csv", part)
    # Explicit exported-output validation, not merely in-memory validation.
    for name, expected in (("resolved", resolved), ("unresolved", unresolved), ("excluded", excluded)):
        reloaded = [json.loads(line) for line in (run / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
        if reloaded != expected:
            raise RuntimeError(f"Round-trip output validation failed: {name}")
    write_json(run / "cleaning_ledger.json", ledger)
    write_json(run / "review_queue.json", queue)
    write_json(run / "adjudication_history.json", store.decision_history())
    write_json(run / "cleaning_stats.json", stats)
    store.event("clean", payload=stats)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="annotaflow", description="Annotation QA CLI")
    ap.add_argument("--root", default=".", help="Repository root containing configs/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("validate", "profile", "prepare", "project", "import", "export",
                "normalize", "analyze", "review", "adjudicate", "clean", "report", "run-offline"):
        p = sub.add_parser(cmd)
        if cmd in ("project", "import", "export"):
            p.add_argument("--project-id", type=int)
        if cmd == "normalize": p.add_argument("--file", required=True)
        if cmd in ("analyze", "review", "clean"):
            p.add_argument("--a", help="First actual annotator user ID")
            p.add_argument("--b", help="Second actual annotator user ID")
        if cmd == "analyze":
            p.add_argument("--weights", choices=["linear", "quadratic"])
            p.add_argument("--ordinal", action="store_true", help="Explicitly declare label scale ordinal")
        if cmd == "adjudicate":
            p.add_argument("--id", required=True)
            p.add_argument("--label")
            p.add_argument("--unresolved", action="store_true")
            p.add_argument("--reviewer", required=True)
            p.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    cfg, run, raw, store = load_stage(args.root)
    cmd = args.cmd
    if cmd == "validate":
        result = do_validate(cfg, run, raw, store)[1]
    elif cmd == "profile":
        result = do_profile(cfg, run, raw, store)
    elif cmd == "prepare":
        result = {"prepared": do_prepare(cfg, run, raw, store)}
    elif cmd == "run-offline":
        do_validate(cfg, run, raw, store)
        do_profile(cfg, run, raw, store)
        do_prepare(cfg, run, raw, store)
        do_clean(cfg, run, raw, store)
        result = {"run": str(run), "report": str(run / "quality_report.md")}
        quality_report(run)
    elif cmd in ("project", "import", "export"):
        api = LabelStudioAPI()
        api.connect()
        if cmd == "project":
            project = api.ensure_project(cfg, args.project_id)
            write_json(run / "project.json", {"id": project["id"],
                "title": project.get("title"), "base_url": api.url,
                "guideline_version": cfg.annotation.version})
            store.event("project_verified", payload={"id": project["id"]})
            result = {"project_id": project["id"], "verified": True}
        else:
            pid = args.project_id or (read_json(run / "project.json")["id"] if (run / "project.json").exists() else None)
            if pid is None: raise ValueError("Set --project-id or run project first")
            api.ensure_project(cfg, pid)
            if cmd == "import":
                result = api.import_tasks(pid, get_records(cfg, run, raw, store), cfg, store)
            else:
                snapshot = run / "raw_annotation_snapshots" / (utc_now().replace(":", "-") + ".json")
                result = api.export_tasks(pid, snapshot)
                write_json(run / "raw_annotations.json", read_json(snapshot))
                do_normalize(cfg, run, raw, store, run / "raw_annotations.json", live_api=True)
                store.event("export_verified", payload=result)
    elif cmd == "normalize":
        result = do_normalize(cfg, run, raw, store, Path(args.file).resolve())
    elif cmd == "analyze":
        if not args.a or not args.b: raise ValueError("analyze requires --a and --b")
        if args.weights and not args.ordinal: raise ValueError("Weighted kappa requires --ordinal")
        path = run / "normalized_annotations.json"
        if not path.exists(): raise ValueError("Normalize a real Label Studio export first")
        records = get_records(cfg, run, raw, store)
        entries = get_annotations(run)
        result = evaluate_pair(entries, records, cfg.annotation.labels, args.a, args.b,
            args.weights, cfg.quality.ci_bootstrap_iterations)
        result["by_category"] = agreement_by_group(entries, records, cfg.annotation.labels, args.a, args.b)
        result["by_source"] = agreement_by_group(entries, records, cfg.annotation.labels, args.a, args.b, "source")
        write_json(run / "agreement.json", result)
        store.event("agreement", payload={"eligible": result["joint_count"],
                                          "excluded": result["excluded_count"]})
    elif cmd == "adjudicate":
        records = get_records(cfg, run, raw, store)
        if args.id not in {r["record_id"] for r in records}:
            raise ValueError("Unknown source record ID")
        if args.unresolved == bool(args.label):
            raise ValueError("Choose exactly one of --label or --unresolved")
        if args.label and args.label not in cfg.annotation.labels:
            raise ValueError("Adjudicated label not in ontology")
        store.decide(args.id, None if args.unresolved else args.label,
                     args.reason, args.reviewer, cfg.annotation.version)
        result = {"record_id": args.id, "review_status": "unresolved" if args.unresolved else "resolved",
                  "revision": store.latest_decisions()[args.id]["revision"]}
    elif cmd == "clean":
        if bool(args.a) != bool(args.b):
            raise ValueError("Specify both --a and --b, or neither to leave pairs unresolved")
        result = do_clean(cfg, run, raw, store, args.a, args.b)
    elif cmd == "review":
        if bool(args.a) != bool(args.b): raise ValueError("Specify both annotators or neither")
        entries = get_annotations(run)
        # 'clean' also populates review flags for low-agreement groups and duplicate conflicts.
        if args.a and args.b:
            do_clean(cfg, run, raw, store, args.a, args.b)
            result = read_json(run / "review_queue.json")
        else:
            result = review_queue(get_records(cfg, run, raw, store), entries,
                                  store.latest_decisions(), args.a, args.b,
                                  aliases=cfg.cleaning.label_aliases)
        write_json(run / "review_queue.json", result)
        result = {"review_queue_rows": len(result), "file": str(run / "review_queue.json")}
    elif cmd == "report":
        result = quality_report(run)
    print(json.dumps({"run_directory": str(run), "result": result}, indent=2, default=str))


if __name__ == "__main__":
    main()
