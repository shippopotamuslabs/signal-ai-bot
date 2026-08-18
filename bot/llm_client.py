import logging
from typing import Optional
import httpx

from config import settings
from bot.memory import GroupConversationBuffer

logger = logging.getLogger("signal_bot.llm")


class OpenRouterClient:
    """Client for generating AI responses via OpenRouter API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL
        self.base_url = settings.OPENROUTER_BASE_URL

    async def generate_response(
        self,
        group_id: str,
        sender_name: str,
        user_prompt: str,
        memory: GroupConversationBuffer,
    ) -> str:
        """
        Generate an LLM response given the recent group history and current user prompt.
        """
        if not self.api_key or self.api_key == "your_openrouter_api_key_here":
            logger.warning("OpenRouter API key is missing or placeholder.")
            return "🤖 (Bot is active, but OpenRouter API key is not configured in .env yet!)"

        # Build context from rolling memory
        # Exclude the current triggering message if it's already in memory so it's not duplicated
        recent_context = memory.get_formatted_transcript(group_id, exclude_last=True)

        system_instruction = (
            f"{settings.SYSTEM_PROMPT}\n\n"
            "--- Recent Group Chat History (last messages for context) ---\n"
            f"{recent_context}\n"
            "--- End of History ---\n\n"
            f"The user '{sender_name}' is currently asking you the following question directly. "
            "Reply naturally to them and the group."
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"{sender_name}: {user_prompt}"},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/signal-ai-bot",
            "X-Title": "Signal AI Family Bot",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API HTTP error: {e.response.status_code} - {e.response.text}")
            return f"⚠️ Sorry, I encountered an error talking to AI service ({e.response.status_code})."
        except Exception as e:
            logger.error(f"Unexpected error calling OpenRouter: {e}", exc_info=True)
            return "⚠️ Sorry, I had trouble generating a response right now."
