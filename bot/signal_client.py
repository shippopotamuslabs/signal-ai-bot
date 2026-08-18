import logging
from typing import Any, Dict, List, Optional
import httpx

from config import settings

logger = logging.getLogger("signal_bot.signal_client")


class SignalClient:
    """Async client for interacting with signal-cli-rest-api."""

    def __init__(self, api_url: Optional[str] = None, phone_number: Optional[str] = None):
        self.api_url = (api_url or settings.SIGNAL_API_URL).rstrip("/")
        self.phone_number = phone_number or settings.SIGNAL_PHONE_NUMBER

    async def get_about(self) -> Dict[str, Any]:
        """Check signal-cli-rest-api status and version."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.api_url}/v1/about")
            resp.raise_for_status()
            return resp.json()

    async def send_message(
        self,
        message: str,
        recipients: Optional[List[str]] = None,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message back to a Signal recipient or group.
        `recipients` is a list of phone numbers or group IDs.
        """
        if not self.phone_number:
            logger.error("Cannot send message: SIGNAL_PHONE_NUMBER is not set in config.")
            return {"error": "SIGNAL_PHONE_NUMBER not configured"}

        target_recipients = recipients or []
        if group_id and group_id not in target_recipients:
            target_recipients.append(group_id)

        if not target_recipients:
            logger.error("Cannot send message: No recipient or group_id provided.")
            return {"error": "No recipients specified"}

        payload = {
            "message": message,
            "number": self.phone_number,
            "recipients": target_recipients,
        }

        logger.info(f"Sending message to {target_recipients} via {self.phone_number}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{self.api_url}/v2/send", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Signal API send error {e.response.status_code}: {e.response.text}")
            return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
        except Exception as e:
            logger.error(f"Failed to communicate with signal-cli API: {e}")
            return {"error": str(e)}

    async def register_number(self, phone_number: str, captcha: Optional[str] = None, voice: bool = False) -> Dict[str, Any]:
        """Request SMS or voice verification code for a phone number."""
        payload: Dict[str, Any] = {"use_voice": voice}
        if captcha:
            payload["captcha"] = captcha

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.api_url}/v1/register/{phone_number}", json=payload)
            resp.raise_for_status()
            return resp.json() if resp.text else {"status": "ok"}

    async def verify_number(self, phone_number: str, token: str, pin: Optional[str] = None) -> Dict[str, Any]:
        """Submit the SMS verification token (code) for a phone number."""
        payload: Dict[str, Any] = {}
        if pin:
            payload["pin"] = pin

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.api_url}/v1/register/{phone_number}/verify/{token}", json=payload)
            resp.raise_for_status()
            return resp.json() if resp.text else {"status": "verified"}

    async def list_groups(self) -> List[Dict[str, Any]]:
        """List groups the bot account belongs to."""
        if not self.phone_number:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.api_url}/v1/groups/{self.phone_number}")
            resp.raise_for_status()
            return resp.json()
