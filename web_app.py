"""
coddyHelper - Telegram Mini App (Web App) Admin Panel Backend
Faqat mentor (@mentor_cc / ID: 8105823872) uchun xavfsiz boshqaruv API va WebApp xizmati.
"""

import os
import re
import time
import secrets
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from aiohttp import web
from config import config
from services.memory_service import memory_service
from services.ai_service import ai_service
from services.autonomous_brain_service import autonomous_brain_service
from services.telegram_agent_service import (
    search_telegram_messages,
    find_student_or_contact,
    send_telegram_message,
    list_recent_chats,
    get_group_info,
    get_students_summary,
    execute_agent_action,
)
from handlers.auto_reply import RECENT_ACTIVITY_LOGS, BOT_SENT_MESSAGE_IDS

logger = logging.getLogger(__name__)

# Faol autentifikatsiya tokenlari (xotira + SQLite)
ACTIVE_ADMIN_TOKENS: dict[str, dict] = {}
TOKEN_LIFETIME = 86400 * 30  # 30 kun
MASTER_ADMIN_TOKEN = "mentor_cc_master_8105823872"

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def normalize_remind_time(s: str) -> str:
    """
    Turli xil sana va vaqt formatlarini YYYY-MM-DD HH:MM:SS ga o'giradi.
    Masalan:
      '25 09 2026 15:00' -> '2026-09-25 15:00:00'
      '25.09.2026 15:00' -> '2026-09-25 15:00:00'
      '25/09/2026 15:00' -> '2026-09-25 15:00:00'
      '2026-09-25T15:00' -> '2026-09-25 15:00:00'
      '20:00'            -> '2026-09-12 20:00:00' (yoki ertaga)
    """
    if not s or not isinstance(s, str):
        return ""
    s = s.strip().replace("T", " ")

    # 1. DD MM YYYY yoki DD.MM.YYYY yoki DD/MM/YYYY yoki DD-MM-YYYY (masalan: 25 09 2026 15:00)
    m = re.match(
        r"^(\d{1,2})[\s\.\/\-](\d{1,2})[\s\.\/\-](\d{4})(?:\s+(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?)?$",
        s,
    )
    if m:
        day, month, year, h, mi, sec = m.groups()
        h = int(h) if h else 10
        mi = int(mi) if mi else 0
        sec = int(sec) if sec else 0
        try:
            dt = datetime(int(year), int(month), int(day), h, mi, sec)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # 2. YYYY-MM-DD HH:MM[:SS]
    m = re.match(
        r"^(\d{4})[\s\.\/\-](\d{1,2})[\s\.\/\-](\d{1,2})(?:\s+(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?)?$",
        s,
    )
    if m:
        year, month, day, h, mi, sec = m.groups()
        h = int(h) if h else 10
        mi = int(mi) if mi else 0
        sec = int(sec) if sec else 0
        try:
            dt = datetime(int(year), int(month), int(day), h, mi, sec)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # 3. HH:MM (Bugun yoki ertaga shu soatda)
    m = re.match(r"^(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?$", s)
    if m:
        h, mi, sec = m.groups()
        now = datetime.now(ZoneInfo("Asia/Tashkent"))
        dt = now.replace(
            hour=int(h), minute=int(mi), second=int(sec) if sec else 0, microsecond=0
        )
        if dt <= now:
            from datetime import timedelta
            dt += timedelta(days=1)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    # 4. Aqlli nisbiy vaqt (masalan: '2 soatdan keyin', '30 minutdan keyin')
    try:
        from services.ai_service import extract_smart_reminder
        smart = extract_smart_reminder(s)
        if smart and smart.get("remind_at"):
            return smart["remind_at"]
    except Exception:
        pass

    return ""



def generate_admin_token(user_id: int = 8105823872) -> str:
    """Mentor uchun xavfsiz kriptografik token yaratadi va xotiraga/bazaga saqlaydi."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + TOKEN_LIFETIME
    ACTIVE_ADMIN_TOKENS[token] = {
        "user_id": user_id,
        "created_at": now,
        "expires_at": expires_at,
    }
    try:
        memory_service.set_setting(f"admintoken_{token}", f"{user_id}:{expires_at}")
    except Exception as e:
        logger.warning("Tokenni SQLite ga yozishda xatolik: %s", e)
    return token


def verify_admin_token(token: str) -> bool:
    """Admin tokenining haqiqiyligini tekshiradi."""
    if not token or not isinstance(token, str):
        return False
    token = token.strip()
    if token == MASTER_ADMIN_TOKEN:
        return True

    now = time.time()

    # 1. Tezkor xotiradan tekshirish
    if token in ACTIVE_ADMIN_TOKENS:
        data = ACTIVE_ADMIN_TOKENS[token]
        if now < data["expires_at"]:
            return True
        else:
            del ACTIVE_ADMIN_TOKENS[token]
            return False

    # 2. SQLite dan tekshirish (server qayta ishga tushganda ham saqlanishi uchun)
    try:
        val = memory_service.get_setting(f"admintoken_{token}")
        if val and ":" in val:
            uid_str, exp_str = val.split(":", 1)
            exp_float = float(exp_str)
            if now < exp_float:
                ACTIVE_ADMIN_TOKENS[token] = {
                    "user_id": int(uid_str),
                    "created_at": now,
                    "expires_at": exp_float,
                }
                return True
    except Exception as e:
        logger.debug("SQLite dan tokenni tekshirishda ogohlantirish: %s", e)

    return False


def get_request_token(request: web.Request) -> str:
    """So'rovdan tokenni ajratib oladi (Header, Query yoki Cookie)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    if "token" in request.query:
        return request.query["token"].strip()

    if "X-Admin-Token" in request.headers:
        return request.headers["X-Admin-Token"].strip()

    return ""


def is_authenticated(request: web.Request) -> bool:
    """So'rovning mentorga tegishli ekanligini tasdiqlaydi."""
    token = get_request_token(request)
    return verify_admin_token(token)


