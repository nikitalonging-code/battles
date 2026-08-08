from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    results_channel: str
    webapp_url: str
    database_url: str = "sqlite+aiosqlite:///./battles.db"
    admin_ids: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]


settings = Settings()
