"""API tests: FastAPI TestClient with the agent replaced by a stub (no Gemini calls)."""

import pytest
from fastapi.testclient import TestClient

from agent import AgentResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    import main

    class StubAgent:
        def __init__(self):
            self.error = None

        def run(self, resume_text, jd_text):
            if self.error:
                raise self.error
            return AgentResult(
                match_score=80,
                matched_must_have=["Python"],
                missing_must_have=["Excel"],
                rewritten_bullets=[{"original": "a", "improved": "b"}],
                reviewer_notes="ok",
            )

    stub = StubAgent()
    monkeypatch.setattr(main, "agent", stub)
    c = TestClient(main.app)
    c.stub = stub
    return c


VALID = {
    "resume_text": "Skills: Python, SQL, Git. Projects: CareerPilot.",
    "job_description": "We need Python and Excel for this data role.",
}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_analyze_returns_the_agent_result(client):
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 200
    body = r.json()
    assert body["match_score"] == 80
    assert body["missing_must_have"] == ["Excel"]
    assert body["rewritten_bullets"] == [{"original": "a", "improved": "b"}]
    assert body["suggestions"] == []


@pytest.mark.parametrize("field", ["resume_text", "job_description"])
def test_rejects_text_shorter_than_20_chars(client, field):
    r = client.post("/api/analyze", json={**VALID, field: "too short"})
    assert r.status_code == 422


def test_rejects_missing_fields(client):
    assert client.post("/api/analyze", json={}).status_code == 422


def test_llm_failure_maps_to_502(client):
    client.stub.error = RuntimeError("Gemini request failed: quota")
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 502
    assert "quota" in r.json()["detail"]


def test_unexpected_error_maps_to_500(client):
    client.stub.error = ValueError("boom")
    r = client.post("/api/analyze", json=VALID)
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]
