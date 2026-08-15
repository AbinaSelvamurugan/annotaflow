import copy
from unittest.mock import Mock
import pytest
import requests

from annotaflow.label_studio import (LabelStudioAPI, LabelStudioError, label_xml,
                                      task_payload)
from annotaflow.storage import Store


class FakeResponse:
    def __init__(self, obj, status=200):
        self.obj = obj
        self.status_code = status
        self.ok = status < 400
        self.text = str(obj)

    def json(self):
        return self.obj


class FakeSession:
    def __init__(self):
        self.tasks = []
        self.created = None
        self.calls = []

    def request(self, method, url, headers, timeout, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/api/projects/1/"):
            return FakeResponse({"id": 1, "maximum_annotations": 2})
        if url.endswith("/api/projects/1/validate/"):
            return FakeResponse({"label_config": kwargs["json"]["label_config"]})
        if url.endswith("/api/projects/1/exports/") and method == "POST":
            return FakeResponse({"id": 19, "status": "created"}, 201)
        if url.endswith("/api/projects/1/exports/19/"):
            return FakeResponse({"id": 19, "status": "completed"})
        if url.endswith("/api/projects/1/exports/19/download"):
            return FakeResponse(self.tasks)
        if url.endswith("/api/projects/1/import"):
            for task in kwargs["json"]:
                self.tasks.append({**task, "id": len(self.tasks) + 1, "annotations": []})
            return FakeResponse({"task_count": len(kwargs["json"]),
                                 "task_ids": [t["id"] for t in self.tasks]})
        if url.endswith("/api/tasks/"):
            return FakeResponse({"tasks": self.tasks, "total": len(self.tasks)})
        if url.endswith("/api/projects/1/export"):
            return FakeResponse(self.tasks)
        if url.endswith("/api/projects/"):
            if method == "POST":
                self.created = kwargs["json"]
                return FakeResponse({"id": 1, "maximum_annotations": 2,
                                     "label_config": self.created["label_config"],
                                     "expert_instruction": self.created["expert_instruction"]}, 201)
            return FakeResponse({"results": []})
        return FakeResponse({"detail": "not found"}, 404)


def test_xml_and_task_serialization(cfg, synthetic_records):
    xml = label_xml(cfg.annotation)
    assert '<Choice value="Positive"' in xml
    task = task_payload(synthetic_records[0], cfg)
    assert task["data"]["source_id"] == "s1"
    assert task["meta"]["guideline_version"] == cfg.annotation.version
    bad = dict(synthetic_records[0], valid=False)
    with pytest.raises(ValueError): task_payload(bad, cfg)


def test_real_api_shaped_import_and_idempotency(cfg, synthetic_records, tmp_path):
    session = FakeSession()
    api = LabelStudioAPI("http://localhost:8080", "token", "legacy", session)
    store = Store(tmp_path / "store.sqlite")
    project = api.ensure_project(cfg)
    assert project["id"] == 1
    assert session.created["maximum_annotations"] == 2
    first = api.import_tasks(1, synthetic_records, cfg, store)
    assert first["new"] == 4
    second = api.import_tasks(1, synthetic_records, cfg, store)
    assert second["new"] == 0
    assert second["preexisting"] == 4
    assert len(session.tasks) == 4
    assert len(store.import_map(1)) == 4
    exported = api.export_tasks(1, tmp_path / "tasks.json")
    assert exported["exported_tasks"] == 4


def test_remote_id_collision_or_content_drift_rejected(cfg, synthetic_records, tmp_path):
    s = FakeSession()
    api = LabelStudioAPI("http://localhost:8080", "token", "legacy", s)
    store = Store(tmp_path / "store.sqlite")
    s.tasks = [{"id": 9, **task_payload(synthetic_records[0], cfg)}]
    changed = copy.deepcopy(synthetic_records)
    changed[0]["text"] = "Different text content"
    with pytest.raises(LabelStudioError, match="differs"):
        api.import_tasks(1, changed, cfg, store)
    s.tasks = s.tasks * 2
    with pytest.raises(LabelStudioError, match="duplicate source_id"):
        api.import_tasks(1, synthetic_records, cfg, store)


def test_connection_error_and_http_failure():
    session = Mock()
    session.request.side_effect = requests.ConnectionError("offline")
    api = LabelStudioAPI("http://localhost:8080", "token", "legacy", session)
    with pytest.raises(LabelStudioError, match="connection failed"):
        api.connect()
    session.request.side_effect = None
    session.request.return_value = FakeResponse({"detail": "forbidden"}, 403)
    with pytest.raises(LabelStudioError, match="403"):
        api.connect()


def test_pat_refresh_token_scheme_and_renewal():
    session = Mock()
    session.post.return_value = FakeResponse({"access": "short-lived"})
    session.request.return_value = FakeResponse({"results": []})
    api = LabelStudioAPI("http://localhost:8080", "refresh-token", "pat", session)
    api.connect()
    assert session.request.call_args.kwargs["headers"] == {"Authorization": "Bearer short-lived"}
    session.post.assert_called_once()


def test_ambiguous_auth_config_rejected():
    with pytest.raises(ValueError):
        LabelStudioAPI("http://localhost", "token", "guess")


def test_import_response_failure(cfg, synthetic_records, tmp_path):
    session = FakeSession()
    api = LabelStudioAPI("http://localhost:8080", "token", "legacy", session)
    store = Store(tmp_path / "store.sqlite")
    def bad_request(method, url, headers, timeout, **kwargs):
        if url.endswith("/import"):
            return FakeResponse({"detail":"failure"}, 400)
        return FakeSession.request(session, method, url, headers, timeout, **kwargs)
    session.request = bad_request
    with pytest.raises(LabelStudioError):
        api.import_tasks(1, synthetic_records, cfg, store)
