from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryMessage:
    role: str
    content: List[Dict[str, Any]] = field(default_factory=list)


class ConversationMemory(ABC):
    @abstractmethod
    def get_history(self, conversation_id: str) -> List[MemoryMessage]:
        ...

    @abstractmethod
    def append_message(self, conversation_id: str, message: MemoryMessage) -> None:
        ...

    @abstractmethod
    def get_state(self, conversation_id: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_state(self, conversation_id: str, new_state: Dict[str, Any]) -> None:
        ...


class InMemoryConversationMemory(ConversationMemory):
    """
    Simple in-process memory with optional state and max message cap.
    """

    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self._messages: Dict[str, List[MemoryMessage]] = {}
        self._state: Dict[str, Dict[str, Any]] = {}

    def get_history(self, conversation_id: str) -> List[MemoryMessage]:
        return list(self._messages.get(conversation_id, []))

    def append_message(self, conversation_id: str, message: MemoryMessage) -> None:
        history = self._messages.get(conversation_id, [])
        history.append(message)
        # Trim to last N messages to avoid unbounded growth.
        if len(history) > self.max_messages:
            history = history[-self.max_messages :]
        self._messages[conversation_id] = history

    def get_state(self, conversation_id: str) -> Dict[str, Any]:
        return dict(self._state.get(conversation_id, {}))

    def update_state(self, conversation_id: str, new_state: Dict[str, Any]) -> None:
        current = self._state.get(conversation_id, {})
        current.update(new_state)
        self._state[conversation_id] = current


def to_claude_messages(history: List[MemoryMessage]) -> List[Dict[str, Any]]:
    """
    Convert stored MemoryMessage objects into Claude messages payload.
    """
    claude_msgs: List[Dict[str, Any]] = []
    for msg in history:
        claude_msgs.append({"role": msg.role, "content": msg.content})
    return claude_msgs
