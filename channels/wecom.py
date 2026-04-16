from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from agent import run_turn
from db import connect
from stores.session_store import MemorySessionStore
from wecom_client import WeComClient
from wecom_crypto import WeComCrypto, WeComCryptoError


router = APIRouter()


def _wecom_crypto(settings) -> WeComCrypto:
    if not settings.wecom_token or not settings.wecom_aes_key:
        raise HTTPException(500, "企业微信回调未配置：请在 .env 设置 WECOM_TOKEN / WECOM_AES_KEY")
    if not settings.wecom_corp_id:
        raise HTTPException(500, "企业微信回调未配置：请在 .env 设置 WECOM_CORP_ID")
    return WeComCrypto(
        token=settings.wecom_token.strip(),
        encoding_aes_key=settings.wecom_aes_key.strip(),
        corp_id=settings.wecom_corp_id.strip(),
    )


def _xml_text(root: ET.Element, tag: str) -> str:
    el = root.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_wecom_plain_xml(plain_xml: str) -> dict[str, Any]:
    root = ET.fromstring(plain_xml)
    msg_type = _xml_text(root, "MsgType")
    out: dict[str, Any] = {
        "msg_type": msg_type,
        "from_user": _xml_text(root, "FromUserName"),
        "to_user": _xml_text(root, "ToUserName"),
        "chat_type": _xml_text(root, "ChatType"),
        "chat_id": _xml_text(root, "ChatId"),
        "msg_id": _xml_text(root, "MsgId") or _xml_text(root, "MsgID"),
        "content": _xml_text(root, "Content"),
    }

    mentioned: list[str] = []
    ml = root.find("MentionedList")
    if ml is not None:
        for it in list(ml.findall("Item")):
            if it.text:
                mentioned.append(it.text.strip())
    out["mentioned_list"] = mentioned
    return out


def _wecom_should_reply(settings, event: dict[str, Any]) -> bool:
    if not settings.wecom_only_reply_when_mentioned:
        return True
    if event.get("mentioned_list"):
        return True
    content = (event.get("content") or "").lstrip()
    return content.startswith("@")


def _wecom_dedup_seen(wecom_seen: dict[str, float], key: str, ttl_sec: int = 300) -> bool:
    now = time.time()
    if wecom_seen:
        expire_before = now - ttl_sec
        for k, t in list(wecom_seen.items()):
            if t < expire_before:
                wecom_seen.pop(k, None)
    if key in wecom_seen:
        return False
    wecom_seen[key] = now
    return True


async def _handle_event(request: Request, event: dict[str, Any]) -> None:
    st = request.app.state
    http_client = getattr(st, "http_client", None)
    settings = getattr(st, "settings", None)
    db_file = getattr(st, "db_file", None)
    sessions: MemorySessionStore | None = getattr(st, "session_store", None)
    wecom_seen: dict[str, float] | None = getattr(st, "wecom_seen", None)

    if http_client is None or settings is None or db_file is None or sessions is None or wecom_seen is None:
        return
    if not settings.wecom_corp_id or not settings.wecom_secret or not settings.wecom_agent_id:
        return

    msg_type = event.get("msg_type")
    content = (event.get("content") or "").strip()
    from_user = (event.get("from_user") or "").strip()
    chat_id = (event.get("chat_id") or "").strip()
    msg_id = (event.get("msg_id") or "").strip()

    if msg_type != "text" or not content:
        return
    if event.get("chat_type") == "groupchat" and not _wecom_should_reply(settings, event):
        return

    dedup_key = f"{event.get('chat_type')}:{chat_id}:{from_user}:{msg_id}:{content[:120]}"
    if not _wecom_dedup_seen(wecom_seen, dedup_key):
        return

    # 会话映射：群聊按用户隔离；单聊按用户隔离
    sid = f"wecom:{settings.wecom_corp_id}:{chat_id or 'direct'}:{from_user or 'unknown'}"
    history = sessions.get(sid)

    conn = connect(db_file)
    try:
        reply, _trace = await run_turn(
            http_client,
            settings,
            conn,
            content,
            history=history,
        )
    finally:
        conn.close()

    sessions.append_turn(sid, content, reply)

    client = WeComClient(
        corpid=settings.wecom_corp_id.strip(),
        agentid=int(settings.wecom_agent_id),
        secret=settings.wecom_secret.strip(),
        http=http_client,
    )
    try:
        if chat_id:
            await client.send_to_appchat(chat_id, reply)
        elif from_user:
            await client.send_to_user(from_user, reply)
    except Exception:
        return


@router.get("/wecom/callback", response_class=PlainTextResponse)
async def wecom_callback_get(
    request: Request,
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    settings = request.app.state.settings
    try:
        plain = _wecom_crypto(settings).verify_url(msg_signature, timestamp, nonce, echostr)
    except WeComCryptoError as e:
        raise HTTPException(403, str(e)) from e
    return plain


@router.post("/wecom/callback", response_class=PlainTextResponse)
async def wecom_callback_post(
    request: Request,
    background: BackgroundTasks,
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    settings = request.app.state.settings
    body = (await request.body()).decode("utf-8", errors="ignore")
    try:
        root = ET.fromstring(body)
        encrypt = _xml_text(root, "Encrypt")
        if not encrypt:
            raise HTTPException(400, "缺少 Encrypt")
        crypto = _wecom_crypto(settings)
        crypto.verify_signature(msg_signature, timestamp, nonce, encrypt)
        plain_xml = crypto.decrypt(encrypt)
        event = _parse_wecom_plain_xml(plain_xml)
    except WeComCryptoError as e:
        raise HTTPException(403, str(e)) from e
    except ET.ParseError as e:
        raise HTTPException(400, f"XML 解析失败: {e}") from e

    background.add_task(_handle_event, request, event)
    return "success"

