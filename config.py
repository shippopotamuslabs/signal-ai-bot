import json
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # OpenRouter
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")
    OPENROUTER_MODEL: str = Field(default="anthropic/claude-3.5-sonnet", description="OpenRouter Model")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Signal
    SIGNAL_PHONE_NUMBER: str = Field(default="", description="Registered Signal phone number (+1...)")
    SIGNAL_API_URL: str = Field(default="http://localhost:8080", description="signal-cli-rest-api base URL")
    TRIGGER_PREFIX: str = Field(default="@AI", description="Prefix trigger for AI")
    MAX_CONTEXT_MESSAGES: int = Field(default=10, description="Rolling context window size")
    STALE_MESSAGE_THRESHOLD_SECONDS: int = Field(default=120, description="Ignore @AI triggers older than this")
    SYSTEM_PROMPT: str = Field(
        default="You are an unhinged, irreverent, witty, and hilarious but concise assistant operating" + 
        " in a no holds barred family group chat. You are aware of the conversation context." + 
        " Keep answers punchy, natural, and easy to read on mobile. Do not end replies with followups or engagement " +
        " farming shit like \"what's next?\" etc.",
        description="System prompt for the LLM",
    )
    FAMILY_NAME_MAP: Dict[str, str] = Field(default_factory=dict, description="Mapping of phone/UUID to friendly names")

    @field_validator("FAMILY_NAME_MAP", mode="before")
    @classmethod
    def parse_family_name_map(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return {}
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
