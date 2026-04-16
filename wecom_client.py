from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class WeComApiError(RuntimeError):
    pass


@dataclass
class WeComClient:
    corpid: str
    agentid: int
    secret: str
    http: httpx.AsyncClient

    _token: str | None = None
    _token_expire_at: float = 0.0

    async def get_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expire_at:
            return self._token

        r = await self.http.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": self.corpid, "corpsecret": self.secret},
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise WeComApiError(f"gettoken 失败: {data}")
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise WeComApiError(f"gettoken 缺少 access_token: {data}")
        expires_in = int(data.get("expires_in") or 7200)
        self._token = token
        self._token_expire_at = now + max(60, expires_in - 120)
        return token

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self.get_access_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/" + path.lstrip("/")
        r = await self.http.post(url, params={"access_token": token}, json=payload, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise WeComApiError(f"{path} 失败: {data}")
        return data

    async def send_to_appchat(self, chatid: str, text: str) -> None:
        payload = {"chatid": chatid, "msgtype": "text", "text": {"content": text}}
        await self._post("appchat/send", payload)

    async def send_to_user(self, userid: str, text: str) -> None:
        payload = {
            "touser": userid,
            "agentid": self.agentid,
            "msgtype": "text",
            "text": {"content": text},
            "safe": 0,
        }
        await self._post("message/send", payload)

