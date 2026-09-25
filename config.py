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
    groq_frontline_keys: list[str] = None
    groq_vip_keys: list[str] = None
    groq_reserve_keys: list[str] = None
    groq_autonomous_keys: list[str] = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    auto_reply_enabled: bool = True
    group_reply_enabled: bool = True
    command_prefix: str = "."
    memory_limit: int = 10
    escalation_chat: str = "-5388159517"
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
    mongodb_uri: str = "mongodb+srv://mahmudovnuriddin35_db_user:a5YQNcWB2EzfMKLy@agent.i4l6lje.mongodb.net/?appName=Agent"
    mongodb_db_name: str = "CoddyAgentBrain"

    @classmethod
    def load(cls) -> "Config":
        raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_id = int(raw_api_id) if raw_api_id.isdigit() else 0

        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        phone = os.getenv("TELEGRAM_PHONE", "").strip()
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        bot_username = os.getenv("BOT_USERNAME", "coddyassistanstbot").strip().lstrip("@")
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        
        raw_frontline = os.getenv("GROQ_FRONTLINE_KEYS", "").strip()
        raw_vip = os.getenv("GROQ_VIP_KEYS", "").strip()
        raw_reserve = os.getenv("GROQ_RESERVE_KEYS", "").strip()
        raw_auto = os.getenv("GROQ_AUTONOMOUS_KEYS", "").strip() or os.getenv("GROQ_EXTRA_KEYS", "").strip()

        groq_frontline_keys = [k.strip() for k in raw_frontline.split(",") if k.strip()]
        groq_vip_keys = [k.strip() for k in raw_vip.split(",") if k.strip()]
        groq_reserve_keys = [k.strip() for k in raw_reserve.split(",") if k.strip()]
        groq_autonomous_keys = [k.strip() for k in raw_auto.split(",") if k.strip()]

        raw_groq_keys = os.getenv("GROQ_API_KEYS", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
        all_keys_list = [k.strip() for k in raw_groq_keys.split(",") if k.strip()]

        combined_keys = []
        for k in (groq_frontline_keys + groq_vip_keys + groq_reserve_keys + groq_autonomous_keys + all_keys_list):
            if k and k not in combined_keys:
                combined_keys.append(k)
        groq_api_keys = combined_keys
        groq_api_key = groq_api_keys[0] if groq_api_keys else ""

        deprecated_text_models = {
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
            "mixtral-8x7b-32768",
            "llama3-70b-8192",
            "llama3-8b-8192",
        }
        raw_groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
        if not raw_groq_model or raw_groq_model in deprecated_text_models:
            groq_model = "openai/gpt-oss-120b"
        else:
            groq_model = raw_groq_model

        deprecated_vision_models = {
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
        }
        raw_vision = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()
        if not raw_vision or raw_vision in deprecated_vision_models:
            groq_vision_model = "qwen/qwen3.8-27b"
        else:
            groq_vision_model = raw_vision

        auto_reply_enabled = str_to_bool(os.getenv("AUTO_REPLY_ENABLED", "true"), default=True)
        group_reply_enabled = str_to_bool(os.getenv("GROUP_REPLY_ENABLED", "true"), default=True)
        command_prefix = os.getenv("COMMAND_PREFIX", ".").strip()
        raw_esc = os.getenv("ESCALATION_CHAT", "-5388159517").strip()
        if not raw_esc or raw_esc.lower() in ("me", "self", "8105823872"):
            escalation_chat = "-5388159517"
        else:
            escalation_chat = raw_esc
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
        mongodb_uri = os.getenv(
            "MONGODB_URI",
            "mongodb+srv://mahmudovnuriddin35_db_user:a5YQNcWB2EzfMKLy@agent.i4l6lje.mongodb.net/?appName=Agent"
        ).strip()
        mongodb_db_name = os.getenv("MONGODB_DB_NAME", "CoddyAgentBrain").strip()

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
            groq_frontline_keys=groq_frontline_keys,
            groq_vip_keys=groq_vip_keys,
            groq_reserve_keys=groq_reserve_keys,
            groq_autonomous_keys=groq_autonomous_keys,
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
            mongodb_uri=mongodb_uri,
            mongodb_db_name=mongodb_db_name,
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

# Faqat yagona mentor (@mentor_cc / ID: 8105823872)
MENTOR_IDS: set[int] = {8105823872, config.mentor_user_id}


def is_mentor(user_id: int | str | None) -> bool:
    """Foydalanuvchi faqat yagona mentor (@mentor_cc / ID: 8105823872) ekanini tekshiradi."""
    if not user_id:
        return False
    try:
        uid = int(user_id)
        return uid in (8105823872, config.mentor_user_id)
    except (ValueError, TypeError):
        return str(user_id).strip().lower() in ("me", "self", "mentor_cc")


def is_escalation_chat(chat_id: int | str) -> bool:
    """Chat ID 'Vazifalar' guruhi ekanini tekshiradi (Izbrannoe / shaxsiy chat kirmaydi)."""
    c_id = str(chat_id).strip()
    if "5388159517" in c_id:
        return True
    target = str(config.escalation_chat).strip()
    if target.lower() in ("me", "self", "8105823872", str(config.mentor_user_id)):
        return False
    if c_id == target:
        return True
    c_norm = c_id.replace("-100", "-")
    t_norm = target.replace("-100", "-")
    return c_norm == t_norm


def normalize_group_id(val: int | str) -> int | str:
    """Telethon uchun guruh ID sini to'g'ri int formatga keltiradi (ortiqcha -100 prefiksini zo'rlab qo'shmaydi)."""
    s = str(val).strip()
    return int(s) if (s.startswith("-") and s.lstrip("-").isdigit()) or s.isdigit() else s


async def get_vazifalar_chat_target(client=None) -> int | str:
    """
    Vazifalar (Boshqaruv markazi) guruhining haqiqiy ID sini aniqlaydi.
    Izbrannoe (Saved Messages / 'me' / 8105823872) ga MUTLAQO HECH NARSANI yo'naltirmaydi!
    """
    try:
        from services.memory_service import memory_service
        saved = memory_service.get_setting("vazifalar_group_id") or memory_service.get_setting("tasks_group_id")
        if saved and str(saved).strip().lower() not in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
            return normalize_group_id(saved)
    except Exception:
        pass

    cfg = str(config.escalation_chat).strip()
    if cfg and cfg.lower() not in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
        return normalize_group_id(cfg)

    if client:
        try:
            dialogs = await client.get_dialogs(limit=40)
            for d in dialogs:
                if d.is_group or d.is_channel:
                    title = (d.name or "").lower()
                    if "vazifa" in title or "boshqaruv" in title:
                        from services.memory_service import memory_service
                        norm_id = normalize_group_id(d.id)
                        memory_service.set_setting("vazifalar_group_id", str(norm_id))
                        return norm_id
        except Exception:
            pass

    return -5388159517


def get_vazifalar_chat_target_sync() -> int | str:
    """Sinxron kontekstda Vazifalar guruh ID sini oladi (hech qachon 'me' yoki Izbrannoe qaytarmaydi)."""
    try:
        from services.memory_service import memory_service
        saved = memory_service.get_setting("vazifalar_group_id") or memory_service.get_setting("tasks_group_id")
        if saved and str(saved).strip().lower() not in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
            return normalize_group_id(saved)
    except Exception:
        pass

    cfg = str(config.escalation_chat).strip()
    if cfg and cfg.lower() not in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
        return normalize_group_id(cfg)

    return -5388159517


def is_administration_chat_or_user(chat_id: Any = None, username: str = None) -> bool:
    """
    CoddyCamp o'quv markazi ma'muriyati (@coddycamp_sergeli / 7754389150) ekanligini aniqlaydi.
    """
    admin_usernames = {"coddycamp_sergeli", "coddycamp_sergeli2"}
    admin_ids = {7754389150, -7754389150}
    if username:
        clean_u = str(username).strip().lstrip("@").lower()
        if clean_u in admin_usernames:
            return True
    if chat_id is not None:
        try:
            cid = int(chat_id)
            if cid in admin_ids:
                return True
        except (ValueError, TypeError):
            pass
        clean_cid = str(chat_id).strip().lstrip("@").lower()
        if clean_cid in admin_usernames:
            return True
    return False



