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
    groq_model: str = "llama-3.3-70b-versatile"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    auto_reply_enabled: bool = True
    group_reply_enabled: bool = True
    command_prefix: str = "."
    memory_limit: int = 10
    escalation_chat: str = "me"
    bot_token: str = ""
    bot_username: str = "coddyassistanstbot"
    session_name: str = "coddy_helper_session"
    string_session: str = ""
    port: int = 10000
    secret_stop_word: str = "ai stop"
    secret_start_word: str = "ai start"
    secret_group_stop_word: str = "guruh stop"
    secret_group_start_word: str = "guruh start"
    mentor_wait_seconds: float = 5.0
    web_app_url: str = "https://coddyhelper.onrender.com"
    mentor_user_id: int = 8105823872

    @classmethod
    def load(cls) -> "Config":
        raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_id = int(raw_api_id) if raw_api_id.isdigit() else 0

        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        phone = os.getenv("TELEGRAM_PHONE", "").strip()
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        bot_username = os.getenv("BOT_USERNAME", "coddyassistanstbot").strip().lstrip("@")
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
        
        raw_groq_keys = os.getenv("GROQ_API_KEYS", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
        groq_api_keys = [k.strip() for k in raw_groq_keys.split(",") if k.strip()]
        groq_api_key = groq_api_keys[0] if groq_api_keys else ""
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        groq_vision_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()

        auto_reply_enabled = str_to_bool(os.getenv("AUTO_REPLY_ENABLED", "true"), default=True)
        group_reply_enabled = str_to_bool(os.getenv("GROUP_REPLY_ENABLED", "true"), default=True)
        command_prefix = os.getenv("COMMAND_PREFIX", ".").strip()
        escalation_chat = os.getenv("ESCALATION_CHAT", "-5388159517").strip()
        string_session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()

        raw_port = os.getenv("PORT", "10000").strip()
        port = int(raw_port) if raw_port.isdigit() else 10000

        secret_stop_word = os.getenv("SECRET_STOP_WORD", "ai stop").strip().lower()
        secret_start_word = os.getenv("SECRET_START_WORD", "ai start").strip().lower()
        secret_group_stop_word = os.getenv("SECRET_GROUP_STOP_WORD", "guruh stop").strip().lower()
        secret_group_start_word = os.getenv("SECRET_GROUP_START_WORD", "guruh start").strip().lower()

        raw_wait = os.getenv("MENTOR_WAIT_SECONDS", "5").strip()
        mentor_wait_seconds = float(raw_wait) if raw_wait.replace(".", "", 1).isdigit() else 5.0

        raw_memory_limit = os.getenv("MEMORY_LIMIT", "10").strip()
        memory_limit = int(raw_memory_limit) if raw_memory_limit.isdigit() else 10

        web_app_url = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEB_APP_URL", "https://coddyhelper.onrender.com")).strip().rstrip("/")
        raw_mentor_id = os.getenv("MENTOR_USER_ID", "8105823872").strip()
        mentor_user_id = int(raw_mentor_id) if raw_mentor_id.isdigit() else 8105823872

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            bot_token=bot_token,
            bot_username=bot_username,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            groq_api_key=groq_api_key,
            groq_api_keys=groq_api_keys,
            groq_model=groq_model,
            groq_vision_model=groq_vision_model,
            auto_reply_enabled=auto_reply_enabled,
            group_reply_enabled=group_reply_enabled,
            command_prefix=command_prefix,
            memory_limit=memory_limit,
            escalation_chat=escalation_chat,
            string_session=string_session,
            port=port,
            secret_stop_word=secret_stop_word,
            secret_start_word=secret_start_word,
            secret_group_stop_word=secret_group_stop_word,
            secret_group_start_word=secret_group_start_word,
            mentor_wait_seconds=mentor_wait_seconds,
            web_app_url=web_app_url,
            mentor_user_id=mentor_user_id,
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


def is_escalation_chat(chat_id: int | str) -> bool:
    """Chat ID 'Vazifalar' (Admin/Eskalyatsiya) guruhi ekanini tekshiradi."""
    c_id = str(chat_id).strip()
    if "5388159517" in c_id:
        return True
    target = str(config.escalation_chat).strip()
    if target.lower() in ("me", "self"):
        if c_id.lower() in ("me", "self") or c_id in (str(config.mentor_user_id), "8105823872"):
            return True
    if c_id == target:
        return True
    c_norm = c_id.replace("-100", "-")
    t_norm = target.replace("-100", "-")
    return c_norm == t_norm


