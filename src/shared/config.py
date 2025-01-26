from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    database_url: str = "postgresql://changeme:updatethis@localhost/bluesky_feed"
    # in practice we seem to flush 250 about every 3 seconds
    batch_size: int = 100
    flush_interval_seconds: int = 10
    jetstream_uri: str = "wss://jetstream2.us-east.bsky.network/subscribe"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    def __init__(self, **kwargs):
        logger.info(f"Loading settings from env file: {self.model_config['env_file']}")
        super().__init__(**kwargs)


settings = Settings()
