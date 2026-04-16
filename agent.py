from __future__ import annotations

import json
import re
from typing import Any

import httpx
import sqlite3

from config import Settings
from prompts import EMERGENCY_KEYWORDS, EMERGENCY_REPLY, SYSTEM_PROMPT, build_tool_feedback_prompt
from tools import ALLOWED_TOOLS, run_tool


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise ValueError("模型未返回合法 JSON")


def _emergency_hit(message: str) -> bool:
    for k in EMERGENCY_KEYWORDS:
        if k in message:
            return True
    return False


async def call_ollama(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    url = settings.ollama_base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    r = await client.post(url, json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    msg = data.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Ollama 响应缺少 message.content")
    return content


async def call_openai_compatible(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    if not settings.openai_api_key.strip():
        raise RuntimeError("已启用 openai_compatible，但未配置 OPENAI_API_KEY（写入 .env）")
    base = settings.openai_api_base.rstrip("/")
    url = base + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.2,
    }
    r = await client.post(url, headers=headers, json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("API 响应缺少 choices")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError("API 响应缺少 choices[0].message.content")
    return content


async def call_llm(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    if settings.llm_backend == "openai_compatible":
        return await call_openai_compatible(client, settings, messages)
    return await call_ollama(client, settings, messages)


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    out: list[dict[str, str]] = []
    for h in history:
        role = h.get("role")
        content = h.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        out.append({"role": role, "content": content})
    return out[-20:]


async def run_turn(
    client: httpx.AsyncClient,
    settings: Settings,
    conn: sqlite3.Connection,
    user_message: str,
    history: list[dict[str, str]] | None,
) -> tuple[str, list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []

    if _emergency_hit(user_message):
        trace.append({"type": "emergency_short_circuit", "hit": True})
        return EMERGENCY_REPLY, trace

    hist = _normalize_history(history)
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(hist)
    messages.append({"role": "user", "content": user_message})

    rounds = max(1, int(settings.agent_max_tool_rounds))
    for i in range(rounds):
        raw = await call_llm(client, settings, messages)
        trace.append({"type": "model_raw", "round": i, "preview": raw[:800]})

        try:
            obj = _extract_json_object(raw)
        except ValueError:
            fallback = (
                "抱歉，我这次没有按格式生成回复。请再说一下您的需求（例如：查询订单 ORD2025001，"
                "或提供手机后四位）。"
            )
            trace.append({"type": "parse_error", "detail": "invalid_json"})
            return fallback, trace

        action = obj.get("action")
        if action == "reply":
            text = obj.get("text")
            if not isinstance(text, str) or not text.strip():
                return "（内部错误：reply 缺少 text）", trace
            trace.append({"type": "final", "action": "reply"})
            return text.strip(), trace

        if action == "tool":
            name = obj.get("name")
            arguments = obj.get("arguments")
            if not isinstance(name, str) or name not in ALLOWED_TOOLS:
                trace.append({"type": "bad_tool_name", "name": name})
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "工具名不合法。请只使用 query_medical_table / query_order / query_ticket / create_ticket，并输出合法 JSON。",
                    },
                )
                continue
            if not isinstance(arguments, dict):
                arguments = {}

            result = run_tool(conn, name, arguments)
            trace.append({"type": "tool", "name": name, "arguments": arguments, "result": result})

            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": build_tool_feedback_prompt(name, result)},
            )
            continue

        trace.append({"type": "bad_action", "action": action})
        return "（内部错误：action 必须是 reply 或 tool）", trace

    return "抱歉，本轮对话工具调用次数过多，请简化问题后重试。", trace