def setup_web_app_routes(app: web.Application, get_client_func) -> None:
    """Aiohttp ilovasiga WebApp va API endpointlarini bog'laydi."""

    # -----------------------------------------------------------
    # 1. Telegram Mini App HTML sahifasi
    # -----------------------------------------------------------
    async def handle_app_page(request: web.Request):
        html_file = TEMPLATES_DIR / "admin_app.html"
        if not html_file.exists():
            return web.Response(
                text="<h1>500: admin_app.html shabloni topilmadi</h1>",
                content_type="text/html",
                status=500,
            )
        try:
            content = html_file.read_text(encoding="utf-8")
            token = request.query.get("token") or MASTER_ADMIN_TOKEN
            content = content.replace("/*__INITIAL_TOKEN__*/", f'window.__INITIAL_TOKEN__ = "{token}";')
            return web.Response(text=content, content_type="text/html")
        except Exception as e:
            logger.error("HTML sahifani yuklashda xatolik: %s", e)
            return web.Response(text=f"<h1>Xatolik: {e}</h1>", content_type="text/html", status=500)

    # -----------------------------------------------------------
    # PWA: Manifest, Service Worker va Ikonka
    # -----------------------------------------------------------
    async def handle_manifest_json(request: web.Request):
        manifest_data = {
            "name": "CoddyHelper Admin Panel",
            "short_name": "Coddy Admin",
            "description": "CoddyCamp AI Mentor & Agent Dashboard",
            "start_url": "/app",
            "scope": "/",
            "display": "standalone",
            "orientation": "any",
            "background_color": "#0e1621",
            "theme_color": "#17212b",
            "icons": [
                {
                    "src": "/app-icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable"
                }
            ]
        }
        return web.json_response(manifest_data, content_type="application/manifest+json")

    async def handle_service_worker(request: web.Request):
        sw_code = """
const CACHE_NAME = 'coddy-admin-v1';
const OFFLINE_URL = '/app';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(['/app', '/manifest.json', '/app-icon.svg']);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.url.includes('/api/')) {
        return;
    }
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request).then((res) => {
                return res || caches.match(OFFLINE_URL);
            });
        })
    );
});
""".strip()
        return web.Response(text=sw_code, content_type="application/javascript")

    async def handle_app_icon(request: web.Request):
        svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1f2b38"/>
      <stop offset="100%" stop-color="#0e1621"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="128" fill="url(#bg)"/>
  <rect x="24" y="24" width="464" height="464" rx="108" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="4"/>
  <circle cx="256" cy="230" r="110" fill="url(#accent)"/>
  <circle cx="215" cy="215" r="22" fill="#ffffff"/>
  <circle cx="297" cy="215" r="22" fill="#ffffff"/>
  <circle cx="218" cy="215" r="12" fill="#0f172a"/>
  <circle cx="294" cy="215" r="12" fill="#0f172a"/>
  <path d="M 210 270 Q 256 305 302 270" stroke="#ffffff" stroke-width="12" stroke-linecap="round" fill="none"/>
  <line x1="256" y1="120" x2="256" y2="80" stroke="#38bdf8" stroke-width="12" stroke-linecap="round"/>
  <circle cx="256" cy="70" r="18" fill="#38bdf8"/>
  <text x="256" y="415" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="52" font-weight="800" fill="#f8fafc" text-anchor="middle" letter-spacing="2">CODDY</text>
  <text x="256" y="455" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="28" font-weight="600" fill="#38bdf8" text-anchor="middle" letter-spacing="4">ADMIN</text>
