from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(RuntimeError):
    pass


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    parts = [token, timestamp, nonce, encrypt]
    parts.sort()
    raw = "".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes, block_size: int = 32) -> bytes:
    if not data or len(data) % block_size != 0:
        raise WeComCryptoError("PKCS7 数据长度非法")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise WeComCryptoError("PKCS7 padding 非法")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise WeComCryptoError("PKCS7 padding 校验失败")
    return data[:-pad_len]


def _aes_key_from_encoding_aes_key(encoding_aes_key: str) -> bytes:
    key = (encoding_aes_key or "").strip()
    if not key:
        raise WeComCryptoError("缺少 EncodingAESKey（WECOM_AES_KEY）")
    try:
        return base64.b64decode(key + "=", validate=False)
    except Exception as e:  # noqa: BLE001
        raise WeComCryptoError(f"EncodingAESKey base64 解码失败: {e}") from e


def _aes_cbc_encrypt(key: bytes, plaintext: bytes) -> bytes:
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(plaintext) + enc.finalize()


def _aes_cbc_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    return dec.update(ciphertext) + dec.finalize()


@dataclass(frozen=True)
class WeComCrypto:
    token: str
    encoding_aes_key: str
    corp_id: str

    _block_size: Final[int] = 32

    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> None:
        expected = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if (msg_signature or "").strip() != expected:
            raise WeComCryptoError("签名校验失败（msg_signature 不匹配）")

    def decrypt(self, encrypt_b64: str) -> str:
        key = _aes_key_from_encoding_aes_key(self.encoding_aes_key)
        try:
            cipher_bytes = base64.b64decode(encrypt_b64)
        except Exception as e:  # noqa: BLE001
            raise WeComCryptoError(f"Encrypt base64 解码失败: {e}") from e

        plain_padded = _aes_cbc_decrypt(key, cipher_bytes)
        plain = _pkcs7_unpad(plain_padded, self._block_size)
        if len(plain) < 16 + 4:
            raise WeComCryptoError("解密后数据长度不足")

        msg_len = struct.unpack("!I", plain[16:20])[0]
        msg = plain[20 : 20 + msg_len]
        corp = plain[20 + msg_len :].decode("utf-8", errors="ignore")
        if self.corp_id and corp != self.corp_id:
            raise WeComCryptoError("CorpID 校验失败（解密得到的 corp_id 不匹配）")
        return msg.decode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        key = _aes_key_from_encoding_aes_key(self.encoding_aes_key)
        msg = plaintext.encode("utf-8")
        corp = (self.corp_id or "").encode("utf-8")
        rand16 = os.urandom(16)
        msg_len = struct.pack("!I", len(msg))
        raw = rand16 + msg_len + msg + corp
        padded = _pkcs7_pad(raw, self._block_size)
        cipher = _aes_cbc_encrypt(key, padded)
        return base64.b64encode(cipher).decode("utf-8")

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        self.verify_signature(msg_signature, timestamp, nonce, echostr)
        return self.decrypt(echostr)

    def build_encrypted_response_xml(self, encrypt_b64: str, nonce: str | None = None) -> str:
        ts = str(int(time.time()))
        nonce2 = nonce or base64.b64encode(os.urandom(8)).decode("utf-8").strip("=")
        sig = _sha1_signature(self.token, ts, nonce2, encrypt_b64)
        return (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypt_b64}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{sig}]]></MsgSignature>"
            f"<TimeStamp>{ts}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce2}]]></Nonce>"
            "</xml>"
        )

