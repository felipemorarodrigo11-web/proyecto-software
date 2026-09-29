from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MAX_FILE_SIZE: int = Field(default=5 * 1024 * 1024, gt=0)
    DB_PATH: str = Field(default="db.json", min_length=1)
    DB_LOCK_TIMEOUT: float = Field(default=10, gt=0)

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
