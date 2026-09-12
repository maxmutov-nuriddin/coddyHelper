"""
Loyiha konfiguratsiyasi va muhit o'zgaruvchilari
"""

import os
from dataclasses import dataclass
from pathlib import Path

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
try:
    from dotenv import load_dotenv
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
    else:
        load_dotenv()
except ImportError:
    pass


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "y", "on")


@dataclass
class Config:
    api_id: int
    api_hash: str
    phone: str
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str = ""
    groq_api_keys: list[str] = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    auto_reply_enabled: bool = True
    command_prefix: str = "."
    memory_limit: int = 10
    escalation_chat: str = "me"
    bot_token: str = ""
    session_name: str = "coddy_helper_session"
    string_session: str = ""
    port: int = 10000

    @classmethod
    def load(cls) -> "Config":
        raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_id = int(raw_api_id) if raw_api_id.isdigit() else 0

        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        phone = os.getenv("TELEGRAM_PHONE", "").strip()
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
        
        raw_groq_keys = os.getenv("GROQ_API_KEYS", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
        groq_api_keys = [k.strip() for k in raw_groq_keys.split(",") if k.strip()]
        groq_api_key = groq_api_keys[0] if groq_api_keys else ""
        groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
        groq_vision_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()

        auto_reply_enabled = str_to_bool(os.getenv("AUTO_REPLY_ENABLED", "true"), default=True)
        command_prefix = os.getenv("COMMAND_PREFIX", ".").strip()
        escalation_chat = os.getenv("ESCALATION_CHAT", "me").strip()
        string_session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()

        raw_port = os.getenv("PORT", "10000").strip()
        port = int(raw_port) if raw_port.isdigit() else 10000

        raw_memory_limit = os.getenv("MEMORY_LIMIT", "10").strip()
        memory_limit = int(raw_memory_limit) if raw_memory_limit.isdigit() else 10

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            groq_api_key=groq_api_key,
            groq_api_keys=groq_api_keys,
            groq_model=groq_model,
            groq_vision_model=groq_vision_model,
            auto_reply_enabled=auto_reply_enabled,
            command_prefix=command_prefix,
            memory_limit=memory_limit,
            escalation_chat=escalation_chat,
            string_session=string_session,
            port=port,
        )

    def validate(self) -> list[str]:
        """Konfiguratsiya xatolarini tekshiradi."""
        errors = []
        if not self.api_id:
            errors.append("TELEGRAM_API_ID kiritilmagan yoki noto'g'ri raqam.")
        if not self.api_hash:
            errors.append("TELEGRAM_API_HASH kiritilmagan.")
        if not self.gemini_api_key and not self.groq_api_key:
            errors.append("GROQ_API_KEY yoki GEMINI_API_KEY kiritilmagan.")
        return errors


# Global konfiguratsiya obyekti
config = Config.load()
