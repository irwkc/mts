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

    memory_top_k: int = 8
    rag_top_k: int = 5
    chunk_size: int = 900
    chunk_overlap: int = 120

    # Память в духе OpenClaw: факты через LLM + лимит строк в SQLite
    memory_max_items_per_user: int = Field(
        default=400, validation_alias="GPTHUB_MEMORY_MAX_ITEMS"
    )
    memory_llm_digest: bool = Field(
        default=True,
        validation_alias="GPTHUB_MEMORY_LLM_DIGEST",
        description="После ответа извлекать 0..N фактов отдельным вызовом LLM",
    )
    memory_digest_model: str = Field(
        default="mts-anya",
        validation_alias="GPTHUB_MEMORY_DIGEST_MODEL",
    )
    memory_raw_fallback: bool = Field(
        default=False,
        validation_alias="GPTHUB_MEMORY_RAW_FALLBACK",
        description="Если digest пуст — всё равно сохранять сырой обмен (шумнее)",
    )
    # Длинные диалоги: сжать «голову» переписки в сводку (дороже по токенам)
    memory_compress_enabled: bool = Field(
        default=False,
        validation_alias="GPTHUB_MEMORY_COMPRESS_CONTEXT",
    )
    memory_compress_after_messages: int = Field(
        default=36,
        validation_alias="GPTHUB_MEMORY_COMPRESS_AFTER",
    )
    memory_compress_keep_last: int = Field(
        default=16,
        validation_alias="GPTHUB_MEMORY_COMPRESS_KEEP",
    )

    # Префикс [GPTHub route: …] в system при true (демо / отладка)
    router_debug: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_DEBUG")
    # Авторежим: выбор модели через один вызов LLM к MWS (иначе — правила pick_route_deterministic)
    router_use_llm: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_USE_LLM")
    router_llm_model: str = Field(default="mts-anya", validation_alias="GPTHUB_ROUTER_LLM_MODEL")
    # Локальный нейро-роутер (OpenAI-compatible: Ollama :11434/v1, llama-server и т.д.) — без MWS
    router_local_base_url: str = Field(
        default="",
        validation_alias="GPTHUB_ROUTER_LOCAL_BASE_URL",
    )
    router_local_model: str = Field(
        default="qwen2.5:0.5b",
        validation_alias="GPTHUB_ROUTER_LOCAL_MODEL",
    )
    router_local_api_key: str = Field(
        default="",
        validation_alias="GPTHUB_ROUTER_LOCAL_API_KEY",
    )
    # Если false — при сбое нейро-роутера не подставлять правила по ключевым словам, а вернуть 503
    router_rules_fallback: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_RULES_FALLBACK")


settings = Settings()
