from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = Field(default="")

    # LLM
    llm_api_key: str = Field(default="")
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_model_name: str = Field(default="gpt-4o-mini")

    # Notion
    notion_enabled: bool = Field(default=False)
    notion_api_key: str = Field(default="")
    notion_database_id: str = Field(default="")

    # Context
    max_context_turns: int = Field(default=10)
    context_expire_minutes: int = Field(default=30)

    # Logging
    log_level: str = Field(default="INFO")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
