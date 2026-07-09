"""Tests for agent session management."""

from mbforge.agent.sessions import AgentSession, ChatMessage, session_store


class TestChatMessage:
    def test_create_message(self):
        msg = ChatMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"


class TestAgentSession:
    def test_create_session(self):
        s = AgentSession(session_id="test-123")
        assert s.session_id == "test-123"
        assert s.messages == []


class TestSessionStore:
    def setup_method(self):
        session_store.clear_all()

    def test_create_and_get(self):
        s = session_store.create("s1")
        assert s.session_id == "s1"
        got = session_store.get("s1")
        assert got is s

    def test_get_nonexistent_returns_none(self):
        assert session_store.get("nonexistent") is None

    def test_delete(self):
        session_store.create("to-delete")
        session_store.delete("to-delete")
        assert session_store.get("to-delete") is None

    def test_clear_messages(self):
        s = session_store.create("s1")
        s.messages.append(ChatMessage(role="user", content="hi"))
        session_store.clear("s1")
        assert len(s.messages) == 0

    def test_list_sessions(self):
        session_store.create("a")
        session_store.create("b")
        ids = session_store.list_sessions()
        assert "a" in ids
        assert "b" in ids
