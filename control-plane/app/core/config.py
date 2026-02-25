from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    # Gateways
    gateway_url: str = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080")
    
    # --- Redis Configuration (新增) ---
    # 必须与 Go 网关连接同一个 Redis，才能实现 Token 共享
    redis_host: str = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    
    pg_host: str = "localhost"
    pg_port: str = "5432"
    pg_user: str = "postgres"
    pg_password: str = "123456"
    pg_db: str = "elevator_ad"
    
    # Snapshot handling
    # --- Snapshot handling ---
    # 截图保存目录（虽然 Go 传了 OSS，但 Python 也可以选择下载一份做备份）
    snapshot_storage_dir: str = os.getenv("SNAPSHOT_STORAGE_DIR", "data/snapshots")
    # 等待电梯端通过 Go 网关回调的超时时间（建议设为 15-30 秒，因为包含网络往返）
    snapshot_wait_timeout: int = int(os.getenv("SNAPSHOT_WAIT_TIMEOUT", "15"))

    # --- 环境变量配置 ---
    class Config:
        env_file = ".env" # 允许从 .env 文件读取变量
        case_sensitive = False
settings = Settings()
