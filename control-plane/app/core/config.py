from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    # Gateways
    gateway_url: str = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080")

    # Snapshot handling
    snapshot_storage_dir: str = os.getenv("SNAPSHOT_STORAGE_DIR", ".data/snapshots")
    snapshot_wait_timeout: int = int(os.getenv("SNAPSHOT_WAIT_TIMEOUT", "10"))


settings = Settings()
