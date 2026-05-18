from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOVA_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"

    # LLM
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    model: str = "claude-sonnet-4-6"
    hard_model: str = "claude-opus-4-7"
    max_tokens: int = 1024
    system_prompt_path: str = "prompts/system.md"
    opus_triggers: list[str] = [
        "think hard",
        "think harder",
        "use opus",
        "deep think",
        "analyze deeply",
    ]

    # Memory (Phase 4)
    data_dir: str = "data"
    db_path: str = "data/nova.sqlite"
    chroma_path: str = "data/chroma"
    memory_top_k: int = 5
    memory_max_recent_turns: int = 20

    # File operations (Phase 5)
    file_root: str = str(Path.home())          # ops are confined to this tree by default
    allow_destructive: bool = False            # if False, delete requires explicit confirm:true
    downloads_dir: str = str(Path.home() / "Downloads")

    # Telegram
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")

    # Google Drive
    google_credentials_file: str = "data/google_credentials.json"
    google_token_file: str = "data/google_token.json"

    # Canva
    canva_client_id: str | None = Field(default=None, validation_alias="NOVA_CANVA_CLIENT_ID")
    canva_client_secret: str | None = Field(default=None, validation_alias="NOVA_CANVA_CLIENT_SECRET")
    canva_token_file: str = "data/canva_token.json"

    # Web (Phase 5)
    web_user_agent: str = "Nova/0.1 (+https://anthropic.com)"
    web_timeout_s: float = 15.0
    web_max_chars: int = 8000

    # Voice
    wake_word: str = "hey_nova"
    stt_backend: str = "faster-whisper"
    tts_backend: str = "piper"

    def ensure_data_dir(self) -> None:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)


settings = Settings()
