"""HTTP-level tests with a scripted model patched in for the real provider."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from tests.test_core import ScriptedLlm, call, text


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for d in ("agent", "input", "output", "jobs/p1/agent", "jobs/p1/input"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "jobs/p1/agent/instruction.md").write_text("pack instruction")
    (tmp_path / "jobs/p1/input/a.txt").write_text("A")
    for k, v in (("AGENT_DIR", "agent"), ("INPUT_DIR", "input"), ("OUTPUT_DIR", "output"), ("JOBS_DIR", "jobs")):
        monkeypatch.setenv(k, str(tmp_path / v))
    monkeypatch.setenv("JOB_HISTORY_FILE", str(tmp_path / "hist.json"))
    import importlib, web_app
    web_app = importlib.reload(web_app)
    web_app.chat_session.reset(web_app._read_instruction())
    web_app.batch_state.reset()
    scripts = {"s": [[text("hello there")]]}
    monkeypatch.setattr(web_app.adk_core, "_build_model",
                        lambda p, m: ScriptedLlm(script=scripts["s"], seen_system=[]))
    with TestClient(web_app.app) as c:
        c.scripts, c.web, c.root = scripts, web_app, tmp_path
        yield c


def sse(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]


def test_routes_not_shadowed(client):
    for path in ("/", "/api/session", "/api/providers", "/api/keys", "/api/tools", "/api/settings",
                 "/api/agent", "/api/input", "/api/output", "/api/jobpacks", "/api/batch/status",
                 "/api/batch/jobs", "/api/model", "/api/readme"):
        assert client.get(path).status_code == 200, path
    assert "gemini" in client.get("/api/providers").json()["providers"]
    assert client.get("/api/keys").json().keys() >= {"gemini", "anthropic"}
    assert any(t["name"] == "skills" for t in client.get("/api/tools").json()["tools"])


def test_file_crud_and_safety(client):
    assert client.put("/api/file/input/x.txt", json={"content": "hi"}).status_code == 200
    assert client.get("/api/file/input/x.txt").json()["content"] == "hi"
    assert client.get("/api/file/input/..%2f..%2fetc/passwd").status_code in (404, 400)
    assert client.put("/api/file/output/x.txt", json={"content": "no"}).status_code == 403
    assert client.post("/api/file/input", json={"name": "x.txt"}).status_code == 409
    up = client.post("/api/upload/input", files={"file": ("up load.txt", b"data")})
    assert up.json()["name"] == "up_load.txt"
    assert client.delete("/api/agent").status_code == 405
    assert client.delete("/api/input").json() == {"cleared": True}
    assert client.get("/api/input").json()["files"] == []


def test_jobpack_load(client):
    r = client.post("/api/jobpacks/load", json={"pack": "p1"})
    assert r.json()["copied"]["input"] == ["a.txt"]
    assert client.get("/api/file/agent/instruction.md").json()["content"] == "pack instruction"
    assert client.post("/api/jobpacks/load", json={"pack": "../x"}).status_code in (400, 404)


def test_chat_flow_and_skills_command(client):
    evs = sse(client.post("/api/chat", json={"message": "hi"}))
    types_ = [e["type"] for e in evs]
    assert types_[0] == "user_message" and types_[-1] == "done"
    assert "".join(e["content"] for e in evs if e["type"] == "delta") == "hello there"
    assert client.get("/api/session").json()["status"] == "idle"
    (client.root / "agent" / "SKILL-x.md").write_text("# X\nskill body")
    evs = sse(client.post("/api/chat", json={"message": "/skills"}))
    assert evs[-1]["message"]["files"] == ["SKILL-x.md"]
    assert client.post("/api/chat", json={"message": ""}).status_code == 400
    assert client.post("/api/chat/reset").status_code == 200


def test_batch_run(client):
    (client.root / "input" / "f.txt").write_text("data")
    client.scripts["s"] = [[call("write_output", path="r.md", content="x")], [text("fin")]]
    assert client.post("/api/batch/run").json() == {"status": "started"}
    assert client.post("/api/batch/run").status_code == 409
    for _ in range(100):
        st = client.get("/api/batch/status").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "completed", st
    assert st["metrics"]["total_turns"] == 1 and st["metrics"]["output_files"] == 1
    logs = sse(client.get("/api/batch/logs"))
    assert logs[-1] == {"done": True, "status": "completed"}
    assert (client.root / "output" / "agent.log").is_file()
    assert client.get("/api/batch/jobs").json()["jobs"][-1]["status"] == "completed"


def test_batch_missing_key(client, monkeypatch):
    monkeypatch.setenv("API_PROVIDER", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert "GOOGLE_API_KEY" in client.post("/api/batch/run").json()["error"]


def test_model_listing_paginates_and_skips_failure_cache(client, monkeypatch):
    web = client.web
    pages = {None: {"data": [{"id": "a"}, {"id": "b"}], "has_more": True, "last_id": "b"},
             "b": {"data": [{"id": "c"}], "has_more": False}}

    async def fake_get_json(_c, url, params=None, **kw):
        if "anthropic" in url:
            return pages[(params or {}).get("after_id")]
        raise RuntimeError("boom")

    monkeypatch.setattr(web, "_get_json", fake_get_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    web._model_cache.clear()
    ids = [m["id"] for m in client.get("/api/models?provider=anthropic").json()["models"]]
    assert ids == ["a", "b", "c"]
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert client.get("/api/models?provider=openai").json()["models"] == []
    assert "openai" not in web._model_cache


def test_key_status_is_per_provider(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    client.post("/api/keys", json={"provider": "openai-compatible", "key": "k"})
    keys = client.get("/api/keys").json()
    assert keys["openai-compatible"] is True and keys["openai"] is False
