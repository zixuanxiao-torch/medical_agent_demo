"""模型输出 JSON 解析、急症短路：不调用 LLM。"""

from __future__ import annotations

import pytest

from agent import _emergency_hit, _extract_json_object
from prompts import EMERGENCY_REPLY


def test_extract_plain_json() -> None:
    obj = _extract_json_object('{"action":"reply","text":"你好"}')
    assert obj["action"] == "reply"
    assert obj["text"] == "你好"


def test_extract_fenced_json() -> None:
    raw = '说明如下\n```json\n{"action":"tool","name":"query_order","arguments":{"order_id":"ORD2025001"}}\n```'
    obj = _extract_json_object(raw)
    assert obj["action"] == "tool"
    assert obj["name"] == "query_order"


def test_extract_embedded_braces() -> None:
    obj = _extract_json_object('prefix {"action":"reply","text":"ok"} suffix')
    assert obj["action"] == "reply"


def test_extract_invalid_raises() -> None:
    with pytest.raises(ValueError, match="合法 JSON"):
        _extract_json_object("not json at all")


def test_emergency_hit_chest_pain() -> None:
    assert _emergency_hit("我剧烈胸痛") is True


def test_emergency_hit_normal() -> None:
    assert _emergency_hit("体检报告多久出") is False


def test_emergency_reply_content() -> None:
    assert "120" in EMERGENCY_REPLY
