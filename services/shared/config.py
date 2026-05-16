import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_consumer_group: str = "collections-engine"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "collections"
    postgres_password: str = "collections"
    postgres_db: str = "collections"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "collections"

    # OPA
    opa_url: str = "http://localhost:8181"

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Lakehouse (real AWS S3)
    lakehouse_s3_region: str = "us-east-1"
    lakehouse_bronze_bucket: str = ""
    lakehouse_silver_bucket: str = ""
    lakehouse_gold_bucket: str = ""
    lakehouse_flush_interval_s: int = 30
    lakehouse_flush_max_events: int = 500

    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def postgres_dsn_sync(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    model_config = {"env_prefix": "COLLECTIONS_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Lakehouse vars are NOT prefixed (they're standard AWS-style names). Bind
    # them directly from the environment so existing .env conventions work.
    for key in (
        "lakehouse_s3_region", "lakehouse_bronze_bucket", "lakehouse_silver_bucket",
        "lakehouse_gold_bucket", "lakehouse_flush_interval_s", "lakehouse_flush_max_events",
    ):
        env_val = os.environ.get(key.upper())
        if env_val is not None and env_val != "":
            current = getattr(s, key)
            if isinstance(current, int):
                try:
                    setattr(s, key, int(env_val))
                except ValueError:
                    pass
            else:
                setattr(s, key, env_val)
    return s
