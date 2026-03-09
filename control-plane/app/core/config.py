from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    # Gateways
    gateway_url: str = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080")

    # Redis configuration
    redis_host: str = os.getenv("REDIS_HOST", "10.12.58.42")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "123456")

    # Postgres configuration
    pg_host: str = "localhost"
    pg_port: str = "5432"
    pg_user: str = "postgres"
    pg_password: str = "123456"
    pg_db: str = "elevator_ad"

    # Snapshot handling
    snapshot_storage_dir: str = os.getenv("SNAPSHOT_STORAGE_DIR", "data/snapshots")
    snapshot_wait_timeout: int = int(os.getenv("SNAPSHOT_WAIT_TIMEOUT", "15"))

    # Toggle memory fallback for campaign endpoints when DB is unavailable.
    enable_memory_fallback: bool = os.getenv("ENABLE_MEMORY_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings()
