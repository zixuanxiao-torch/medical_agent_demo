from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Settings, finetune_jsonl_resolved


def append_finetune_record(settings: Settings, record: dict[str, Any]) -> Path:
    path = finetune_jsonl_resolved(settings)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def count_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def build_record_from_messages(
    messages: list[dict[str, str]],
    *,
    tags: list[str] | None = None,
    source: str | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "chatml_messages",
        "messages": messages,
    }
    if tags:
        rec["tags"] = tags
    if source:
        rec["source"] = source
    if session_id:
        rec["session_id"] = session_id
    if extra:
        rec["extra"] = extra
    return rec
