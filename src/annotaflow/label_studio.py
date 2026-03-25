"""Documented Label Studio REST API integration with real response verification.

Supports PAT refresh->Bearer and legacy Token. No fake task IDs or success responses.
"""
import hashlib
import html
import json
import os
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from .io import write_json


class LabelStudioError(RuntimeError):
    pass


def instruction_html(annotation_cfg):
    definitions = "".join(f"<li><strong>{html.escape(label)}</strong>: "
                          f"{html.escape(annotation_cfg.label_descriptions[label])}</li>"
                          for label in annotation_cfg.labels)
    return (f"<h3>Guidelines {html.escape(annotation_cfg.version)}</h3>"
            "<p>Read the full text and choose exactly one dominant sentiment. "
            "Skip ambiguous or unreadable examples; do not infer a negative class from a skip. "
            "Do not consult another annotator's submitted labels.</p>"
            f"<ul>{definitions}</ul>")


def label_xml(annotation_cfg):
    choices = "\n".join(f'<Choice value="{html.escape(l, quote=True)}"/>' for l in annotation_cfg.labels)
    result = (f'<View><Header value="{html.escape(annotation_cfg.project_title, quote=True)}"/>'
              f'<Text name="{html.escape(annotation_cfg.result_to_name, quote=True)}" value="$text"/>'
              f'<Choices name="{html.escape(annotation_cfg.result_from_name, quote=True)}"'
              f' toName="{html.escape(annotation_cfg.result_to_name, quote=True)}" choice="single" showInLine="false">{choices}</Choices></View>')
    ET.fromstring(result)
    return result


def task_payload(record, cfg):
    if not record["valid"]:
        raise ValueError(f"Invalid record {record['record_id']} cannot be imported")
    return {"data": {"text": record["text"], "source_id": record["record_id"]},
            "meta": {"source": record["source"], "category": record["category"],
                     "guideline_version": cfg.annotation.version,
                     "dataset_version": cfg.dataset.version}}


