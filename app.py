from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent import run_turn
from config import Settings, db_path_resolved, finetune_jsonl_resolved, get_settings
from db import (
    connect,
    init_db,
    list_all_tickets_admin,
    list_tickets_newer_than,
    seed_if_empty,
)
from finetune_store import append_finetune_record, build_record_from_messages, count_lines
from prompts import SYSTEM_PROMPT
from tool_registry import get_tool_registry
from channels.wecom import router as wecom_router
from stores.session_store import MemorySessionStore


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None
    history: list[ChatMessage] | None = None
    debug: bool = False


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    debug_trace: list | None = None


class FinetuneSampleBody(BaseModel):
    """写入一条 SFT 用 JSONL 样本（多轮 messages）。"""

    messages: list[ChatMessage] = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    source: str | None = Field(None, max_length=200)
    include_system_prompt: bool = False
    extra: dict[str, Any] | None = None

    @field_validator("messages")
    @classmethod
    def roles_ok(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        allowed = {"system", "user", "assistant"}
        for m in v:
            if m.role not in allowed:
                raise ValueError(f"role 仅允许 system/user/assistant，收到: {m.role}")
        return v


class FinetuneFromSessionBody(BaseModel):
    session_id: str = Field(..., min_length=8)
    tags: list[str] = Field(default_factory=list)
    source: str = "session_export"
    include_system_prompt: bool = False


settings = get_settings()
db_file = db_path_resolved(settings)
http_client: httpx.AsyncClient | None = None
SESSIONS: dict[str, list[dict[str, str]]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    _conn = connect(db_file)
    try:
        init_db(_conn)
        seed_if_empty(_conn)
    finally:
        _conn.close()
    # Avoid system proxy breaking localhost or API calls
    http_client = httpx.AsyncClient(trust_env=False)
    # expose state for channels / tools
    app.state.http_client = http_client
    app.state.settings = settings
    app.state.db_file = db_file
    app.state.session_store = MemorySessionStore()
    app.state.wecom_seen = {}
    yield
    if http_client is not None:
        await http_client.aclose()
        http_client = None


app = FastAPI(title="Medical Agent Demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# channels
app.include_router(wecom_router)


@app.get("/")
async def index():
    index_html = static_dir / "index.html"
    if not index_html.is_file():
        raise HTTPException(404, "static/index.html 缺失")
    return FileResponse(index_html)


@app.get("/health")
async def health():
    out = {
        "ok": True,
        "db": str(db_file),
        "llm_backend": settings.llm_backend,
    }
    if settings.llm_backend == "openai_compatible":
        out["model"] = settings.openai_model
        out["api_base"] = settings.openai_api_base
    else:
        out["model"] = settings.ollama_model
        out["ollama_base"] = settings.ollama_base_url
    return out


def _verify_chat_api(
    authorization: str | None,
    x_chat_token: str | None,
) -> None:
    """内接时建议设置 CHAT_API_TOKEN，由调用方在请求头携带。"""
    expected = (settings.chat_api_token or "").strip()
    if not expected:
        return
    got = (x_chat_token or "").strip()
    if not got and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=401,
            detail=(
                "对话接口需要凭证：请求头 X-Chat-Token: <与 CHAT_API_TOKEN 相同>，"
                "或 Authorization: Bearer <与 CHAT_API_TOKEN 相同>"
            ),
        )


def _verify_admin(
    token: str | None,
    x_admin_token: str | None,
) -> None:
    expected = (settings.admin_token or "").strip()
    if not expected:
        return
    got = (x_admin_token or token or "").strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail="管理接口需要 token：URL 加 ?token= 或请求头 X-Admin-Token（与 .env 中 ADMIN_TOKEN 一致）",
        )


@app.get("/admin")
async def admin_page():
    admin_html = static_dir / "admin.html"
    if not admin_html.is_file():
        raise HTTPException(404, "static/admin.html 缺失")
    return FileResponse(admin_html)


@app.get("/admin/api/tickets")
async def admin_api_tickets(
    after_id: int = Query(0, ge=0, description="id 大于该值的工单；0 表示返回当前全量列表"),
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """管理后台轮询：浏览器每 2 秒请求一次；after_id 用上次返回的 max_id 可只拉增量。"""
    _verify_admin(token, x_admin_token)
    conn = connect(db_file)
    try:
        if after_id <= 0:
            tickets = list_all_tickets_admin(conn)
        else:
            tickets = list_tickets_newer_than(conn, after_id)
        max_row = conn.execute("SELECT IFNULL(MAX(id), 0) AS m FROM tickets").fetchone()
        max_id = int(max_row["m"])
        total = int(conn.execute("SELECT COUNT(*) AS c FROM tickets").fetchone()["c"])
    finally:
        conn.close()
    return {
        "tickets": tickets,
        "max_id": max_id,
        "total": total,
        "poll_interval_sec": max(1, settings.admin_poll_interval_sec),
    }


@app.get("/admin/api/tools/registry")
async def admin_tools_registry(
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """工具清单 + 数据范围 + 边界说明，便于 Bruno/Apifox 对接与写微调数据说明。"""
    _verify_admin(token, x_admin_token)
    return get_tool_registry()


@app.post("/admin/api/ft/sample")
async def admin_ft_append_sample(
    body: FinetuneSampleBody,
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """追加一条微调样本到 data/finetune/samples.jsonl（一行一个 JSON）。"""
    _verify_admin(token, x_admin_token)
    msgs = [m.model_dump() for m in body.messages]
    if body.include_system_prompt:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + msgs
    rec = build_record_from_messages(
        msgs,
        tags=body.tags or None,
        source=body.source,
        extra=body.extra,
    )
    path = append_finetune_record(settings, rec)
    return {"ok": True, "id": rec["id"], "path": str(path), "lines_total": count_lines(path)}


@app.post("/admin/api/ft/from-session")
async def admin_ft_from_session(
    body: FinetuneFromSessionBody,
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """把当前内存中的对话 session 导出为一条 JSONL 样本（需该 session 在服务端仍存在）。"""
    _verify_admin(token, x_admin_token)
    store: MemorySessionStore = app.state.session_store
    hist = store.get(body.session_id)
    if not hist:
        raise HTTPException(404, "未找到该 session_id，可能已过期或未在本进程聊过")
    msgs = list(hist)
    if body.include_system_prompt:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + msgs
    rec = build_record_from_messages(
        msgs,
        tags=body.tags or None,
        source=body.source,
        session_id=body.session_id,
    )
    path = append_finetune_record(settings, rec)
    return {"ok": True, "id": rec["id"], "path": str(path), "lines_total": count_lines(path)}


@app.get("/admin/api/ft/stats")
async def admin_ft_stats(
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    _verify_admin(token, x_admin_token)
    path = finetune_jsonl_resolved(settings)
    return {"path": str(path), "lines": count_lines(path), "exists": path.is_file()}


@app.get("/admin/api/ft/download")
async def admin_ft_download(
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """下载完整 JSONL，供拷贝到训练流水线。"""
    _verify_admin(token, x_admin_token)
    path = finetune_jsonl_resolved(settings)
    if not path.is_file():
        raise HTTPException(404, "尚无样本文件，请先 POST /admin/api/ft/sample 写入")
    return FileResponse(
        path,
        media_type="application/x-ndjson",
        filename="finetune_samples.jsonl",
    )


@app.get("/admin/api/meta")
async def admin_meta(
    token: str | None = Query(None),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """当前 Agent 协议与常用管理路径索引。"""
    _verify_admin(token, x_admin_token)
    return {
        "chat_protocol": (
            "POST /chat JSON；可选鉴权：CHAT_API_TOKEN 非空时须 X-Chat-Token 或 Authorization Bearer；"
            "模型侧为 action/tool 与 action/reply JSON（见 prompts.py）"
        ),
        "admin_pages": ["/admin"],
        "admin_api": [
            "GET /admin/api/tickets",
            "GET /admin/api/tools/registry",
            "POST /admin/api/ft/sample",
            "POST /admin/api/ft/from-session",
            "GET /admin/api/ft/stats",
            "GET /admin/api/ft/download",
        ],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    authorization: str | None = Header(None),
    x_chat_token: str | None = Header(None, alias="X-Chat-Token"),
):
    _verify_chat_api(authorization, x_chat_token)
    if http_client is None:
        raise HTTPException(503, "HTTP 客户端未初始化")

    sid = req.session_id or str(uuid.uuid4())
    store: MemorySessionStore = app.state.session_store
    if req.session_id and not store.has(sid):
        store.set(sid, [])
    if not req.session_id:
        store.set(sid, [])

    hist_payload = [h.model_dump() for h in req.history] if req.history else store.get(sid)

    conn = connect(db_file)
    try:
        try:
            reply, trace = await run_turn(
                http_client,
                settings,
                conn,
                req.message.strip(),
                hist_payload,
            )
        except Exception as e:  # noqa: BLE001
            # 让联调时可见具体错误原因；生产可改为结构化日志 + 通用错误码
            raise HTTPException(500, f"/chat 处理失败: {e}") from e
    finally:
        conn.close()

    if req.history is None:
        store.append_turn(sid, req.message, reply)

    return ChatResponse(
        reply=reply,
        session_id=sid,
        debug_trace=trace if req.debug else None,
    )
