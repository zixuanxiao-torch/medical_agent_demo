"""FastAPI 健康检查（不调用 LLM）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import app


def test_health_ok() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "llm_backend" in data
