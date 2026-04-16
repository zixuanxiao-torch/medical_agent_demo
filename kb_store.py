from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from openai import OpenAI

from config import Settings


class KbError(RuntimeError):
    pass


def _stable_id(rec: dict[str, Any]) -> str:
    h = str(rec.get("hash") or "").strip()
    if h:
        return h
    s = (str(rec.get("question", "")) + "\n" + str(rec.get("answer", ""))).encode("utf-8", errors="ignore")
    return hashlib.md5(s).hexdigest()


def _doc_text(rec: dict[str, Any]) -> str:
    q = str(rec.get("question") or "").strip()
    a = str(rec.get("answer") or "").strip()
    return f"Q: {q}\nA: {a}".strip()


@dataclass
class KbStore:
    settings: Settings

    def _chroma(self) -> chromadb.PersistentClient:
        p = Path(self.settings.kb_chroma_dir)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent / p
        p.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(p))

    def _collection(self):
        c = self._chroma()
        return c.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

    def _embed_client(self) -> OpenAI:
        if not self.settings.embed_api_key.strip():
            raise KbError("缺少 EMBED_API_KEY（.env 里 embed_api_key / EMBED_API_KEY）")
        return OpenAI(
            api_key=self.settings.embed_api_key.strip(),
            base_url=self.settings.embed_api_base.strip(),
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = self._embed_client()
        resp = client.embeddings.create(model=self.settings.embed_model, input=texts)
        return [d.embedding for d in resp.data]

    def retrieve(self, query: str, top_k: int | None = None) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {"ok": False, "error": "query 不能为空"}
        k = int(top_k or self.settings.kb_top_k or 5)
        k = max(1, min(k, 20))

        q_emb = self.embed_texts([q])[0]
        col = self._collection()
        res = col.query(query_embeddings=[q_emb], n_results=k)

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        hits: list[dict[str, Any]] = []
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append(
                {
                    "text": doc,
                    "meta": meta or {},
                    "distance": dist,
                }
            )
        return {"ok": True, "query": q, "top_k": k, "hits": hits}


def build_chroma_from_jsonl(
    settings: Settings,
    *,
    collection_name: str = "knowledge_base",
    batch: int = 128,
) -> dict[str, Any]:
    """离线建库：把 kb_source_jsonl 的 Q/A 生成 embedding 并写入 Chroma。"""
    src = (settings.kb_source_jsonl or "").strip()
    if not src:
        raise KbError("缺少 KB_SOURCE_JSONL（.env 里 kb_source_jsonl / KB_SOURCE_JSONL）")
    p = Path(src)
    if not p.is_file():
        raise KbError(f"KB_SOURCE_JSONL 不存在: {p}")

    store = KbStore(settings)
    client = store._embed_client()

    chroma_client = store._chroma()
    col = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    batch_size = int(getattr(settings, "embed_batch_size", batch) or batch)
    batch_size = max(1, min(batch_size, batch))

    added = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        ids = [_stable_id(r) for r in chunk]
        docs = [_doc_text(r) for r in chunk]
        metas = [
            {
                "source_file": r.get("source_file", ""),
                "q_speaker": r.get("q_speaker", ""),
                "q_ts": r.get("q_ts", ""),
            }
            for r in chunk
        ]

        resp = client.embeddings.create(model=settings.embed_model, input=docs)
        embs = [d.embedding for d in resp.data]
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        added += len(chunk)

    return {"ok": True, "added": added, "collection": collection_name, "chroma_dir": settings.kb_chroma_dir}

