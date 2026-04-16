#!/usr/bin/env python3
"""
批量场景测试：请求运行中的 POST /chat（debug=true），根据 scenarios.json 做检查。

用法（先另开终端启动服务）:
  cd medical_agent_demo
  uvicorn app:app --host 127.0.0.1 --port 8000

再执行:
  python scripts/run_scenarios.py
  python scripts/run_scenarios.py --base-url http://127.0.0.1:8000
  set CHAT_API_TOKEN=你的token && python scripts/run_scenarios.py

若出现 HTTP 502 且响应体为空：多为系统/公司代理劫持了本机地址。本脚本默认 trust_env=False（不走代理）。
若你故意要通过代理访问远端智能体，请加: --trust-env

结果写入 scenarios/results/last_run.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "scenarios" / "scenarios.json"
RESULTS_DIR = ROOT / "scenarios" / "results"


def load_scenarios() -> list[dict[str, Any]]:
    if not SCENARIOS_PATH.is_file():
        print(f"未找到 {SCENARIOS_PATH}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return list(data.get("scenarios") or [])


def trace_tool_names(trace: list[Any] | None) -> list[str]:
    if not trace:
        return []
    names: list[str] = []
    for step in trace:
        if isinstance(step, dict) and step.get("type") == "tool":
            n = step.get("name")
            if isinstance(n, str):
                names.append(n)
    return names


def check_scenario(row: dict[str, Any], reply: str, trace: list[Any] | None) -> tuple[bool, str]:
    if row.get("expect_emergency"):
        has_short = any(
            isinstance(s, dict) and s.get("type") == "emergency_short_circuit" for s in (trace or [])
        )
        if has_short and "120" in reply:
            return True, "急症短路 + 回复含 120"
        if "120" in reply:
            return True, "回复含 120（未在 trace 中看到短路标记，宽松通过）"
        return False, "未见急症处理（无 120 或 trace 异常）"

    if row.get("expect_tool"):
        want = row["expect_tool"]
        got = trace_tool_names(trace)
        if want in got:
            return True, f"已调用工具 {want}"
        return False, f"期望工具 {want}，实际 trace 中工具序列: {got or '无'}"

    if row.get("expect_reply_contains"):
        sub = row["expect_reply_contains"]
        if sub in reply:
            return True, f"回复包含 {sub!r}"
        return False, f"回复未包含 {sub!r}"

    if row.get("must_not_contain"):
        bad = row["must_not_contain"]
        if bad in reply:
            return False, f"回复不应包含 {bad!r}"
        return True, f"回复未出现 {bad!r}"

    return True, "无自动断言字段，仅记录"


def _http_error_detail(r: httpx.Response) -> str:
    body = (r.text or "").strip()
    if not body:
        body = "（响应体为空）"
    else:
        body = body[:500]
    phrase = getattr(r, "reason_phrase", None) or ""
    tail = ""
    if r.status_code == 502 and not (r.text or "").strip():
        tail = (
            " 常见原因：① 本机未启动 uvicorn；② 系统代理/抓包软件把 127.0.0.1 转发失败（请用默认 trust_env=False 重试，"
            "或关闭代理后再试）。"
        )
    return f"HTTP {r.status_code} {phrase}: {body}{tail}"


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 scenarios/scenarios.json 对接口 /chat 的批量检查")
    parser.add_argument("--base-url", default=os.environ.get("AGENT_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="使用系统环境变量中的 HTTP(S)_PROXY（默认关闭，避免本机 127.0.0.1 被错误代理成 502）",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    token = (os.environ.get("CHAT_API_TOKEN") or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["X-Chat-Token"] = token

    scenarios = load_scenarios()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "last_run.json"
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    client_kw: dict[str, Any] = {"timeout": args.timeout}
    if not args.trust_env:
        client_kw["trust_env"] = False

    with httpx.Client(**client_kw) as client:
        try:
            hr = client.get(f"{base}/health")
        except httpx.RequestError as e:
            print(f"预检失败：无法连接 {base}/health → {e}", file=sys.stderr)
            print("请先在本机启动: uvicorn app:app --host 127.0.0.1 --port 8000", file=sys.stderr)
            sys.exit(2)

        if hr.status_code != 200:
            print(f"预检失败：GET /health 返回 {hr.status_code}，智能体可能未正常启动。", file=sys.stderr)
            print(_http_error_detail(hr), file=sys.stderr)
            sys.exit(2)
        for row in scenarios:
            sid = row.get("id", "?")
            payload = {"message": row["message"], "debug": True}
            try:
                r = client.post(f"{base}/chat", headers=headers, json=payload)
            except httpx.RequestError as e:
                results.append(
                    {
                        "id": sid,
                        "ok": False,
                        "error": f"连接失败: {e}（请先启动 uvicorn）",
                    }
                )
                failed += 1
                continue

            if r.status_code != 200:
                detail = _http_error_detail(r)
                results.append(
                    {
                        "id": sid,
                        "ok": False,
                        "http_status": r.status_code,
                        "error": detail,
                    }
                )
                failed += 1
                continue

            data = r.json()
            reply = data.get("reply") or ""
            trace = data.get("debug_trace")
            ok, reason = check_scenario(row, reply, trace)
            if ok:
                passed += 1
            else:
                failed += 1
            results.append(
                {
                    "id": sid,
                    "ok": ok,
                    "reason": reason,
                    "reply_preview": reply[:300],
                    "trace_tool_names": trace_tool_names(trace),
                }
            )

    summary = {
        "at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "total": len(scenarios),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"完成：通过 {passed} / 失败 {failed}，共 {len(scenarios)} 条")
    print(f"详情：{out_path}")
    for item in results:
        mark = "OK " if item.get("ok") else "FAIL"
        line = item.get("reason") or item.get("error") or ""
        if len(line) > 200:
            line = line[:200] + "…"
        print(f"  [{mark}] {item.get('id')}: {line}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
