from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    results_channel: str
    webapp_url: str
    database_url: str = "sqlite+aiosqlite:///./battles.db"
    admin_ids: str = ""

    # --- Банк через Business Bot API (если Telegram снимет ограничение) ---
    bank_business_connection_id: str = ""
    bank_username: str = ""
    bank_sync_interval: int = 20

    # --- Банк через MTProto user-сессию (обход ограничения gifts) ---
    api_id: str = ""
    api_hash: str = ""
    bank_session: str = ""  # Telethon StringSession

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def use_user_bank(self) -> bool:
        return bool(self.api_id and self.api_hash and self.bank_session)


settings = Settings()
