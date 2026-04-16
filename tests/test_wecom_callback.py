from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

import app as app_mod
from wecom_crypto import WeComCrypto


def _sig(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    parts = [token, timestamp, nonce, encrypt]
    parts.sort()
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def test_wecom_get_verify_ok(monkeypatch) -> None:
    # patch settings (module-level singleton)
    s = app_mod.settings
    s.wecom_corp_id = "ww123"
    s.wecom_token = "tok"
    s.wecom_aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"

    crypto = WeComCrypto(token=s.wecom_token, encoding_aes_key=s.wecom_aes_key, corp_id=s.wecom_corp_id)
    echostr = crypto.encrypt("hi")
    ts = "1710000000"
    nonce = "n1"
    sig = _sig(s.wecom_token, ts, nonce, echostr)

    with TestClient(app_mod.app) as client:
        r = client.get(
            "/wecom/callback",
            params={"msg_signature": sig, "timestamp": ts, "nonce": nonce, "echostr": echostr},
        )
        assert r.status_code == 200
        assert r.text == "hi"


def test_wecom_post_ack_success(monkeypatch) -> None:
    s = app_mod.settings
    s.wecom_corp_id = "ww123"
    s.wecom_token = "tok"
    s.wecom_aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"

    crypto = WeComCrypto(token=s.wecom_token, encoding_aes_key=s.wecom_aes_key, corp_id=s.wecom_corp_id)
    plain = (
        "<xml>"
        "<ToUserName><![CDATA[toUser]]></ToUserName>"
        "<FromUserName><![CDATA[fromUser]]></FromUserName>"
        "<CreateTime>1348831860</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[hello]]></Content>"
        "<MsgId>123456</MsgId>"
        "</xml>"
    )
    enc = crypto.encrypt(plain)
    body = f"<xml><Encrypt><![CDATA[{enc}]]></Encrypt></xml>"
    ts = "1710000001"
    nonce = "n2"
    sig = _sig(s.wecom_token, ts, nonce, enc)

    with TestClient(app_mod.app) as client:
        r = client.post(
            "/wecom/callback",
            params={"msg_signature": sig, "timestamp": ts, "nonce": nonce},
            content=body.encode("utf-8"),
            headers={"Content-Type": "text/xml"},
        )
        assert r.status_code == 200
        assert r.text.strip() == "success"

