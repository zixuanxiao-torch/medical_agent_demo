import sqlite3
from typing import Any

from db import create_ticket, find_order, query_tickets, search_medical_items
from kb_store import KbStore

ALLOWED_TOOLS = frozenset(
    {"query_medical_table", "query_order", "query_ticket", "create_ticket", "kb_retrieve"},
)


def run_tool(
    conn: sqlite3.Connection,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        return {"ok": False, "error": f"未知工具: {name}"}

    if name == "query_medical_table":
        kw = str(arguments.get("keyword", "")).strip()
        if not kw:
            return {"ok": False, "error": "keyword 不能为空"}

        rows = search_medical_items(conn, kw)
        return {"ok": True, "rows": rows, "count": len(rows)}

    if name == "query_order":
        order_id = arguments.get("order_id")
        phone_last4 = arguments.get("phone_last4")
        if not order_id and not phone_last4:
            return {"ok": False, "error": "请提供 order_id 或 phone_last4"}

        rows = find_order(conn, str(order_id) if order_id else None, str(phone_last4) if phone_last4 else None)
        return {"ok": True, "orders": rows, "count": len(rows)}

    if name == "query_ticket":
        raw_id = arguments.get("ticket_id")
        if raw_id is not None and str(raw_id).strip() != "":
            try:
                tid = int(str(raw_id).strip())
            except ValueError:
                return {"ok": False, "error": "ticket_id 必须是整数，例如 1"}
            rows = query_tickets(conn, ticket_id=tid)
        else:
            rows = query_tickets(conn, ticket_id=None)
        return {
            "ok": True,
            "tickets": rows,
            "count": len(rows),
            "note": "数据来源为客服工单表 tickets，不是订单表 orders",
        }

    if name == "create_ticket":
        title = str(arguments.get("title", "")).strip()
        detail = str(arguments.get("detail", "")).strip()
        if not title or not detail:
            return {"ok": False, "error": "title 与 detail 均不能为空"}

        out = create_ticket(conn, title, detail)
        return {"ok": True, **out}

    if name == "kb_retrieve":
        query = str(arguments.get("query", "")).strip()
        try:
            top_k = int(arguments.get("top_k", 5))
        except Exception:
            top_k = 5
        # settings 是单例（config.get_settings），kb_store 内部会读取它
        from config import get_settings

        store = KbStore(get_settings())
        return store.retrieve(query, top_k=top_k)

    return {"ok": False, "error": "未实现"}
