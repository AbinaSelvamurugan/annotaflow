"""Source loading, deterministic run paths, safe file output."""
import hashlib
import math
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_json(data):
    """Tag non-finite source numbers; original bytes remain unchanged in raw snapshot."""
    if isinstance(data, float) and not math.isfinite(data):
        return {"__source_non_finite_float__": str(data)}
    if isinstance(data, dict):
        return {str(k): safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [safe_json(v) for v in data]
    return data


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_json(data), indent=2, ensure_ascii=False, sort_keys=True,
                               default=str, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in data:
            f.write(json.dumps(safe_json(obj), ensure_ascii=False, default=str, allow_nan=False) + "\n")


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=columns)
    for col in df.columns:
        df[col] = df[col].map(lambda v: json.dumps(safe_json(v), ensure_ascii=False,
                              sort_keys=True) if isinstance(v, (dict, list)) else v)
    df.to_csv(path, index=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_context(root, cfg):
    root = Path(root).resolve()
    src = Path(cfg.dataset.path)
    src = src if src.is_absolute() else root / src
    if not src.is_file():
        raise FileNotFoundError(src)
    source_hash = digest(src.read_bytes())
    config_payload = cfg.model_dump(mode="json")
    cfg_hash = digest(json.dumps(config_payload, sort_keys=True).encode("utf-8"))
    # Code fingerprint guards against confusing different implementation versions.
    code_bytes = b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in
                          sorted(Path(__file__).parent.glob("*.py")))
    code_hash = digest(code_bytes)
    run_id = f"{cfg.dataset.version}-{digest((source_hash + cfg_hash + code_hash).encode())[:12]}"
    run = root / "results" / run_id
    run.mkdir(parents=True, exist_ok=True)
    raw = run / "raw" / src.name
    if not raw.exists():
        raw.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, raw)
    if digest(raw.read_bytes()) != source_hash:
        raise RuntimeError("Raw snapshot hash mismatch; never overwrite a raw snapshot")
    manifest = run / "manifest.json"
    if not manifest.exists():
        write_json(manifest, {"run_id": run_id, "source_path": str(src),
                              "raw_snapshot": str(raw.relative_to(run)),
                              "source_sha256": source_hash, "config_sha256": cfg_hash,
                              "source_code_sha256": code_hash, "pipeline_version": "0.1.0",
                              "dataset_version": cfg.dataset.version,
                              "guideline_version": cfg.annotation.version,
                              "created_at": utc_now(), "config": config_payload})
    return run, raw


def load_rows(path: Path, fmt="auto", encoding="utf-8") -> tuple[list[dict], list[dict]]:
    """Return original row dicts and malformed-line records without silently skipping them."""
    fmt = path.suffix.lower().lstrip(".") if fmt == "auto" else fmt.lower()
    if fmt == "csv":
        # strict decode first; read_csv may otherwise quietly replace malformed bytes
        path.read_text(encoding=encoding, errors="strict")
        df = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False,
                         na_filter=False, on_bad_lines="error")
        return df.to_dict("records"), []
    if fmt == "jsonl":
        lines = path.read_text(encoding=encoding, errors="strict").splitlines()
        rows, malformed = [], []
        for line_no, line in enumerate(lines, 1):
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("JSONL row must be an object")
                rows.append({**obj, "__source_line": line_no})
            except (json.JSONDecodeError, ValueError) as e:
                malformed.append({"source_line": line_no, "reason": str(e), "raw": line})
        return rows, malformed
    if fmt == "parquet":
        return pd.read_parquet(path).to_dict("records"), []
    raise ValueError(f"Unsupported file format: {fmt}")
