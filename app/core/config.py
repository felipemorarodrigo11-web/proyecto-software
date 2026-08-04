from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MAX_FILE_SIZE: int = 5 * 1024 * 1024
    DB_PATH: str = "db.json"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()