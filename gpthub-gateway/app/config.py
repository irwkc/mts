from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
    )

    mws_api_base: str = "https://api.gpt.mws.ru/v1"
    mws_api_key: str = ""

    data_dir: Path = Path("/data")

    @field_validator("data_dir", mode="before")
    @classmethod
    def parse_data_dir(cls, v: object) -> Path:
        if v is None or v == "":
            return Path("/data")
        return Path(str(v))

    # Router / defaults (override via env after GET /v1/models on real deployment)
    auto_model_id: str = "gpthub-auto"
    default_llm: str = "mts-anya"
    vision_model: str = "gpt-4o"
    image_gen_model: str = "qwen-image"
    asr_model: str = "whisper-large-v3"
    embedding_model: str = "bge-m3"

    memory_top_k: int = 5
    rag_top_k: int = 5
    chunk_size: int = 900
    chunk_overlap: int = 120

    # Префикс [GPTHub route: …] в system при true (демо / отладка)
    router_debug: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_DEBUG")


settings = Settings()
