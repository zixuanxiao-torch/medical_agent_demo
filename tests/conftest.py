"""共享 fixture：内存 SQLite，结构与种子数据与线上一致。"""

from __future__ import annotations

import sqlite3

import pytest

from db import init_db, seed_if_empty


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()
