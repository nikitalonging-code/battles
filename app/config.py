from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    results_channel: str
    webapp_url: str
    database_url: str = "sqlite+aiosqlite:///./battles.db"
    admin_ids: str = ""

    # Банк подарков: business_connection_id аккаунта, на который кидают NFT
    bank_business_connection_id: str = ""
    # Username банка без @ — показывается пользователям («отправьте подарок @xxx»)
    bank_username: str = ""

    # Интервал опроса новых подарков в банке (секунды)
    bank_sync_interval: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]


settings = Settings()
