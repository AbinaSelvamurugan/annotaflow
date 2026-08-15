"""Offline E2E with explicitly SIMULATED annotation exports; no empirical score claim."""
import shutil
from pathlib import Path
from annotaflow.cli import main, load_stage
from annotaflow.io import read_json
from annotaflow.reporting import quality_report


def test_offline_pipeline_and_simulated_export(tmp_path, simulated_export):
    src = Path(__file__).resolve().parents[2]
    (tmp_path / "data" / "examples").mkdir(parents=True)
    shutil.copytree(src / "configs", tmp_path / "configs")
    shutil.copy(src / "data" / "examples" / "synthetic_unlabeled.csv",
                tmp_path / "data" / "examples" / "synthetic_unlabeled.csv")
    main(["--root", str(tmp_path), "run-offline"])
    cfg, run, raw, store = load_stage(tmp_path)
    original_bytes = raw.read_bytes()
    validation = read_json(run / "validation_report.json")
    assert validation["valid_rows"] == 6
    assert len(read_json(run / "prepared_tasks.json")) == 6
    assert not (run / "agreement.json").exists()
    assert read_json(run / "quality_report.json")["agreement_status"] == "Not computed"
    # End-to-end software test: simulated annotations are not human evidence.
    main(["--root", str(tmp_path), "adjudicate", "--id", "s001", "--label", "Positive",
          "--reviewer", "test-only", "--reason", "SIMULATED TEST DECISION"])
    main(["--root", str(tmp_path), "clean"])
    assert read_json(run / "cleaning_stats.json")["counts"]["resolved"] == 1
    assert raw.read_bytes() == original_bytes
    assert len((run / "adjudication_history.json").read_text()) > 10
    report = quality_report(run)
    assert report["agreement_status"] == "Not computed"
    assert (run / "resolved.csv").exists()
    assert (run / "resolved.jsonl").exists()

