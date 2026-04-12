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
    # Отображаемое имя авто-модели в UI (список моделей Open WebUI)
    auto_model_display_name: str = Field(
        default="smart BAOBAB",
        validation_alias="GPTHUB_AUTO_MODEL_DISPLAY_NAME",
    )

    @field_validator("auto_model_display_name", mode="after")
    @classmethod
    def strip_quotes_auto_model_display_name(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
            return s[1:-1].strip()
        return s
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
    # Авторежим: выбор модели через один вызов LLM к MWS (иначе — правила pick_route_deterministic)
    router_use_llm: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_USE_LLM")
    router_llm_model: str = Field(default="mts-anya", validation_alias="GPTHUB_ROUTER_LLM_MODEL")
    # Если false — при сбое нейро-роутера не подставлять правила по ключевым словам, а вернуть 503
    router_rules_fallback: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_RULES_FALLBACK")


settings = Settings()
