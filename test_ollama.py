"""在 my_lab_env 中运行: python test_ollama.py
用于确认 Ollama 已启动且模型名称正确。
"""

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    url = base + "/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "用一句话回复：你好"}],
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("连接失败:", e)
        print("请先安装并启动 Ollama，并执行: ollama pull", model)
        return 1
    msg = body.get("message") or {}
    content = msg.get("content", "")
    print("模型:", model)
    print("回复:", content[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
