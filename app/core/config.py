from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FansOnly Backend"
    API_V1_PREFIX: str = "/api/v1"

    GCS_BUCKET_NAME: str = "onlyfats-private-media"

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_REFRESH_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    FIREBASE_PROJECT_ID: str = "onlyfats"
    FIREBASE_SA_KEY_PATH: str = ""  # optional path to service account JSON

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )
settings = Settings()