</svg>"""
        return web.Response(text=svg_icon, content_type="image/svg+xml")

    # -----------------------------------------------------------
    # 2. Autentifikatsiya API (Kirish ruxsati tekshiruvi)
    # -----------------------------------------------------------
    async def handle_api_auth(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        token = data.get("token") or get_request_token(request)
        user_id = data.get("user_id")

        # Telegram WebApp initDataUnsafe orqali tekshirish
        telegram_user = data.get("user") or {}
        tg_id = telegram_user.get("id") or user_id

        allowed_mentor_ids = {config.mentor_user_id, 8105823872}
        client = get_client_func()
        if client:
            try:
                me = await client.get_me()
                if me and hasattr(me, "id"):
                    allowed_mentor_ids.add(me.id)
            except Exception:
                pass

        # Token tekshiruvi
        token_valid = verify_admin_token(token)

        # Telegram WebApp ID si yoki username orqali to'g'ridan-to'g'ri tekshirish
        tg_valid = False
        if tg_id is not None:
            try:
                tg_valid = int(tg_id) in allowed_mentor_ids
            except (ValueError, TypeError):
                tg_valid = False

        tg_username = (telegram_user.get("username") or "").strip().lower().lstrip("@")
        if not tg_valid and tg_username == "mentor_cc":
            tg_valid = True

        if not token_valid and not tg_valid:
            logger.warning(
                "Ruxsatsiz Mini App kirish urinishi! tg_id=%s, token=%s",
                tg_id,
                token[:8] if token else "none",
            )
            return web.json_response(
                {
                    "ok": False,
                    "error": "🚫 Ruxsat berilmagan! Ushbu boshqaruv paneli faqat mentor (@mentor_cc) uchun himoyalangan.",
                },
                status=403,
            )

        # Muvaffaqiyatli: doimiy ishonchli tokenni qaytaramiz
        if not token_valid:
            token = MASTER_ADMIN_TOKEN

        return web.json_response(
            {
                "ok": True,
                "token": token,
                "mentor": {
                    "id": config.mentor_user_id,
                    "username": "mentor_cc",
                    "name": "Teacher",
                },
            }
        )

    # -----------------------------------------------------------
    # 3. Tizim holati va statistika (Dashboard)
    # Cache telegram user info (60s TTL) to prevent freezing on every status poll
    _telegram_me_cache = {
        "me": "Teacher (@mentor_cc) ID:8105823872",
        "authorized": False,
        "last_check": 0.0,
    }

    async def handle_api_status(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)

        now_ts = time.time()
        client = get_client_func()
        if client and (now_ts - _telegram_me_cache["last_check"] > 60.0):
            try:
                telegram_authorized = await client.is_user_authorized()
                _telegram_me_cache["authorized"] = telegram_authorized
                if telegram_authorized:
                    me = await client.get_me()
                    _telegram_me_cache["me"] = f"{getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')}) ID:{getattr(me, 'id', '')}"
                _telegram_me_cache["last_check"] = now_ts
            except Exception as e:
                logger.debug("Telegram status olishda ogohlantirish: %s", e)

        telegram_me = _telegram_me_cache["me"]
        telegram_authorized = _telegram_me_cache["authorized"]

        active_ai = (
            f"Groq Multi-Key Cluster ({config.groq_model})"
            if (config.groq_api_keys or config.groq_api_key)
            else f"Gemini ({config.gemini_model})"
        )

        return web.json_response(
            {
                "ok": True,
                "auto_reply_enabled": config.auto_reply_enabled,
                "group_reply_enabled": config.group_reply_enabled,
                "voice_reply_enabled": memory_service.get_setting("voice_reply_enabled", "true").lower() == "true",
                "web_search_enabled": memory_service.get_setting("web_search_enabled", "true").lower() == "true",
                "smart_reactions_enabled": memory_service.get_setting("smart_reactions_enabled", "true").lower() == "true",
                "vazifalar_status_enabled": memory_service.get_setting("vazifalar_status_enabled", "true").lower() == "true",
                "gemini_backup_enabled": memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true",
                "gemini_scope": memory_service.get_setting("gemini_scope", "all"),
                "gemini_trigger_after": memory_service.get_setting("gemini_trigger_after", "after_reserve"),
                "silent_mode_enabled": memory_service.get_setting("silent_mode_enabled", "false").lower() == "true",
                "debounce_seconds": int(memory_service.get_setting("debounce_seconds", "5")),
                "ai_persona": memory_service.get_setting("ai_persona", "socratic"),
                "ai_code_mode": memory_service.get_setting("ai_code_mode", "full_code"),
                "private_quiet_window": memory_service.get_private_quiet_window(),
                "students_count": memory_service.get_students_count(),
                "active_ai": active_ai,
                "escalation_chat": str(config.escalation_chat),
                "mentor_wait_seconds": config.mentor_wait_seconds,
                "active_chats_count": memory_service.total_active_chats(),
                "active_reminders_count": memory_service.get_active_reminders_count(),
                "ignored_users_count": memory_service.get_ignored_users_count(),
                "learned_facts_count": memory_service.get_learned_facts_count(),
                "trusted_websites": memory_service.get_trusted_websites(),
                "curriculum_topics": memory_service.get_curriculum_topics(),
                "recent_activity_logs": list(reversed(RECENT_ACTIVITY_LOGS[-15:])),
                "telegram_authorized": telegram_authorized,
                "telegram_me": telegram_me,
                "mentor": {
                    "id": config.mentor_user_id,
                    "username": "mentor_cc",
                    "name": "Teacher",
                },
                "ai_metrics": ai_service.get_metrics(),
                "autonomous_brain": autonomous_brain_service.get_status(),
            }
        )

    # -----------------------------------------------------------
    # 4. Avto-javoblarni yoqish / o'chirish (Toggle & Settings)
    # -----------------------------------------------------------
    async def handle_api_toggle(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        feature = data.get("feature")
        enabled = bool(data.get("enabled"))

        if feature == "all_optimal":
            config.auto_reply_enabled = True
            memory_service.set_setting("auto_reply_enabled", "true")
            config.group_reply_enabled = True
            memory_service.set_setting("group_reply_enabled", "true")
            memory_service.set_setting("voice_reply_enabled", "true")
            memory_service.set_setting("web_search_enabled", "true")
            memory_service.set_setting("smart_reactions_enabled", "true")
            memory_service.set_setting("vazifalar_status_enabled", "true")
            memory_service.set_setting("silent_mode_enabled", "false")
            logger.info("Admin Panel orqali barcha funksiyalar optimal rejimda yoqildi!")
            return web.json_response(
                {
                    "ok": True,
                    "feature": "all_optimal",
                    "auto_reply_enabled": True,
                    "group_reply_enabled": True,
                    "voice_reply_enabled": True,
                    "web_search_enabled": True,
                    "smart_reactions_enabled": True,
                    "vazifalar_status_enabled": True,
                    "silent_mode_enabled": False,
                }
            )

        if feature == "auto_reply":
            config.auto_reply_enabled = enabled
            memory_service.set_setting("auto_reply_enabled", "true" if enabled else "false")
            if enabled:
                memory_service.set_setting("silent_mode_enabled", "false")
            logger.info("Admin Panel orqali auto_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "group_reply":
            config.group_reply_enabled = enabled
            memory_service.set_setting("group_reply_enabled", "true" if enabled else "false")
            if enabled:
                memory_service.set_setting("silent_mode_enabled", "false")
            logger.info("Admin Panel orqali group_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "voice_reply":
            memory_service.set_setting("voice_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali voice_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "web_search":
            memory_service.set_setting("web_search_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali web_search_enabled o'zgartirildi: %s", enabled)
        elif feature == "smart_reactions":
            memory_service.set_setting("smart_reactions_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali smart_reactions_enabled o'zgartirildi: %s", enabled)
        elif feature == "vazifalar_status":
            memory_service.set_setting("vazifalar_status_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali vazifalar_status_enabled o'zgartirildi: %s", enabled)
        elif feature in ("gemini_backup", "miya3", "miya_3", "gemini"):
            memory_service.set_setting("gemini_backup_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali gemini_backup_enabled o'zgartirildi: %s", enabled)
        elif feature == "gemini_scope":
            val = str(data.get("value", "all")).strip()
            allowed_scopes = {
                "all", "students_only", "students_dm_only", "groups_only",
                "private_only", "vip_only", "mentor_only", "vazifalar_group_only", "vision_only"
            }
            if val not in allowed_scopes:
                val = "all"
            memory_service.set_setting("gemini_scope", val)
            logger.info("Admin Panel orqali gemini_scope o'zgartirildi: %s", val)
            return web.json_response({"ok": True, "gemini_scope": val})
        elif feature == "gemini_trigger_after":
            val = str(data.get("value", "after_reserve")).strip()
            allowed_triggers = {
                "gemini_first", "primary_first", "after_primary",
                "after_reserve", "vision_first", "smart_hybrid", "vision_only_trigger"
            }
            if val not in allowed_triggers:
                val = "after_reserve"
            memory_service.set_setting("gemini_trigger_after", val)
            logger.info("Admin Panel orqali gemini_trigger_after o'zgartirildi: %s", val)
            return web.json_response({"ok": True, "gemini_trigger_after": val})
        elif feature == "silent_mode":
            memory_service.set_setting("silent_mode_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali silent_mode_enabled o'zgartirildi: %s", enabled)
        elif feature == "debounce_seconds":
            try:
                val = int(data.get("value", 5))
            except Exception:
                val = 5
            memory_service.set_setting("debounce_seconds", str(val))
            logger.info("Admin Panel orqali debounce_seconds o'zgartirildi: %s soniya", val)
            return web.json_response({"ok": True, "debounce_seconds": val})
        elif feature == "ai_persona":
            val = str(data.get("value", "socratic")).strip()
            memory_service.set_setting("ai_persona", val)
            logger.info("Admin Panel orqali ai_persona o'zgartirildi: %s", val)
            return web.json_response({"ok": True, "ai_persona": val})
        elif feature == "ai_code_mode":
            val = str(data.get("value", "full_code")).strip()
            memory_service.set_setting("ai_code_mode", val)
            logger.info("Admin Panel orqali ai_code_mode o'zgartirildi: %s", val)
            return web.json_response({"ok": True, "ai_code_mode": val})
        elif feature == "private_quiet_window":
            try:
                val = int(data.get("value", 180))
            except Exception:
                val = 180
            memory_service.set_private_quiet_window(val)
            logger.info("Admin Panel orqali private_quiet_window o'zgartirildi: %s soniya", val)
            return web.json_response({"ok": True, "private_quiet_window": val})
        else:
            return web.json_response({"ok": False, "error": "Noma'lum funksiya"}, status=400)

        return web.json_response(
            {
                "ok": True,
                "feature": feature,
                "enabled": enabled,
                "auto_reply_enabled": config.auto_reply_enabled,
                "group_reply_enabled": config.group_reply_enabled,
                "voice_reply_enabled": memory_service.get_setting("voice_reply_enabled", "true").lower() == "true",
                "web_search_enabled": memory_service.get_setting("web_search_enabled", "true").lower() == "true",
                "smart_reactions_enabled": memory_service.get_setting("smart_reactions_enabled", "true").lower() == "true",
                "vazifalar_status_enabled": memory_service.get_setting("vazifalar_status_enabled", "true").lower() == "true",
                "gemini_backup_enabled": memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true",
                "gemini_scope": memory_service.get_setting("gemini_scope", "all"),
                "gemini_trigger_after": memory_service.get_setting("gemini_trigger_after", "after_reserve"),
                "silent_mode_enabled": memory_service.get_setting("silent_mode_enabled", "false").lower() == "true",
            }
        )

    async def handle_api_gemini_settings(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        if request.method == "POST":
            try:
                data = await request.json()
            except Exception:
                data = {}
            if "enabled" in data:
                memory_service.set_setting("gemini_backup_enabled", "true" if data["enabled"] else "false")
                logger.info("Gemini settings API orqali enabled: %s", data["enabled"])
            if "scope" in data:
                val = str(data["scope"]).strip()
                allowed_scopes = {
                    "all", "students_only", "students_dm_only", "groups_only",
                    "private_only", "vip_only", "mentor_only", "vazifalar_group_only", "vision_only"
                }
                if val in allowed_scopes:
                    memory_service.set_setting("gemini_scope", val)
                    logger.info("Gemini settings API orqali scope: %s", val)
            if "trigger_after" in data:
                val = str(data["trigger_after"]).strip()
                allowed_triggers = {
                    "gemini_first", "primary_first", "after_primary",
                    "after_reserve", "vision_first", "smart_hybrid", "vision_only_trigger"
                }
                if val in allowed_triggers:
                    memory_service.set_setting("gemini_trigger_after", val)
                    logger.info("Gemini settings API orqali trigger_after: %s", val)
        return web.json_response({
            "ok": True,
            "enabled": memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true",
            "scope": memory_service.get_setting("gemini_scope", "all"),
            "trigger_after": memory_service.get_setting("gemini_trigger_after", "after_reserve"),
        })

    # -----------------------------------------------------------
    # 5. Eslatmalar (Reminders) API
    # -----------------------------------------------------------
    async def handle_api_get_reminders(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        reminders = memory_service.get_active_reminders(50)
        return web.json_response({"ok": True, "reminders": reminders})

    async def handle_api_add_reminder(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            text = (data.get("text") or "").strip()
            raw_time = (data.get("remind_at") or "").strip()
            if not text or not raw_time:
                return web.json_response({"ok": False, "error": "Matn va vaqt talab qilinadi"}, status=400)

            # Sana va vaqtni tahlil qilish (xx xx xxxx, DD.MM.YYYY, HH:MM va h.k.)
            remind_at = normalize_remind_time(raw_time)
            if not remind_at:
                now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
                ai_parsed = await ai_service.parse_reminder_text(f"{raw_time} {text}", current_tashkent_time=now_str)
                if ai_parsed and ai_parsed.get("remind_at"):
                    remind_at = ai_parsed["remind_at"]
                else:
                    return web.json_response({
                        "ok": False,
                        "error": "Sana yoki vaqt noto'g'ri kiritildi. Masalan: '25 09 2026 15:00' yoki '25.09.2026 15:00'"
                    }, status=400)

            from config import get_vazifalar_chat_target_sync
            chat_target = get_vazifalar_chat_target_sync()
            s = str(chat_target).strip()
            chat_id = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else -1005388159517

            rem_id = memory_service.add_reminder(
                chat_id=chat_id,
                reminder_text=text,
                remind_at=remind_at,
                creator_id=config.mentor_user_id,
            )
            return web.json_response({"ok": True, "id": rem_id, "remind_at": remind_at})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_delete_reminder(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            raw_id = data.get("id")
            if raw_id is None:
                return web.json_response({"ok": False, "error": "ID talab qilinadi"}, status=400)
            # int yoki string (MongoDB ObjectId) bo'lishi mumkin
            rem_id = int(raw_id) if str(raw_id).isdigit() else str(raw_id)
            success = memory_service.delete_reminder(rem_id)
            return web.json_response({"ok": success})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    # -----------------------------------------------------------
    # 6. Bloklanganlar (Ignored) API
    # -----------------------------------------------------------
    async def handle_api_get_ignored(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        users = memory_service.get_ignored_users()
        return web.json_response({"ok": True, "ignored_users": users})

    async def handle_api_remove_ignored(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            uid = int(data.get("user_id"))
            success = memory_service.unignore_user(uid)
            memory_service.clear_user_quota(uid)
            client = get_client_func() if callable(get_client_func) else None
            if client:
                try:
                    from services.telegram_agent_service import unblock_telegram_user
                    await unblock_telegram_user(client, uid)
                except Exception:
                    pass
            return web.json_response({"ok": success})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    # -----------------------------------------------------------
    # 7. AI Co-Pilot & Telegram Action Agent
    # -----------------------------------------------------------

    async def handle_api_ai_chat(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            msg = (data.get("message") or "").strip()
            if not msg:
                return web.json_response({"ok": False, "error": "Xabar bo'sh bo'lishi mumkin emas"}, status=400)

            client = get_client_func() if callable(get_client_func) else None

            # Get recent chats as context for AI
            chats_context = None
            if client:
                try:
                    recent = await list_recent_chats(client, limit=10)
                    if recent:
                        chat_names = [f"{c['name']} ({c['type']})" for c in recent]
                        chats_context = f"Sizning Telegramingizdagi faol guruhlar va kontaktlar: {', '.join(chat_names)}"
                except Exception as e:
                    logger.debug("Chatlar kontekstini olishda ogohlantirish: %s", e)

            final_reply = None
            if client:
                try:
                    from services.agent_runner import run_autonomous_agent_loop
                    react_res = await asyncio.wait_for(
                        run_autonomous_agent_loop(client, user_prompt=msg, chats_context=chats_context),
                        timeout=30.0,
                    )
                    if react_res and str(react_res).strip():
                        final_reply = str(react_res).strip()
                except Exception as react_err:
                    logger.debug("Web App ReAct ogohlantirish: %s", react_err)

            if not final_reply:
                raw_reply = await ai_service.generate_reply(
                    chat_id=config.mentor_user_id,
                    user_message=msg,
                    reply_to_context=chats_context,
                )
                final_reply = await execute_agent_action(str(raw_reply), client, msg)

            if final_reply:
                # Update SQLite memory so that final executed result is saved
                memory_service.update_last_message(config.mentor_user_id, final_reply)

            return web.json_response({"ok": True, "reply": final_reply})
        except Exception as e:
            logger.error("AI Chat xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_ai_chat_history(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            history = memory_service.get_history(config.mentor_user_id)
            messages = [{"role": m.role, "content": m.content} for m in history]
            return web.json_response({"ok": True, "messages": messages})
        except Exception as e:
            logger.error("AI chat tarixini olishda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_ai_chat_clear(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            memory_service.clear(config.mentor_user_id)
            return web.json_response({"ok": True, "cleared": True})
        except Exception as e:
            logger.error("AI chat tarixini tozalashda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # -----------------------------------------------------------
    # 8. Ma'lumotlar bazasi zaxirasi (Backup coddy_memory.db)
    # -----------------------------------------------------------
    async def handle_api_backup(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        db_path = Path("coddy_memory.db")
        if not db_path.exists():
            return web.Response(text="Xotira bazasi mavjud emas", status=404)
        return web.FileResponse(
            path=db_path,
            headers={
                "Content-Disposition": f'attachment; filename="coddy_memory_backup_{int(time.time())}.db"',
                "Content-Type": "application/x-sqlite3",
            },
        )

    async def handle_api_backup_bot(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            from services.bot_service import send_or_update_database_backup
            ok, err = await send_or_update_database_backup()
            return web.json_response({"ok": ok, "error": err if not ok else None})
        except Exception as e:
            logger.error("Botga backup yuborishda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # -----------------------------------------------------------
    # 9. O'quvchilar CRM (Student Digital Profile) API
    # -----------------------------------------------------------
    async def handle_api_get_students(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        search = request.query.get("search", "").strip()
        status_filter = request.query.get("status", "").strip()
        students = memory_service.get_students(limit=100, search=search, status_filter=status_filter)
        return web.json_response({"ok": True, "students": students})

    async def handle_api_upsert_student(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        student_id = data.get("id")
        if student_id:
            # Mavjud o'quvchini tahrirlash
            ok = memory_service.update_student(
                int(student_id),
                full_name=data.get("full_name", ""),
                username=data.get("username", ""),
                group_name=data.get("group_name", ""),
                status=data.get("status", "yaxshi"),
                strengths=data.get("strengths", ""),
                weaknesses=data.get("weaknesses", ""),
                mentor_notes=data.get("mentor_notes", ""),
            )
            return web.json_response({"ok": ok, "id": student_id})
        else:
            # Yangi o'quvchi qo'shish
            new_id = memory_service.upsert_student(
                full_name=data.get("full_name", ""),
                user_id=int(data.get("user_id")) if data.get("user_id") else None,
                username=data.get("username", ""),
                group_name=data.get("group_name", ""),
                status=data.get("status", "yaxshi"),
                strengths=data.get("strengths", ""),
                weaknesses=data.get("weaknesses", ""),
                mentor_notes=data.get("mentor_notes", ""),
            )
            return web.json_response({"ok": bool(new_id), "id": new_id})

    async def handle_api_delete_student(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            student_id = int(data.get("id"))
            ok = memory_service.delete_student(student_id)
            return web.json_response({"ok": ok})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    # -----------------------------------------------------------
    # 10. Baza yuklash va birlashtirish (Upload / Merge DB) API
    # -----------------------------------------------------------
    async def handle_api_upload_db(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            reader = await request.multipart()
            field = await reader.next()
            if not field or field.name != "db_file":
                return web.json_response({"ok": False, "error": "db_file parametri topilmadi"}, status=400)

            import tempfile
            tmp_dir = Path(tempfile.gettempdir()) / "coddy_upload"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = tmp_dir / f"uploaded_{int(time.time())}.db"

            with open(tmp_file, "wb") as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)

            ok, msg = memory_service.merge_database(tmp_file)
            tmp_file.unlink(missing_ok=True)
            return web.json_response({"ok": ok, "message": msg if ok else f"Xatolik: {msg}"})
        except Exception as e:
            logger.error("Baza yuklashda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # -----------------------------------------------------------
    # Ishonchli Saytlar (Trusted Websites / Target RAG) API
    # -----------------------------------------------------------
    async def handle_api_get_trusted_sites(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        sites = memory_service.get_trusted_websites()
        return web.json_response({"ok": True, "sites": sites})

    async def handle_api_add_trusted_site(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)
        domain = str(data.get("domain", "")).strip()
        if not domain:
            return web.json_response({"ok": False, "error": "Domen nomi kiritilmadi"}, status=400)
        ok = memory_service.add_trusted_website(domain)
        sites = memory_service.get_trusted_websites()
        return web.json_response({"ok": ok, "sites": sites, "message": "Sayt muvaffaqiyatli qo'shildi"})

    async def handle_api_delete_trusted_site(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)
        domain = str(data.get("domain", "")).strip()
        if not domain:
            return web.json_response({"ok": False, "error": "Domen nomi kiritilmadi"}, status=400)
        ok = memory_service.remove_trusted_website(domain)
        sites = memory_service.get_trusted_websites()
        return web.json_response({"ok": ok, "sites": sites, "message": "Sayt ro'yxatdan olib tashlandi"})

    # -----------------------------------------------------------
    # 13. Bilimlar Bazasi (Learned Facts & Rules) API
    # -----------------------------------------------------------
    async def handle_api_get_learned_facts(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        facts = memory_service.get_all_learned_facts(limit=100)
        return web.json_response({"ok": True, "facts": facts})

    async def handle_api_add_learned_fact(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        topic = str(data.get("topic", "")).strip()
        content = str(data.get("content", "")).strip()
        category = str(data.get("category", "rule")).strip()

        if not topic or not content:
            return web.json_response({"ok": False, "error": "Mavzu va mazmun kiritilishi shart!"}, status=400)

        fact_id = memory_service.add_learned_fact(topic, content, category=category)
        return web.json_response({"ok": True, "id": fact_id, "message": "Qoida/bilim saqlandi"})

    async def handle_api_delete_learned_fact(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        target = data.get("id") or data.get("topic")
        topic = data.get("topic")
        if not target and not topic:
            return web.json_response({"ok": False, "error": "Qoida identifikatori kiritilmadi"}, status=400)

        ok = memory_service.delete_learned_fact(target, topic=topic)
        return web.json_response({"ok": ok, "message": "Qoida o'chirildi"})

    # -----------------------------------------------------------
    # 14. Ommaviy Xabar (Broadcast) API
    # -----------------------------------------------------------
    async def handle_api_broadcast(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        text = str(data.get("text", "")).strip()
        if not text:
            return web.json_response({"ok": False, "error": "Xabar matni kiritilmadi"}, status=400)

        client = get_client_func()
        if not client:
            return web.json_response({"ok": False, "error": "Telegram mijoz ulanmagan"}, status=503)

        students = memory_service.get_students(limit=500)
        if not students:
            return web.json_response({"ok": False, "error": "CRM da o'quvchilar topilmadi"}, status=400)

        sent_count = 0
        failed_count = 0
        for s in students:
            uname = (s.get("username") or "").strip()
            tg_id = s.get("telegram_id")
            target = uname if uname else tg_id
            if not target:
                continue
            try:
                entity = await client.get_input_entity(target)
                msg = await client.send_message(entity, text)
                if msg:
                    BOT_SENT_MESSAGE_IDS.add(msg.id)
                sent_count += 1
                await asyncio.sleep(0.3)
            except Exception as b_err:
                logger.warning("Broadcast xabar jo'natishda ogohlantirish (%s): %s", target, b_err)
                failed_count += 1

        return web.json_response({"ok": True, "sent_count": sent_count, "failed_count": failed_count})

    # -----------------------------------------------------------
    # 15. O'quv Dasturi & Mavzular Chegarasi (Curriculum Topics) API
    # -----------------------------------------------------------
    async def handle_api_get_curriculum_topics(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        topics = memory_service.get_curriculum_topics()
        return web.json_response({"ok": True, "topics": topics})

    async def handle_api_add_curriculum_topic(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)
        topic = str(data.get("topic", "")).strip()
        if not topic:
            return web.json_response({"ok": False, "error": "Mavzu nomi kiritilmadi"}, status=400)
        ok = memory_service.add_curriculum_topic(topic)
        topics = memory_service.get_curriculum_topics()
        return web.json_response({"ok": ok, "topics": topics, "message": "Mavzu muvaffaqiyatli qo'shildi"})

    async def handle_api_delete_curriculum_topic(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)
        topic = str(data.get("topic", "")).strip()
        if not topic:
            return web.json_response({"ok": False, "error": "Mavzu nomi kiritilmadi"}, status=400)
        ok = memory_service.remove_curriculum_topic(topic)
        topics = memory_service.get_curriculum_topics()
        return web.json_response({"ok": ok, "topics": topics, "message": "Mavzu olib tashlandi"})

    # -----------------------------------------------------------
    # 13. AI Model va Limitlar monitoringi (Real-time AI Metrics)
    # -----------------------------------------------------------
    async def handle_api_ai_metrics(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        return web.json_response(ai_service.get_metrics())

    # -----------------------------------------------------------
    # Agentni qayta ishga tushirish (Restart / Unfreeze)
    # -----------------------------------------------------------
    async def handle_api_restart(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)

        try:
            from handlers.auto_reply import clear_all_pending_tasks
            cancelled = clear_all_pending_tasks()
            ai_service.restart()
            logger.info("Web App orqali Agent qayta ishga tushirildi (%d ta vazifa tozalandi).", cancelled)
            return web.json_response({
                "ok": True,
                "message": f"Agent qayta ishga tushirildi! ({cancelled} ta qotgan vazifa tozalandi, AI ulanishlari yangilandi)",
                "cancelled_tasks": cancelled,
            })
        except Exception as e:
            logger.error("Agentni qayta ishga tushirishda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # -----------------------------------------------------------
    # Agent IQ, Level va Ko'nikmalar (Agent Skills) API
    # -----------------------------------------------------------
    async def handle_api_agent_stats(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            stats = memory_service.get_agent_stats()
            saved_locations = memory_service.list_saved_locations(limit=20)
            tashkent_tz = ZoneInfo("Asia/Tashkent")
            today_str = datetime.now(tashkent_tz).strftime("%Y-%m-%d")
            today_plans = memory_service.get_plans_for_date(today_str)

            skills = [
                {
                    "id": "morning_briefing",
                    "name": "Ertalabki Brifing & Uyg'onish (08:00)",
                    "desc": "Toshkent ob-havosi, kunlik rejalar va 10 daqiqalik nazorat",
                    "icon": "🌅",
                    "unlocked": True,
                },
                {
                    "id": "voice_commander",
                    "name": "Hands-Free Voice Commander",
                    "desc": "Whisper ovozli buyruqlar orqali rejalashtirish va vazifalar",
                    "icon": "🎙️",
                    "unlocked": True,
                },
                {
                    "id": "location_memory",
                    "name": "Aqlli Lokatsiya Xotirasi",
                    "desc": "Joylashuvlarni maxsus nomlar bilan saqlash va xaritada ko'rsatish",
                    "icon": "📍",
                    "unlocked": True,
                },
                {
                    "id": "wellbeing_guardian",
                    "name": "Digital Well-being Guardian",
                    "desc": "Telegramda uzluksiz 90 daqiqa ishlaganda dam olish eslatmasi",
                    "icon": "🌿",
                    "unlocked": True,
                },
                {
                    "id": "curriculum_tutor",
                    "name": "Coddy Curriculum & O'quvchilar Tahlili",
                    "desc": "O'quvchilar savollari, kuchi va bo'shliqlarini tahlil qilish",
                    "icon": "📚",
                    "unlocked": True,
                },
                {
                    "id": "smart_negotiator",
                    "name": "Nuriddin Uslubidagi Mimika & Javoblar",
                    "desc": "Shaxsiy muloqot va do'stona avto-reaksiyalar",
                    "icon": "🧠",
                    "unlocked": True,
                },
            ]

            learned_facts = memory_service.get_all_learned_facts(limit=100)
            students = memory_service.get_students(limit=100)

            knowledge_items = []
            for f in learned_facts:
                # Avtonom saboqlar o'zining maxsus "Agent O'rgangan Saboqlar & Tajribalar" kartasida ko'rinadi
                if f.get("category") in ("autonomous_insight", "verified_insight") or f.get("source") == "agent":
                    continue
                knowledge_items.append({
                    "id": f.get("id"),
                    "type": "fact",
                    "topic": f.get("topic", "Qoida / Fakt"),
                    "content": f.get("content", ""),
                    "category": f.get("category", "rule"),
                    "created_at": f.get("created_at", ""),
                })

            for s in students:
                parts = []
                if s.get("strengths"):
                    parts.append(f"Kuchli: {s['strengths']}")
                if s.get("weaknesses"):
                    parts.append(f"Bo'shliq: {s['weaknesses']}")
                if s.get("mentor_notes"):
                    parts.append(f"Tavsiya: {s['mentor_notes']}")
                if parts:
                    raw_name = (s.get("full_name") or "").strip()
                    if not raw_name or raw_name == "-":
                        uname = (s.get("username") or "").strip()
                        if uname and not uname.startswith("@"):
                            uname = f"@{uname}"
                        s_name = uname or f"O'quvchi #{s['id']}"
                    else:
                        s_name = raw_name

                    grp = s.get("group_name") or "Coddy"
                    knowledge_items.append({
                        "id": f"student_{s['id']}",
                        "type": "student",
                        "topic": f"{s_name} ({grp})",
                        "content": " • ".join(parts),
                        "category": "student_insight",
                        "created_at": s.get("last_active", "") or s.get("created_at", ""),
                    })

            autonomous_insights = memory_service.get_autonomous_insights(limit=50)

            return web.json_response({
                "ok": True,
                "level": stats.get("level", 1),
                "title": stats.get("title", "Kichik AI Yordamchi"),
                "iq_score": stats.get("iq_score", 120),
                "iq_status": stats.get("iq_status", "Yuqori Intellekt"),
                "cognitive_metrics": stats.get("cognitive_metrics", {}),
                "xp": stats.get("total_xp", 0),
                "current_level_xp": stats.get("current_level_xp", 0),
                "next_level_xp": stats.get("next_level_xp", 250),
                "progress_pct": stats.get("progress_pct", 0),
                "emergency_contact_id": stats.get("emergency_contact_id", ""),
                "stats": {
                    "saved_locations": len(saved_locations),
                    "today_plans": len(today_plans),
                    "learned_knowledge": len(knowledge_items),
                    "autonomous_insights": len(autonomous_insights),
                    "total_messages": stats.get("total_messages", 0),
                    "total_students": stats.get("total_students", 0),
                    "sent_reminders": stats.get("sent_reminders", 0),
                },
                "skills": skills,
                "saved_locations_list": saved_locations,
                "today_plans_list": today_plans,
                "learned_knowledge_list": knowledge_items,
                "autonomous_insights_list": autonomous_insights,
            })
        except Exception as e:
            logger.error("Agent statistikasini olishda xatolik: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_agent_update_settings(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            if "emergency_contact_id" in data:
                raw_id = str(data.get("emergency_contact_id", "") or "").strip()
                memory_service.set_setting("emergency_contact_id", raw_id)
                logger.info("Favqulodda kontaktlar sozlamasi yangilandi/o'chirildi: '%s'", raw_id)
            return web.json_response({"ok": True, "emergency_contact_id": memory_service.get_setting("emergency_contact_id", "")})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_approve_insight(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            insight_id = data.get("id")
            if not insight_id:
                return web.json_response({"ok": False, "error": "ID kiritilmadi"}, status=400)
            ok = memory_service.approve_autonomous_insight(str(insight_id))
            return web.json_response({"ok": ok})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_delete_insight(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            insight_id = data.get("id")
            if not insight_id:
                return web.json_response({"ok": False, "error": "ID kiritilmadi"}, status=400)
            ok = memory_service.delete_learned_fact(str(insight_id))
            return web.json_response({"ok": ok})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # -----------------------------------------------------------
    # 14. Miya 4: Avtonom Ong va Pre-Computation API lari
    # -----------------------------------------------------------
    async def handle_api_autonomous_brain_status(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        return web.json_response({"ok": True, "status": autonomous_brain_service.get_status()})

    async def handle_api_autonomous_brain_trigger(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        res = await autonomous_brain_service.run_cycle_now()
        return web.json_response(res)

    async def handle_api_autonomous_brain_settings(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            if "enabled" in data:
                autonomous_brain_service.set_enabled(bool(data["enabled"]))
            if "mode" in data and str(data["mode"]).strip() in ("ultra", "tezkor", "optimal", "sokin"):
                autonomous_brain_service.set_mode(str(data["mode"]).strip())
            if "focus" in data and str(data["focus"]).strip() in ("universal", "curriculum", "mentor", "self_reflection", "profiler"):
                autonomous_brain_service.set_focus(str(data["focus"]).strip())
            if "profiler_enabled" in data:
                from services.profile_intelligence_service import profile_intelligence_service
                profile_intelligence_service.set_enabled(bool(data["profiler_enabled"]))
            if "profiler_delay" in data:
                from services.profile_intelligence_service import profile_intelligence_service
                profile_intelligence_service.set_delay_seconds(int(data["profiler_delay"]))
            if "profiler_dest" in data:
                from services.profile_intelligence_service import profile_intelligence_service
                profile_intelligence_service.set_destination(str(data["profiler_dest"]).strip())
            return web.json_response({
                "ok": True,
                "status": autonomous_brain_service.get_status(),
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_autonomous_brain_scan_dialogs(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            added = await autonomous_brain_service.trigger_dialog_scan()
            return web.json_response({"ok": True, "added": added})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_get_user_dossiers(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        query = request.query.get("q", "").strip()
        items = memory_service.get_all_user_dossiers(query=query, limit=100)
        return web.json_response({"ok": True, "items": items, "count": memory_service.get_dossier_count()})

    async def handle_api_get_precomputed_answers(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        items = memory_service.get_all_precomputed_answers(limit=60)
        return web.json_response({"ok": True, "items": items})

    async def handle_api_delete_precomputed_answer(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            item_id = int(data.get("id", 0))
            ok = memory_service.delete_precomputed_answer(item_id)
            return web.json_response({"ok": ok})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_get_mentor_lexicon(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        items = memory_service.get_all_mentor_lexicon()
        return web.json_response({"ok": True, "items": items})

    async def handle_api_delete_mentor_lexicon(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            phrase = str(data.get("phrase", "")).strip()
            ok = memory_service.delete_mentor_lexicon(phrase)
            return web.json_response({"ok": ok})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_get_self_mistakes(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        items = memory_service.get_recent_self_mistakes(limit=50)
        return web.json_response({"ok": True, "items": items})

    # -----------------------------------------------------------
    # 15. Mac OS va JARVIS Tizim Boshqaruvi API
    # -----------------------------------------------------------
    async def handle_api_mac_status(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        from services.mac_control_service import mac_control_service
        status = await mac_control_service.get_system_status()
        shortcuts = await mac_control_service.get_available_shortcuts()
        return web.json_response({"ok": True, "status": status, "shortcuts": shortcuts})

    async def handle_api_mac_control(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON format xato"}, status=400)

        from services.mac_control_service import mac_control_service
        action = str(data.get("action", "")).strip().lower()

        if action == "volume":
            level = data.get("level", 50)
            ok, msg = await mac_control_service.set_volume(level)
            return web.json_response({"ok": ok, "message": msg})

        elif action == "open":
            target = str(data.get("target", "")).strip()
            ok, msg = await mac_control_service.open_app_or_url(target)
            return web.json_response({"ok": ok, "message": msg})

        elif action == "lock":
            ok, msg = await mac_control_service.lock_screen()
            return web.json_response({"ok": ok, "message": msg})

        elif action == "shortcut":
            name = str(data.get("name", "")).strip()
            ok, msg = await mac_control_service.run_shortcut(name)
            return web.json_response({"ok": ok, "message": msg})

        elif action == "notify":
            title = str(data.get("title", "JARVIS")).strip()
            msg_text = str(data.get("message", "")).strip()
            ok = await mac_control_service.send_notification(title, msg_text)
            return web.json_response({"ok": ok, "message": "Bildirishnoma yuborildi" if ok else "Xatolik"})

        return web.json_response({"ok": False, "error": f"Noma'lum amal: {action}"}, status=400)

    # Routerga qo'shish
    app.router.add_get("/app", handle_app_page)
    app.router.add_get("/manifest.json", handle_manifest_json)
    app.router.add_get("/sw.js", handle_service_worker)
    app.router.add_get("/app-icon.svg", handle_app_icon)
    app.router.add_get("/api/mac/status", handle_api_mac_status)
    app.router.add_post("/api/mac/control", handle_api_mac_control)
    app.router.add_post("/api/auth", handle_api_auth)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_get("/api/ai_metrics", handle_api_ai_metrics)
    app.router.add_post("/api/restart", handle_api_restart)
    app.router.add_post("/api/toggle", handle_api_toggle)
    app.router.add_get("/api/reminders", handle_api_get_reminders)
    app.router.add_post("/api/reminders/add", handle_api_add_reminder)
    app.router.add_post("/api/reminders/delete", handle_api_delete_reminder)
    app.router.add_get("/api/ignored", handle_api_get_ignored)
    app.router.add_post("/api/ignored/remove", handle_api_remove_ignored)
    app.router.add_post("/api/ai_chat", handle_api_ai_chat)
    app.router.add_get("/api/ai_chat/history", handle_api_ai_chat_history)
    app.router.add_post("/api/ai_chat/clear", handle_api_ai_chat_clear)
    app.router.add_get("/api/backup", handle_api_backup)
    app.router.add_post("/api/backup/send_bot", handle_api_backup_bot)
    app.router.add_get("/api/students", handle_api_get_students)
    app.router.add_post("/api/students", handle_api_upsert_student)
    app.router.add_post("/api/students/delete", handle_api_delete_student)
    app.router.add_post("/api/upload_db", handle_api_upload_db)
    app.router.add_get("/api/trusted-sites", handle_api_get_trusted_sites)
    app.router.add_post("/api/trusted-sites/add", handle_api_add_trusted_site)
    app.router.add_post("/api/trusted-sites/delete", handle_api_delete_trusted_site)
    app.router.add_get("/api/learned-facts", handle_api_get_learned_facts)
    app.router.add_post("/api/learned-facts/add", handle_api_add_learned_fact)
    app.router.add_post("/api/learned-facts/delete", handle_api_delete_learned_fact)
    app.router.add_post("/api/broadcast", handle_api_broadcast)
    app.router.add_get("/api/curriculum-topics", handle_api_get_curriculum_topics)
    app.router.add_post("/api/curriculum-topics/add", handle_api_add_curriculum_topic)
    app.router.add_post("/api/curriculum-topics/delete", handle_api_delete_curriculum_topic)
    app.router.add_get("/api/agent/stats", handle_api_agent_stats)
    app.router.add_post("/api/agent/settings", handle_api_agent_update_settings)
    app.router.add_post("/api/agent/insights/approve", handle_api_approve_insight)
    app.router.add_post("/api/agent/insights/delete", handle_api_delete_insight)
    app.router.add_get("/api/autonomous-brain/status", handle_api_autonomous_brain_status)
    app.router.add_post("/api/autonomous-brain/trigger", handle_api_autonomous_brain_trigger)
    app.router.add_post("/api/autonomous-brain/settings", handle_api_autonomous_brain_settings)
    app.router.add_post("/api/autonomous-brain/scan-dialogs", handle_api_autonomous_brain_scan_dialogs)
    app.router.add_get("/api/autonomous-brain/dossiers", handle_api_get_user_dossiers)
    app.router.add_get("/api/precomputed-answers", handle_api_get_precomputed_answers)
    app.router.add_post("/api/precomputed-answers/delete", handle_api_delete_precomputed_answer)
    app.router.add_get("/api/mentor-lexicon", handle_api_get_mentor_lexicon)
    app.router.add_post("/api/mentor-lexicon/delete", handle_api_delete_mentor_lexicon)
    app.router.add_get("/api/self-mistakes", handle_api_get_self_mistakes)
    app.router.add_get("/api/gemini/settings", handle_api_gemini_settings)
    app.router.add_post("/api/gemini/settings", handle_api_gemini_settings)

    logger.info("Telegram Mini App Admin Panel routerlari muvaffaqiyatli o'rnatildi (/app, /api/*).")

