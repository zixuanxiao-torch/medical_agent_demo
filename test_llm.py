"""测试 .env 里的 LLM 配置是否可用。
在 medical_agent_demo 目录下: python test_llm.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv


async def main() -> int:
    load_dotenv()
    backend = os.environ.get("LLM_BACKEND", "ollama").strip()

    import httpx

    if backend == "openai_compatible":
        base = os.environ.get("OPENAI_API_BASE", "https://api.deepseek.com").rstrip("/")
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = os.environ.get("OPENAI_MODEL", "deepseek-chat").strip()
        if not key:
            print("请在 .env 中设置 OPENAI_API_KEY")
            return 1
        url = base + "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "用一句话回复：你好"}],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, json=payload, timeout=60.0)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError:
                print("HTTP", r.status_code, r.text[:500])
                return 1
            data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        print("后端: openai_compatible | 模型:", model)
        print("回复:", (content or "")[:500])
        return 0

    # ollama
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    url = base + "/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "用一句话回复：你好"}],
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, timeout=60.0)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            print("HTTP", r.status_code, r.text[:500])
            print("请确认 Ollama 已启动且已 ollama pull", model)
            return 1
        data = r.json()
    content = (data.get("message") or {}).get("content", "")
    print("后端: ollama | 模型:", model)
    print("回复:", (content or "")[:500])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
