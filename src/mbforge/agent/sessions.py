"""In-memory session store for agent conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str  # user, assistant, system
    content: str
    name: str = ""


@dataclass
class AgentSession:
    session_id: str
    library_root: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)
    agent: Any = None
    llm: Any = None


class SessionStore:
    """In-memory session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def create(self, session_id: str, library_root: str | None = None) -> AgentSession:
        session = AgentSession(session_id=session_id, library_root=library_root)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def clear(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.messages.clear()

    def clear_all(self) -> None:
        self._sessions.clear()

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())


# Global singleton
session_store = SessionStore()
