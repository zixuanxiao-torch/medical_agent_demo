from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from wecom_crypto import WeComCrypto, WeComCryptoError


def _sig(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    import hashlib

    parts = [token, timestamp, nonce, encrypt]
    parts.sort()
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def test_encrypt_decrypt_roundtrip() -> None:
    # 43 位 EncodingAESKey（示例值，仅用于单测），base64 解码后应为 32 bytes
    aes = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    c = WeComCrypto(token="t", encoding_aes_key=aes, corp_id="ww123")
    plain = "<xml><Test>ok</Test></xml>"
    enc = c.encrypt(plain)
    got = c.decrypt(enc)
    assert got == plain


def test_verify_url_ok() -> None:
    aes = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    token = "token1"
    c = WeComCrypto(token=token, encoding_aes_key=aes, corp_id="ww123")
    echostr = c.encrypt("hello")
    ts = "1710000000"
    nonce = "n1"
    sig = _sig(token, ts, nonce, echostr)
    assert c.verify_url(sig, ts, nonce, echostr) == "hello"


def test_verify_signature_bad() -> None:
    aes = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    c = WeComCrypto(token="t", encoding_aes_key=aes, corp_id="ww123")
    enc = c.encrypt("x")
    with pytest.raises(WeComCryptoError, match="签名校验失败"):
        c.verify_signature("bad", "1", "2", enc)


def test_build_response_xml_shape() -> None:
    aes = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    c = WeComCrypto(token="t", encoding_aes_key=aes, corp_id="ww123")
    enc = c.encrypt("<xml/>")
    xml = c.build_encrypted_response_xml(enc, nonce="abc")
    root = ET.fromstring(xml)
    assert root.findtext("Encrypt") is not None
    assert root.findtext("MsgSignature") is not None
    assert root.findtext("TimeStamp") is not None
    assert root.findtext("Nonce") is not None

