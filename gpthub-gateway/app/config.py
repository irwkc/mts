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

    log_level: str = Field(
        default="INFO",
        validation_alias="GPTHUB_LOG_LEVEL",
        description="Уровень логов шлюза: DEBUG, INFO, WARNING, ERROR",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: object) -> str:
        s = str(v or "INFO").strip().upper()
        if s in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            return s
        return "INFO"

    # Router / defaults (override via env after GET /v1/models on real deployment)
    auto_model_id: str = "gpthub-auto"
    # Отображаемое имя авто-модели в UI (список моделей Open WebUI)
    auto_model_display_name: str = Field(
        default="gena 2.0",
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
    asr_model: str = "whisper-medium"
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
    # gena — как gena/router select_model + перехваты; legacy — старые правила шлюза (llm → gena)
    router_mode: str = Field(default="gena", validation_alias="GPTHUB_ROUTER_MODE")
    gena_code_model: str = Field(
        default="qwen3-coder-480b-a35b",
        validation_alias="GPTHUB_GENA_CODE_MODEL",
    )
    gena_long_doc_model: str = Field(
        default="cotype-pro-vl-32b",
        validation_alias="GPTHUB_GENA_LONG_DOC_MODEL",
    )
    # Аналог mws-gpt-alpha в gena/router — «обычный диалог»
    gena_chat_model: str = Field(default="", validation_alias="GPTHUB_GENA_CHAT_MODEL")
    gena_long_doc_word_threshold: int = Field(
        default=600,
        validation_alias="GPTHUB_GENA_LONG_DOC_WORDS",
    )
    # Подмешивается в system: кто такой ассистент (пусто — отключить)
    gena_system_identity: str = Field(
        default=(
            "Идентичность: ты — gena 2.0, цифровой ассистент. "
            "На вопросы «кто ты», «как тебя зовут», «представься» отвечай кратко: "
            "ты gena (версия 2.0). Не выдумывай другое имя и не представляйся базовой моделью провайдера. "
            "В диалоге после генерации изображения, если пользователь просит правку (цвет, деталь, стиль), "
            "опирайся на последнее твоё сообщение с этой картинкой и не отвечай пустой ссылкой — "
            "уточни запрос или опиши изменение явно."
        ),
        validation_alias="GPTHUB_GENA_IDENTITY",
    )

    # Публичный URL шлюза для ссылок на /static/... (презентации). Пусто — берётся из заголовка запроса.
    public_base_url: str = Field(default="", validation_alias="GPTHUB_PUBLIC_BASE_URL")
    # ChromaDB (как в gena/router/memory.py); пустой host — отключено, только SQLite-память шлюза
    chroma_host: str = Field(default="", validation_alias="CHROMA_HOST")
    chroma_port: int = Field(default=8000, validation_alias="CHROMA_PORT")

    # Надёжность / производительность (не «безопасность»)
    mws_http_retries: int = Field(
        default=2,
        validation_alias="GPTHUB_MWS_HTTP_RETRIES",
        description="Повторы при 502/503/504/429 и таймауте (итого попыток = 1 + retries)",
    )
    mws_retry_backoff_sec: float = Field(
        default=1.0,
        validation_alias="GPTHUB_MWS_RETRY_BACKOFF_SEC",
    )
    web_search_cache_ttl_sec: float = Field(
        default=120.0,
        validation_alias="GPTHUB_WEB_SEARCH_CACHE_TTL_SEC",
    )
    web_search_cache_max_entries: int = Field(
        default=64,
        validation_alias="GPTHUB_WEB_SEARCH_CACHE_MAX_ENTRIES",
    )
    max_chat_payload_chars: int = Field(
        default=500_000,
        validation_alias="GPTHUB_MAX_CHAT_PAYLOAD_CHARS",
        description="Лимит размера тела chat/completions (JSON), защита от случайно огромных запросов",
    )
    gena_max_presentation_slides: int = Field(
        default=20,
        validation_alias="GPTHUB_MAX_PRESENTATION_SLIDES",
    )
    # Базовый PPTX для сборки (пусто — встроенный файл keynote_base.pptx). См. gena_pptx_use_bundled_template.
    gena_pptx_template_path: str = Field(
        default="",
        validation_alias="GPTHUB_PPTX_TEMPLATE_PATH",
    )
    # True — грузить app/assets/keynote_base.pptx (или кастомный шаблон). False — голый Presentation() (часто лучше для Keynote).
    gena_pptx_use_bundled_template: bool = Field(
        default=False,
        validation_alias="GPTHUB_PPTX_USE_BUNDLED_TEMPLATE",
    )
    # Второе сохранение через Presentation(path) — у PowerPoint иногда помогает; Keynote часто ломает импорт — по умолчанию выкл.
    gena_pptx_roundtrip: bool = Field(default=False, validation_alias="GPTHUB_PPTX_ROUNDTRIP")
    # Проверка ZIP/обязательных частей после записи.
    gena_pptx_validate_zip: bool = Field(default=True, validation_alias="GPTHUB_PPTX_VALIDATE_ZIP")
    # Длинная сторона картинки для встраивания (даунскейл при превышении).
    gena_pptx_max_image_px: int = Field(
        default=4096,
        validation_alias="GPTHUB_PPTX_MAX_IMAGE_PX",
    )

    @field_validator("gena_max_presentation_slides", mode="before")
    @classmethod
    def clamp_max_presentation_slides(cls, v: object) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 20
        return max(1, min(40, n))

    @field_validator("gena_pptx_max_image_px", mode="before")
    @classmethod
    def clamp_pptx_max_image_px(cls, v: object) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 4096
        return max(512, min(8192, n))

    @field_validator("router_mode", mode="before")
    @classmethod
    def normalize_router_mode(cls, v: object) -> str:
        s = str(v or "gena").strip().lower()
        if s == "llm":
            return "gena"
        if s in ("gena", "legacy"):
            return s
        return "gena"


settings = Settings()
