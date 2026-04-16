"""工具层纯逻辑测试：不调用 LLM，秒级跑完。"""

from __future__ import annotations

import sqlite3

from tools import run_tool


def test_query_medical_table_hits_seed(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_medical_table", {"keyword": "空腹"})
    assert out["ok"] is True
    assert out["count"] >= 1
    assert any("空腹" in str(r.get("title", "")) or "空腹" in str(r.get("content", "")) for r in out["rows"])


def test_query_medical_table_empty_keyword(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_medical_table", {"keyword": "  "})
    assert out["ok"] is False
    assert "keyword" in out.get("error", "").lower() or "空" in out["error"]


def test_query_order_by_id(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_order", {"order_id": "ORD2025001"})
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["orders"][0]["id"] == "ORD2025001"


def test_query_order_by_phone(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_order", {"phone_last4": "1234"})
    assert out["ok"] is True
    assert out["count"] >= 1


def test_query_order_missing_args(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_order", {})
    assert out["ok"] is False


def test_unknown_tool(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "not_a_real_tool", {})
    assert out["ok"] is False
    assert "未知" in out["error"] or "unknown" in out["error"].lower()


def test_create_ticket_then_query(conn: sqlite3.Connection) -> None:
    t = "测试工单标题"
    d = "测试详情内容"
    out = run_tool(conn, "create_ticket", {"title": t, "detail": d})
    assert out["ok"] is True
    tid = out["ticket_id"]
    q = run_tool(conn, "query_ticket", {"ticket_id": tid})
    assert q["ok"] is True
    assert q["count"] == 1
    assert q["tickets"][0]["title"] == t


def test_query_ticket_invalid_id(conn: sqlite3.Connection) -> None:
    out = run_tool(conn, "query_ticket", {"ticket_id": "abc"})
    assert out["ok"] is False
