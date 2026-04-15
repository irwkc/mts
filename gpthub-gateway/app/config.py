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

    log_level: str = Field(default="INFO", validation_alias="GPTHUB_LOG_LEVEL")

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: object) -> str:
        s = str(v or "INFO").strip().upper()
        if s in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            return s
        return "INFO"

    log_json_max_chars: int = Field(default=16_000, validation_alias="GPTHUB_LOG_JSON_MAX_CHARS")
    log_upstream_error_chars: int = Field(default=8_000, validation_alias="GPTHUB_LOG_UPSTREAM_ERROR_CHARS")

    @field_validator("log_json_max_chars", "log_upstream_error_chars", mode="before")
    @classmethod
    def non_negative_log_int(cls, v: object) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, n)

    auto_model_id: str = "gpthub-auto"
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
    default_llm: str = "mws-gpt-alpha"
    vision_model: str = "cotype-pro-vl-32b"
    image_gen_model: str = "qwen-image"
    image_edit_enabled: bool = Field(default=True, validation_alias="GPTHUB_IMAGE_EDIT_ENABLED")
    image_edit_model: str = Field(default="", validation_alias="GPTHUB_IMAGE_EDIT_MODEL")
    image_edit_input_fidelity: str = Field(default="high", validation_alias="GPTHUB_IMAGE_EDIT_FIDELITY")
    image_edit_img2img_strength: float = Field(
        default=0.42,
        validation_alias="GPTHUB_IMAGE_EDIT_STRENGTH",
    )

    @field_validator("image_edit_input_fidelity", mode="before")
    @classmethod
    def normalize_image_edit_fidelity(cls, v: object) -> str:
        s = str(v or "high").strip().lower()
        return s if s in ("high", "low") else "high"

    @field_validator("image_edit_img2img_strength", mode="before")
    @classmethod
    def clamp_img2img_strength(cls, v: object) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return 0.42
        return max(0.05, min(0.95, x))

    asr_model: str = "whisper-medium"
    asr_default_language: str = Field(
        default="",
        validation_alias="GPTHUB_ASR_DEFAULT_LANGUAGE",
    )
    # Если MWS не принимает tts-1/alloy из Open WebUI — задайте id модели и голоса из GET /v1/models (или документации).
    tts_override_model: str = Field(default="", validation_alias="GPTHUB_TTS_MODEL")
    tts_override_voice: str = Field(default="", validation_alias="GPTHUB_TTS_VOICE")
    embedding_model: str = "bge-m3"
    non_chat_model_ids: str = Field(
        default="bge-m3",
        validation_alias="GPTHUB_NON_CHAT_MODEL_IDS",
    )

    def router_skip_model_ids(self) -> frozenset[str]:
        ids = {x.strip() for x in (self.non_chat_model_ids or "").split(",") if x.strip()}
        em = (self.embedding_model or "").strip()
        if em:
            ids.add(em)
        return frozenset(ids)

    memory_top_k: int = 8
    rag_top_k: int = 5
    chunk_size: int = 900
    chunk_overlap: int = 120

    memory_max_items_per_user: int = Field(
        default=400, validation_alias="GPTHUB_MEMORY_MAX_ITEMS"
    )
    memory_llm_digest: bool = Field(default=True, validation_alias="GPTHUB_MEMORY_LLM_DIGEST")
    memory_digest_model: str = Field(
        default="mws-gpt-alpha",
        validation_alias="GPTHUB_MEMORY_DIGEST_MODEL",
    )
    memory_raw_fallback: bool = Field(default=False, validation_alias="GPTHUB_MEMORY_RAW_FALLBACK")
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

    router_debug: bool = Field(default=True, validation_alias="GPTHUB_ROUTER_DEBUG")
    router_mode: str = Field(default="gena", validation_alias="GPTHUB_ROUTER_MODE")
    gena_code_model: str = Field(
        default="qwen3-coder-480b-a35b",
        validation_alias="GPTHUB_GENA_CODE_MODEL",
    )
    gena_long_doc_model: str = Field(
        default="cotype-pro-vl-32b",
        validation_alias="GPTHUB_GENA_LONG_DOC_MODEL",
    )
    gena_chat_model: str = Field(
        default="mws-gpt-alpha",
        validation_alias="GPTHUB_GENA_CHAT_MODEL",
    )
    simple_chat_model: str = Field(
        default="",
        validation_alias="GPTHUB_SIMPLE_CHAT_MODEL",
    )
    gena_long_doc_word_threshold: int = Field(
        default=600,
        validation_alias="GPTHUB_GENA_LONG_DOC_WORDS",
    )
    gena_system_identity: str = Field(
        default=(
            "Идентичность: ты — gena 2.0, цифровой ассистент. "
            "На вопросы «кто ты», «как тебя зовут», «представься» отвечай кратко: "
            "ты gena (версия 2.0). Не выдумывай другое имя и не представляйся базовой моделью провайдера. "
            "Отвечай на том же языке, на котором пользователь пишет (русский, English и т.д.), "
            "если он явно не просит другой язык. "
            "В диалоге после генерации изображения, если пользователь просит правку (цвет, деталь, стиль), "
            "опирайся на последнее твоё сообщение с этой картинкой и не отвечай пустой ссылкой — "
            "уточни запрос или опиши изменение явно."
        ),
        validation_alias="GPTHUB_GENA_IDENTITY",
    )

    public_base_url: str = Field(default="", validation_alias="GPTHUB_PUBLIC_BASE_URL")
    chroma_host: str = Field(default="", validation_alias="CHROMA_HOST")
    chroma_port: int = Field(default=8000, validation_alias="CHROMA_PORT")

    mws_http_retries: int = Field(default=2, validation_alias="GPTHUB_MWS_HTTP_RETRIES")
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
        default=2_000_000,
        validation_alias="GPTHUB_MAX_CHAT_PAYLOAD_CHARS",
    )
    gena_max_presentation_slides: int = Field(
        default=20,
        validation_alias="GPTHUB_MAX_PRESENTATION_SLIDES",
    )
    gena_pptx_template_path: str = Field(
        default="",
        validation_alias="GPTHUB_PPTX_TEMPLATE_PATH",
    )
    gena_pptx_use_bundled_template: bool = Field(
        default=False,
        validation_alias="GPTHUB_PPTX_USE_BUNDLED_TEMPLATE",
    )
    gena_pptx_roundtrip: bool = Field(default=False, validation_alias="GPTHUB_PPTX_ROUNDTRIP")
    gena_pptx_validate_zip: bool = Field(default=True, validation_alias="GPTHUB_PPTX_VALIDATE_ZIP")
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
