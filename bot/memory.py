import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MessageRecord:
    sender_id: str
    sender_name: str
    text: str
    timestamp: float
    is_bot: bool = False

    def to_formatted_line(self) -> str:
        """Render for inclusion in conversation history."""
        speaker = "AI (You)" if self.is_bot else self.sender_name
        return f"{speaker}: {self.text}"


class GroupConversationBuffer:
    """
    Maintains a rolling window of recent messages for each Signal group / chat.
    Thread-safe and memory-bounded.
    """

    def __init__(self, max_messages: int = 10, name_map: Optional[Dict[str, str]] = None):
        self.max_messages = max_messages
        self.name_map = name_map or {}
        self._buffers: Dict[str, deque[MessageRecord]] = {}
        self._lock = threading.Lock()

    def resolve_sender_name(self, sender_id: str, profile_name: Optional[str] = None) -> str:
        """Resolve a sender to a friendly name from config, profile name, or masked ID."""
        if sender_id in self.name_map:
            return self.name_map[sender_id]
        if profile_name and profile_name.strip():
            return profile_name.strip()
        # Fallback to last 4 digits if phone number or short UUID
        if len(sender_id) > 6:
            return f"User (...{sender_id[-4:]})"
        return sender_id or "Family Member"

    def add_message(
        self,
        group_id: str,
        sender_id: str,
        text: str,
        profile_name: Optional[str] = None,
        timestamp: Optional[float] = None,
        is_bot: bool = False,
    ) -> MessageRecord:
        """Add a message to the group's rolling buffer."""
        sender_name = self.resolve_sender_name(sender_id, profile_name)
        ts = timestamp if timestamp is not None else time.time()

        record = MessageRecord(
            sender_id=sender_id,
            sender_name=sender_name,
            text=text.strip(),
            timestamp=ts,
            is_bot=is_bot,
        )

        with self._lock:
            if group_id not in self._buffers:
                self._buffers[group_id] = deque(maxlen=self.max_messages)
            self._buffers[group_id].append(record)

        return record

    def get_history(self, group_id: str) -> List[MessageRecord]:
        """Get copy of all messages in buffer for a group."""
        with self._lock:
            buf = self._buffers.get(group_id)
            if not buf:
                return []
            return list(buf)

    def get_formatted_transcript(self, group_id: str, exclude_last: bool = False) -> str:
        """
        Get a plaintext transcript of recent messages suitable for injection
        into LLM system / user prompt context.
        """
        history = self.get_history(group_id)
        if exclude_last and history:
            history = history[:-1]

        if not history:
            return "No previous messages in context."

        return "\n".join(record.to_formatted_line() for record in history)

    def clear(self, group_id: str) -> None:
        """Clear memory for a given group."""
        with self._lock:
            if group_id in self._buffers:
                self._buffers[group_id].clear()