def payload_hash(task):
    return hashlib.sha256(json.dumps(task, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class LabelStudioAPI:
    def __init__(self, url=None, key=None, token_type=None, session=None, timeout=30):
        self.url = (url or os.environ.get("LABEL_STUDIO_URL", "")).rstrip("/")
        self.key = key or os.environ.get("LABEL_STUDIO_API_KEY", "")
        self.token_type = (token_type or os.environ.get("LABEL_STUDIO_TOKEN_TYPE", "pat")).lower()
        if not self.url.startswith(("http://", "https://")) or not self.key:
            raise ValueError("Set LABEL_STUDIO_URL and LABEL_STUDIO_API_KEY")
        if self.token_type not in ("pat", "legacy"):
            raise ValueError("LABEL_STUDIO_TOKEN_TYPE must be pat or legacy")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.access = None

    def _headers(self):
        if self.token_type == "legacy":
            return {"Authorization": f"Token {self.key}"}
        if self.access is None:
            r = self.session.post(self.url + "/api/token/refresh",
                                  json={"refresh": self.key}, timeout=self.timeout)
            if not r.ok:
                raise LabelStudioError(f"PAT refresh failed: HTTP {r.status_code}")
            self.access = r.json().get("access")
            if not self.access:
                raise LabelStudioError("PAT refresh response lacks access token")
        return {"Authorization": f"Bearer {self.access}"}

    def request(self, method, endpoint, **kwargs):
        if not endpoint.startswith("/api/"):
            raise ValueError("Only documented API endpoints are supported")
        for attempt in range(2):
            try:
                r = self.session.request(method, self.url + endpoint, headers=self._headers(),
                                         timeout=self.timeout, **kwargs)
            except requests.RequestException as e:
                raise LabelStudioError(f"Label Studio connection failed: {type(e).__name__}") from e
            if r.status_code == 401 and self.token_type == "pat" and attempt == 0:
                self.access = None
                continue
            if not r.ok:
                raise LabelStudioError(f"Label Studio {method} {endpoint} HTTP {r.status_code}: "
                                       f"{r.text[:200]}")
            return r
        raise LabelStudioError("Authentication failed after PAT refresh")

    def connect(self):
        return self.request("GET", "/api/projects/", params={"page_size": 1}).json()

    def get_project(self, project_id):
        return self.request("GET", f"/api/projects/{int(project_id)}/").json()

    def ensure_project(self, cfg, project_id=None):
        xml = label_xml(cfg.annotation)
        if project_id is None:
            project = self.request("POST", "/api/projects/", json={
                "title": cfg.annotation.project_title, "label_config": xml,
                "maximum_annotations": 2 if cfg.annotation.require_two_annotators else 1,
                "show_annotation_history": False, "show_collab_predictions": False,
                "expert_instruction": instruction_html(cfg.annotation)}).json()
        else:
            project = self.get_project(project_id)
            # Do not silently overwrite an existing project's labeling interface.
            if project.get("expert_instruction") != instruction_html(cfg.annotation):
                raise LabelStudioError("Existing project's annotator instructions/version differ")
            if not project.get("label_config"):
                raise LabelStudioError("Existing project response omitted label config; cannot verify")
            if (ET.tostring(ET.fromstring(project["label_config"])) !=
                ET.tostring(ET.fromstring(xml))):
                raise LabelStudioError("Existing project label config differs; choose a matching project")
        if "id" not in project:
            raise LabelStudioError("Project response missing id")
        if cfg.annotation.require_two_annotators and project.get("maximum_annotations", 0) < 2:
            raise LabelStudioError("Project must allow at least two annotations per task")
        # Server-side validation catches Label Studio's tag/ontology requirements.
        self.request("POST", f"/api/projects/{int(project['id'])}/validate/",
                     json={"label_config": xml})
        return project

    def list_tasks(self, project_id):
        result, page = [], 1
        while True:
            obj = self.request("GET", "/api/tasks/", params={
                "project": int(project_id), "fields": "all", "page": page,
                "page_size": 100}).json()
            tasks = obj.get("tasks") if isinstance(obj, dict) else obj
            if not isinstance(tasks, list):
                raise LabelStudioError("Unexpected paginated task response")
            result.extend(tasks)
            total = obj.get("total", obj.get("count")) if isinstance(obj, dict) else None
            if total is not None and len(result) >= total:
                break
            if len(tasks) < 100:
                break
            page += 1
            if page > 10000:
                raise LabelStudioError("Task pagination safety bound exceeded")
        return result

    def import_tasks(self, project_id, records, cfg, store, batch_size=100):
        existing = {}
        for task in self.list_tasks(project_id):
            data = task.get("data") or {}
            rid = data.get("source_id")
            if not rid:
                continue
            if rid in existing:
                raise LabelStudioError(f"Existing project contains duplicate source_id {rid}")
            existing[rid] = task
        payloads = [task_payload(r, cfg) for r in records if r["valid"]]
        if len({t["data"]["source_id"] for t in payloads}) != len(payloads):
            raise LabelStudioError("Duplicate source IDs among valid tasks")
        pending, skipped = [], 0
        for payload in payloads:
            rid = payload["data"]["source_id"]
            if rid in existing:
                task = existing[rid]
                if payload_hash({"data": task.get("data"), "meta": task.get("meta")}) != payload_hash(payload):
                    raise LabelStudioError(f"Remote task {rid} differs from current input/version")
                skipped += 1
            else:
                pending.append(payload)
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i+batch_size]
            resp = self.request("POST", f"/api/projects/{int(project_id)}/import",
                                params={"return_task_ids": "true"}, json=batch).json()
            # Only list_tasks verification below establishes success.
            if not isinstance(resp, (dict, list)):
                raise LabelStudioError("Unexpected task import response")
        remote = self.list_tasks(project_id)
        mapped = {}
        for task in remote:
            rid = (task.get("data") or {}).get("source_id")
            if rid in mapped:
                raise LabelStudioError(f"Duplicate remote source_id {rid}")
            if rid:
                mapped[rid] = task
        for payload in payloads:
            rid = payload["data"]["source_id"]
            target = mapped.get(rid)
            if target is None or "id" not in target:
                raise LabelStudioError(f"Import verification failed for {rid}")
            if payload_hash({"data": target.get("data"), "meta": target.get("meta")}) != payload_hash(payload):
                raise LabelStudioError(f"Task verification mismatch for {rid}")
            prev = store.import_map(project_id).get(rid)
            if prev and prev["task_id"] != target["id"]:
                raise LabelStudioError(f"Local task mapping conflict for {rid}")
            if not prev:
                store.remember_import(project_id, rid, int(target["id"]), payload_hash(payload))
        store.event("import_verified", payload={"project_id": project_id,
                    "new": len(pending), "preexisting": skipped, "verified": len(payloads)})
        return {"new": len(pending), "preexisting": skipped, "verified": len(payloads),
                "remote_project_tasks": len(remote)}

    def export_tasks(self, project_id, path: Path, poll_seconds=2, max_polls=150):
        """Asynchronous JSON snapshot, verifying full remote task identity before success."""
        created = self.request("POST", f"/api/projects/{int(project_id)}/exports/",
                               json={"task_filter_options": {"only_with_annotations": False},
                                     "serialization_options": {"include_annotation_history": True}}).json()
        snap_id = created.get("id")
        if snap_id is None:
            raise LabelStudioError("Snapshot creation response missing id")
        for _ in range(max_polls):
            status = self.request("GET", f"/api/projects/{int(project_id)}/exports/{snap_id}/").json()
            if status.get("status") == "completed":
                break
            if status.get("status") == "failed":
                raise LabelStudioError(f"Export snapshot {snap_id} failed")
            time.sleep(poll_seconds)
        else:
            raise LabelStudioError("Export snapshot not completed before polling limit")
        resp = self.request("GET", f"/api/projects/{int(project_id)}/exports/{snap_id}/download",
                            params={"exportType": "JSON"})
        try:
            tasks = resp.json()
        except ValueError as e:
            raise LabelStudioError("Export was not JSON") from e
        if not isinstance(tasks, list) or any(not isinstance(t, dict) for t in tasks):
            raise LabelStudioError("Export must contain JSON task objects")
        actual = self.list_tasks(project_id)
        actual_ids = {t.get("id") for t in actual}
        export_ids = {t.get("id") for t in tasks}
        if len(tasks) != len(actual) or len(export_ids) != len(tasks) or export_ids != actual_ids:
            raise LabelStudioError("Export task count/IDs differ from project task inventory")
        # A remote task list may expose annotation stubs or a full list; check counts
        # when detailed annotation arrays are visible to this administrative user.
        by_id = {t["id"]: t for t in actual}
        for task in tasks:
            remote = by_id[task["id"]]
            if (isinstance(remote.get("annotations"), list) and
                remote.get("total_annotations") is not None and
                len(task.get("annotations") or []) < int(remote["total_annotations"])):
                raise LabelStudioError(f"Incomplete annotation export for task {task['id']}")
        write_json(path, tasks)
        return {"exported_tasks": len(tasks), "file": str(path),
                "snapshot_id": snap_id, "export_strategy": "asynchronous_snapshot_verified"}
