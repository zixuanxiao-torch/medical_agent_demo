import sqlite3
from pathlib import Path
from typing import Any


def connect(db_file: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS medical_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            keyword TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            phone_last4 TEXT,
            item_name TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def seed_if_empty(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) AS c FROM medical_items")
    if cur.fetchone()["c"] > 0:
        return

    items: list[tuple[str, str, str, str]] = [
        (
            "体检",
            "空腹",
            "抽血前是否要空腹",
            "部分项目需空腹 8–12 小时（以医院说明为准）。饮水少量通常可，具体以预约单为准。",
        ),
        (
            "体检",
            "报告",
            "报告多久出",
            "常规体检报告一般 3–7 个工作日出具，加急项目以科室通知为准。",
        ),
        (
            "预约",
            "改期",
            "如何改期",
            "请通过原预约渠道或致电客服提供姓名与预约号办理改期。",
        ),
        (
            "预约",
            "预约丁小丁",
            "如何预约丁小丁",
            "不许预约丁小丁。",
        ),
    ]
    conn.executemany(
        "INSERT INTO medical_items (category, keyword, title, content) VALUES (?, ?, ?, ?)",
        items,
    )

    orders: list[tuple[str, str | None, str, str, str]] = [
        ("ORD2025001", "1234", "入职体检套餐", "已完成", "报告已上传系统"),
        ("ORD2025002", "5678", "幽门螺杆菌检测", "待采样", "请按预约时间到院"),
    ]
    conn.executemany(
        "INSERT INTO orders (id, phone_last4, item_name, status, note) VALUES (?, ?, ?, ?, ?)",
        orders,
    )
    conn.commit()


def search_medical_items(conn: sqlite3.Connection, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    like = f"%{keyword.strip()}%"
    cur = conn.execute(
        """
        SELECT category, keyword, title, content
        FROM medical_items
        WHERE keyword LIKE ? OR title LIKE ? OR content LIKE ?
        LIMIT ?
        """,
        (like, like, like, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def list_all_tickets_admin(conn: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
    """管理后台：工单列表，新在前。"""
    cur = conn.execute(
        """
        SELECT id, title, detail, status, created_at
        FROM tickets
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def list_tickets_newer_than(conn: sqlite3.Connection, after_id: int) -> list[dict[str, Any]]:
    """id 大于 after_id 的工单，按 id 升序（便于提示「新增」顺序）。"""
    cur = conn.execute(
        """
        SELECT id, title, detail, status, created_at
        FROM tickets
        WHERE id > ?
        ORDER BY id ASC
        """,
        (after_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def find_order(conn: sqlite3.Connection, order_id: str | None, phone_last4: str | None) -> list[dict[str, Any]]:
    rows: list[sqlite3.Row] = []
    if order_id:
        cur = conn.execute(
            "SELECT id, phone_last4, item_name, status, note FROM orders WHERE id = ?",
            (order_id.strip(),),
        )
        rows = cur.fetchall()
    elif phone_last4:
        cur = conn.execute(
            "SELECT id, phone_last4, item_name, status, note FROM orders WHERE phone_last4 = ?",
            (phone_last4.strip(),),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def create_ticket(conn: sqlite3.Connection, title: str, detail: str) -> dict[str, Any]:
    cur = conn.execute(
        "INSERT INTO tickets (title, detail, status) VALUES (?, ?, 'open')",
        (title.strip(), detail.strip()),
    )
    conn.commit()
    tid = cur.lastrowid
    return {"ticket_id": tid, "status": "open"}


def query_tickets(
    conn: sqlite3.Connection,
    ticket_id: int | None = None,
    recent_limit: int = 10,
) -> list[dict[str, Any]]:
    """按工单 id 精确查，或不传 id 时返回最近若干条（演示用）。"""
    if ticket_id is not None:
        cur = conn.execute(
            """
            SELECT id, title, detail, status, created_at
            FROM tickets WHERE id = ?
            """,
            (ticket_id,),
        )
    else:
        cur = conn.execute(
            """
            SELECT id, title, detail, status, created_at
            FROM tickets ORDER BY id DESC LIMIT ?
            """,
            (recent_limit,),
        )
    return [dict(r) for r in cur.fetchall()]
