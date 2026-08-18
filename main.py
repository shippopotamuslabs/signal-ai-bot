import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from config import settings
from bot.handler import SignalMessageHandler

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("signal_bot.server")

app = FastAPI(
    title="Signal AI Bot Server",
    description="Webhook server for Signal AI group chat integration via OpenRouter",
    version="1.0.0",
)

# Global message handler instance
handler = SignalMessageHandler()


class SimulateMessageRequest(BaseModel):
    group_id: str = Field(default="family-group-1", description="Signal group ID or chat ID")
    sender_id: str = Field(default="+15559876543", description="Phone number or UUID of sender")
    sender_name: Optional[str] = Field(default="Sarah", description="Profile/Display name")
    message: str = Field(default="@AI what should we make for dinner with chicken and rice?", description="Text message")
    timestamp_offset_seconds: float = Field(default=0.0, description="Offset in seconds from now (positive is past)")


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Signal AI Bot Server",
        "trigger": settings.TRIGGER_PREFIX,
        "model": settings.OPENROUTER_MODEL,
    }


@app.get("/health")
async def health():
    has_key = bool(settings.OPENROUTER_API_KEY and settings.OPENROUTER_API_KEY != "your_openrouter_api_key_here")
    has_number = bool(settings.SIGNAL_PHONE_NUMBER and settings.SIGNAL_PHONE_NUMBER != "+15551234567")
    return {
        "status": "healthy",
        "openrouter_configured": has_key,
        "signal_number_configured": has_number,
        "model": settings.OPENROUTER_MODEL,
        "max_context": settings.MAX_CONTEXT_MESSAGES,
    }


@app.post("/webhook/signal")
async def signal_webhook(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Webhook endpoint invoked by signal-cli-rest-api on incoming messages.
    Processes asynchronously to acknowledge webhook quickly.
    """
    logger.debug(f"Received webhook payload: {payload}")
    
    # Process in background task so Signal daemon doesn't timeout
    background_tasks.add_task(handler.handle_incoming_payload, payload)
    return {"status": "received"}


@app.post("/api/simulate")
async def simulate_message(req: SimulateMessageRequest):
    """
    Simulate an incoming Signal message to test buffer memory and OpenRouter responses
    without needing an active Signal eSIM connection.
    """
    import time

    msg_time = time.time() - req.timestamp_offset_seconds
    mock_payload = {
        "envelope": {
            "source": req.sender_id,
            "sourceNumber": req.sender_id,
            "sourceName": req.sender_name,
            "timestamp": int(msg_time * 1000),
            "dataMessage": {
                "timestamp": int(msg_time * 1000),
                "message": req.message,
                "groupInfo": {
                    "groupId": req.group_id,
                    "type": "DELIVER",
                },
            },
        }
    }

    # Execute directly (synchronously for testing feedback)
    reply = await handler.handle_incoming_payload(mock_payload)
    history = handler.memory.get_history(req.group_id)

    return {
        "status": "processed",
        "received_message": req.message,
        "ai_reply": reply,
        "current_group_history": [
            {
                "sender": h.sender_name,
                "text": h.text,
                "is_bot": h.is_bot,
            }
            for h in history
        ],
    }


@app.get("/api/history/{group_id}")
async def get_group_history(group_id: str):
    """View rolling memory for a specific group."""
    history = handler.memory.get_history(group_id)
    return {
        "group_id": group_id,
        "message_count": len(history),
        "history": [
            {
                "sender": h.sender_name,
                "text": h.text,
                "timestamp": h.timestamp,
                "is_bot": h.is_bot,
            }
            for h in history
        ],
        "formatted_context": handler.memory.get_formatted_transcript(group_id),
    }


@app.post("/api/history/{group_id}/clear")
async def clear_group_history(group_id: str):
    """Clear memory buffer for a group."""
    handler.memory.clear(group_id)
    return {"status": "cleared", "group_id": group_id}
