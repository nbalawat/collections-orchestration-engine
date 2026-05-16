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

    @property
    def postgres_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def postgres_dsn_sync(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    model_config = {"env_prefix": "COLLECTIONS_", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
