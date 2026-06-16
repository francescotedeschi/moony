from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    musixmatch_api_key: str = ""
    jamendo_client_id: str = ""
    catalog_path: str = "catalog/catalog.json"
    cors_origins: str = "http://localhost:5173"
    database_url: str = "postgresql+psycopg://moony:moony@localhost:5432/moony"

    # In-memory subtitle cache (session-only, not Musixmatch catalog storage)
    lyrics_cache_ttl_seconds: int = 600
    lyrics_cache_max_entries: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
