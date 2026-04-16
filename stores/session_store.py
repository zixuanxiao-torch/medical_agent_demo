from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemorySessionStore:
    """进程内会话存储（适合本机演示）。

    后续接入 Redis 时只需替换本类实现，不影响 agent / channel 逻辑。
    """

    _sessions: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    max_msgs: int = 40

    def get(self, session_id: str) -> list[dict[str, str]]:
        return list(self._sessions.get(session_id, []))

    def set(self, session_id: str, history: list[dict[str, str]]) -> None:
        self._sessions[session_id] = list(history)[-self.max_msgs :]

    def append_turn(self, session_id: str, user_text: str, assistant_text: str) -> None:
        hist = self._sessions.setdefault(session_id, [])
        hist.append({"role": "user", "content": user_text})
        hist.append({"role": "assistant", "content": assistant_text})
        self._sessions[session_id] = hist[-self.max_msgs :]

    def has(self, session_id: str) -> bool:
        return session_id in self._sessions

