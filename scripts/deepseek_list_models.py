from __future__ import annotations

import json
import os
import sys
from urllib.parse import urljoin

import httpx


def _base_url() -> str:
    base = (os.environ.get("OPENAI_API_BASE") or "https://api.deepseek.com").strip()
    # deepseek OpenAI-compatible base usually requires /v1
    if not base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base


def _auth_headers() -> dict[str, str]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("缺少 OPENAI_API_KEY。请在 .env 设置后再运行。")
    return {"Authorization": f"Bearer {key}"}


def list_models() -> list[str]:
    base = _base_url()
    url = urljoin(base.rstrip("/") + "/", "models")
    with httpx.Client(timeout=20.0) as c:
        r = c.get(url, headers=_auth_headers())
        r.raise_for_status()
        data = r.json()
    out: list[str] = []
    for m in data.get("data") or []:
        mid = m.get("id")
        if isinstance(mid, str):
            out.append(mid)
    return out


def probe_embeddings(model: str) -> tuple[bool, str]:
    """尝试调用 /embeddings，判断是否可用。"""
    base = _base_url()
    url = urljoin(base.rstrip("/") + "/", "embeddings")
    payload = {"model": model, "input": ["hello"]}
    with httpx.Client(timeout=20.0) as c:
        r = c.post(url, headers={**_auth_headers(), "Content-Type": "application/json"}, json=payload)
    if r.status_code == 200:
        return True, "OK"
    # 尽量打印 body 帮你定位 404 的原因
    body = r.text.strip()
    if len(body) > 800:
        body = body[:800] + "…"
    return False, f"HTTP {r.status_code}: {body or '（空响应体）'}"


def main() -> None:
    try:
        models = list_models()
    except Exception as e:  # noqa: BLE001
        print("拉取模型列表失败：", repr(e), file=sys.stderr)
        sys.exit(2)

    print("OPENAI_API_BASE =", _base_url())
    print("models =", json.dumps(models, ensure_ascii=False, indent=2))

    # 依据 DeepSeek 文档示例，默认会看到 deepseek-chat / deepseek-reasoner
    if models:
        # 用第一个模型试探 embeddings（大概率会失败，用于确认 404 根因）
        ok, msg = probe_embeddings(models[0])
        print(f"embeddings_probe(model={models[0]!r}) =", ok, msg)


if __name__ == "__main__":
    main()

