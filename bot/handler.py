import logging
import time
from typing import Any, Dict, Optional, Tuple
from config import settings
from bot.memory import GroupConversationBuffer
from bot.llm_client import OpenRouterClient
from bot.signal_client import SignalClient

logger = logging.getLogger("signal_bot.handler")


class SignalMessageHandler:
    """Coordinates parsing, buffering, trigger detection, LLM generation, and dispatch."""

    def __init__(
        self,
        memory: Optional[GroupConversationBuffer] = None,
        llm_client: Optional[OpenRouterClient] = None,
        signal_client: Optional[SignalClient] = None,
    ):
        self.memory = memory or GroupConversationBuffer(
            max_messages=settings.MAX_CONTEXT_MESSAGES,
            name_map=settings.FAMILY_NAME_MAP,
        )
        self.llm = llm_client or OpenRouterClient()
        self.signal = signal_client or SignalClient()

    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract standardized message information from signal-cli-rest-api webhook payload.
        Handles variations in payload structure.
        """
        envelope = payload.get("envelope", payload)
        data_message = envelope.get("dataMessage")

        if not data_message:
            # Not a standard text message (could be a receipt, typing indicator, syncMessage, etc.)
            # Check for syncMessage (sent by the bot from another client)
            sync_message = envelope.get("syncMessage", {}).get("sentMessage")
            if sync_message:
                data_message = sync_message
            else:
                return None

        text = data_message.get("message")
        if not text:
            return None

        # Sender identity
        sender_id = (
            envelope.get("sourceNumber")
            or envelope.get("sourceUuid")
            or envelope.get("source")
            or "Unknown"
        )
        sender_name = envelope.get("sourceName")

        # Timestamp (Signal uses milliseconds)
        raw_ts = data_message.get("timestamp") or envelope.get("timestamp")
        msg_timestamp = (raw_ts / 1000.0) if raw_ts else time.time()

        # Group Info
        group_info = data_message.get("groupInfo") or {}
        group_id = group_info.get("groupId")

        # If no group_id, this is a direct 1-on-1 message
        target_chat_id = group_id if group_id else sender_id
        is_group = bool(group_id)

        # Check if the message came from the bot's own number to prevent self-trigger loop
        is_from_bot = (
            settings.SIGNAL_PHONE_NUMBER
            and (sender_id == settings.SIGNAL_PHONE_NUMBER or envelope.get("sourceNumber") == settings.SIGNAL_PHONE_NUMBER)
        )

        return {
            "text": text,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "timestamp": msg_timestamp,
            "chat_id": target_chat_id,
            "is_group": is_group,
            "is_from_bot": is_from_bot,
        }

    def is_triggered(self, text: str) -> Tuple[bool, str]:
        """
        Check if the text begins with the trigger prefix (e.g. '@AI').
        Returns (is_triggered, cleaned_prompt).
        """
        cleaned = text.strip()
        prefix = settings.TRIGGER_PREFIX.strip()

        # Case-insensitive prefix check
        if cleaned.lower().startswith(prefix.lower()):
            # Strip the trigger word
            prompt = cleaned[len(prefix):].strip()
            # If user just wrote "@AI", provide a fallback query prompt
            if not prompt:
                prompt = "Hello! How can I help you and the family today?"
            return True, prompt

        return False, ""

    def is_stale(self, msg_timestamp: float) -> bool:
        """Check if message was sent too long ago (e.g. while laptop was offline)."""
        age_seconds = time.time() - msg_timestamp
        return age_seconds > settings.STALE_MESSAGE_THRESHOLD_SECONDS

    async def handle_incoming_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """Main processing pipeline for incoming webhook events."""
        parsed = self.parse_webhook_payload(payload)
        if not parsed:
            return None

        text = parsed["text"]
        sender_id = parsed["sender_id"]
        sender_name = parsed["sender_name"]
        chat_id = parsed["chat_id"]
        msg_timestamp = parsed["timestamp"]
        is_from_bot = parsed["is_from_bot"]

        # If it was sent by our bot, just store it in context and return
        if is_from_bot:
            self.memory.add_message(
                group_id=chat_id,
                sender_id=sender_id,
                text=text,
                profile_name=sender_name,
                timestamp=msg_timestamp,
                is_bot=True,
            )
            return None

        # 1. Add incoming user message to rolling conversation buffer
        record = self.memory.add_message(
            group_id=chat_id,
            sender_id=sender_id,
            text=text,
            profile_name=sender_name,
            timestamp=msg_timestamp,
            is_bot=False,
        )

        # 2. Check if message triggers the AI
        triggered, user_prompt = self.is_triggered(text)
        if not triggered:
            logger.debug(f"Message in {chat_id} received, no @AI trigger: {text[:40]}...")
            return None

        logger.info(f"Triggered by {record.sender_name} in {chat_id}: '{user_prompt}'")

        # 3. Staleness check
        if self.is_stale(msg_timestamp):
            age_sec = int(time.time() - msg_timestamp)
            logger.warning(
                f"Skipping LLM reply: message is {age_sec}s old (> {settings.STALE_MESSAGE_THRESHOLD_SECONDS}s threshold)."
            )
            return None

        # 4. Generate AI reply via OpenRouter
        ai_reply = await self.llm.generate_response(
            group_id=chat_id,
            sender_name=record.sender_name,
            user_prompt=user_prompt,
            memory=self.memory,
        )

        # 5. Record bot reply into buffer so future messages have context of the answer
        self.memory.add_message(
            group_id=chat_id,
            sender_id=settings.SIGNAL_PHONE_NUMBER or "bot",
            text=ai_reply,
            profile_name="AI",
            is_bot=True,
        )

        # 6. Send reply back to Signal
        await self.signal.send_message(
            message=ai_reply,
            recipients=[chat_id] if not parsed["is_group"] else None,
            group_id=chat_id if parsed["is_group"] else None,
        )

        return ai_reply
