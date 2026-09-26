"""
Maxfiy qiymatlarni (mijozlarning Telegram HSS / StringSession kodlarini) shifrlab saqlash.

Kalit manbasi (ustuvorlik bo'yicha):
  1. SESSION_ENCRYPTION_KEY muhit o'zgaruvchisi (tavsiya etiladi)
  2. TELEGRAM_API_HASH + BOT_TOKEN dan hosil qilinadigan kalit (fallback)

Shifrlangan qiymat "enc:v1:" prefiksi bilan saqlanadi. Prefikssiz (eski, ochiq) qiymatlar
o'zgarishsiz qaytariladi — shuning uchun mavjud sessiyalar buzilmaydi.
"""

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography o'rnatilmagan — sessiya kodlari shifrlanmaydi.")
        _fernet = False
        return _fernet

    from config import _clean_env_value
    raw_key = _clean_env_value(os.getenv("SESSION_ENCRYPTION_KEY", ""))
    if not raw_key:
        from config import config
        seed = f"coddyhelper-session-v1|{config.api_hash}|{config.bot_token}|{config.api_id}"
        raw_key = seed
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
    _fernet = Fernet(key)
    return _fernet


def encrypt_secret(value: str) -> str:
    """Qiymatni shifrlaydi (bo'sh yoki allaqachon shifrlangan bo'lsa o'zgarishsiz qaytaradi)."""
    if not value or value.startswith(_PREFIX):
        return value or ""
    f = _get_fernet()
    if not f:
        return value
    return _PREFIX + f.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    """Shifrlangan qiymatni ochadi. Eski (ochiq) qiymatlarni o'zgarishsiz qaytaradi."""
    if not value or not value.startswith(_PREFIX):
        return value or ""
    f = _get_fernet()
    if not f:
        return ""
    try:
        return f.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        logger.error("Sessiya kodini deshifrlab bo'lmadi (SESSION_ENCRYPTION_KEY o'zgarganmi?).")
        return ""
