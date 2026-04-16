"""
Merge two KB JSONL files (question/answer rows) for Chroma ingest.

Stable id matches kb_store._stable_id: use record["hash"] if present, else MD5(question + "\\n" + answer).

Usage:
  py -3 -m scripts.kb_merge_jsonl --base D:/path/kb_clean.jsonl --add D:/path/new_kb_clean.jsonl --out D:/path/kb_merged.jsonl

Then point KB_SOURCE_JSONL to merged file (or replace canonical kb_clean.jsonl) and run incremental build:
  py -3 -m scripts.kb_build_chroma
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from kb_store import _stable_id


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Merge KB JSONL (dedupe by stable id).")
    p.add_argument("--base", required=True, help="Existing kb_clean.jsonl")
    p.add_argument("--add", required=True, help="New kb_clean.jsonl to append")
    p.add_argument("--out", required=True, help="Output merged JSONL path")
    args = p.parse_args()

    base_path = Path(args.base)
    add_path = Path(args.add)
    out_path = Path(args.out)
    if not base_path.is_file():
        raise SystemExit(f"base not found: {base_path}")
    if not add_path.is_file():
        raise SystemExit(f"add not found: {add_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats: Counter[str] = Counter()
    order: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}

    for label, path in (("base", base_path), ("add", add_path)):
        for rec in _load_rows(path):
            stats[f"in_{label}"] += 1
            sid = _stable_id(rec)
            if not str(rec.get("question", "")).strip() and not str(rec.get("answer", "")).strip():
                stats["empty_row"] += 1
                continue
            if not sid:
                stats["empty_id"] += 1
                continue
            if sid in by_id:
                stats[f"dup_{label}"] += 1
                continue
            by_id[sid] = rec
            order.append(sid)

    with out_path.open("w", encoding="utf-8") as w:
        for sid in order:
            w.write(json.dumps(by_id[sid], ensure_ascii=False) + "\n")

    stats["out_total"] = len(order)
    print(
        {
            "ok": True,
            "out": str(out_path),
            "base_in": int(stats["in_base"]),
            "add_in": int(stats["in_add"]),
            "out_total": int(stats["out_total"]),
            "dup_base": int(stats.get("dup_base", 0)),
            "dup_add": int(stats.get("dup_add", 0)),
            "empty_id": int(stats.get("empty_id", 0)),
            "empty_row": int(stats.get("empty_row", 0)),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
