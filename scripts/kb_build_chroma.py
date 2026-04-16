from __future__ import annotations

import argparse
import time

from dotenv import load_dotenv

from config import get_settings
from kb_store import KbStore, _doc_text, _stable_id


def _snapshot_existing_ids(col) -> set[str]:
    """Load all document ids in the collection once (avoids thousands of small col.get calls)."""
    out: set[str] = set()
    try:
        res = col.get(include=[])
        for i in res.get("ids") or []:
            if i is not None and str(i):
                out.add(str(i))
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"无法预加载 Chroma 已有 id（请检查库是否损坏或版本兼容）: {e}"
        ) from e
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build/update local Chroma KB from JSONL.")
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing Chroma collection then rebuild from source JSONL.",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="Full upsert mode: do not skip existing ids (still uses upsert).",
    )
    p.add_argument(
        "--collection",
        default="knowledge_base",
        help='Chroma collection name (default: "knowledge_base").',
    )
    p.add_argument(
        "--progress-every",
        type=int,
        default=200,
        help="Print progress every N added docs (default: 200).",
    )
    p.add_argument(
        "--progress-scan-every",
        type=int,
        default=2000,
        help="Also print every N JSONL rows scanned (incremental skip phase; default: 2000). Set 0 to disable.",
    )
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = _parse_args()
    s = get_settings()
    store = KbStore(s)
    chroma = store._chroma()
    collection_name = str(args.collection or "knowledge_base").strip() or "knowledge_base"
    if args.rebuild:
        try:
            chroma.delete_collection(name=collection_name)
            print(f"deleted_collection={collection_name}", flush=True)
        except Exception:
            # collection may not exist; keep going
            pass
    col = chroma.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    src = (s.kb_source_jsonl or "").strip()
    if not src:
        raise SystemExit("缺少 KB_SOURCE_JSONL（.env 里 KB_SOURCE_JSONL）")

    import json
    from pathlib import Path

    p = Path(src)
    print(f"KB_SOURCE_JSONL={p}", flush=True)

    batch = int(getattr(s, "embed_batch_size", 10) or 10)
    batch = max(1, min(batch, 10))

    print(
        f"collection={collection_name} rebuild={bool(args.rebuild)} mode={'full' if args.full else 'incremental'}",
        flush=True,
    )
    print(f"batch={batch} model={s.embed_model} base={s.embed_api_base}", flush=True)
    t0 = time.time()
    added = 0
    skipped = 0
    scanned = 0
    last_scan_bucket = -1
    scan_every = int(args.progress_scan_every or 0)

    existing_ids: set[str] = set()
    if not args.full:
        if args.rebuild:
            print({"existing_ids_loaded": 0, "note": "rebuild"}, flush=True)
        else:
            existing_ids = _snapshot_existing_ids(col)
            print({"existing_ids_loaded": len(existing_ids)}, flush=True)

    buf: list[dict] = []
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            buf.append(json.loads(line))
            if len(buf) < batch:
                continue

            ids = [_stable_id(r) for r in buf]
            if args.full:
                keep_mask = [True] * len(ids)
            else:
                keep_mask = [i not in existing_ids for i in ids]

            chunk = [r for r, keep in zip(buf, keep_mask) if keep]
            skipped += len(buf) - len(chunk)

            if chunk:
                chunk_ids = [_stable_id(r) for r in chunk]
                docs = [_doc_text(r) for r in chunk]
                metas = [
                    {
                        "source_file": r.get("source_file", ""),
                        "q_speaker": r.get("q_speaker", ""),
                        "q_ts": r.get("q_ts", ""),
                    }
                    for r in chunk
                ]
                embs = store.embed_texts(docs)
                col.upsert(ids=chunk_ids, documents=docs, metadatas=metas, embeddings=embs)
                added += len(chunk)
                if not args.full:
                    existing_ids.update(chunk_ids)
            scanned += len(buf)
            buf = []
            if scan_every > 0:
                bucket = scanned // scan_every
                if bucket > last_scan_bucket:
                    last_scan_bucket = bucket
                    print(
                        {
                            "scan_progress": True,
                            "jsonl_line": line_no,
                            "scanned_records": scanned,
                            "added": added,
                            "skipped": skipped,
                            "elapsed_s": round(time.time() - t0, 1),
                        },
                        flush=True,
                    )
            if args.progress_every and added > 0 and added % int(args.progress_every) == 0:
                print({"upserted": added, "skipped": skipped}, flush=True)

    if buf:
        tail_n = len(buf)
        ids = [_stable_id(r) for r in buf]
        if args.full:
            keep_mask = [True] * len(ids)
        else:
            keep_mask = [i not in existing_ids for i in ids]

        chunk = [r for r, keep in zip(buf, keep_mask) if keep]
        skipped += len(buf) - len(chunk)
        if chunk:
            chunk_ids = [_stable_id(r) for r in chunk]
            docs = [_doc_text(r) for r in chunk]
            metas = [
                {
                    "source_file": r.get("source_file", ""),
                    "q_speaker": r.get("q_speaker", ""),
                    "q_ts": r.get("q_ts", ""),
                }
                for r in chunk
            ]
            embs = store.embed_texts(docs)
            col.upsert(ids=chunk_ids, documents=docs, metadatas=metas, embeddings=embs)
            added += len(chunk)
        scanned += tail_n
        if scan_every > 0:
            bucket = scanned // scan_every
            if bucket > last_scan_bucket:
                last_scan_bucket = bucket
                print(
                    {
                        "scan_progress": True,
                        "jsonl_line": line_no,
                        "scanned_records": scanned,
                        "added": added,
                        "skipped": skipped,
                        "elapsed_s": round(time.time() - t0, 1),
                        "tail": True,
                    },
                    flush=True,
                )

    elapsed_s = round(time.time() - t0, 3)
    print(
        {
            "ok": True,
            "added": added,
            "skipped": skipped,
            "chroma_dir": s.kb_chroma_dir,
            "collection": collection_name,
            "count": col.count(),
            "elapsed_s": elapsed_s,
        },
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        raise

