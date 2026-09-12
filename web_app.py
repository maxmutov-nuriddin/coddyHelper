"""
coddyHelper - Telegram Mini App (Web App) Admin Panel Backend
Faqat mentor (@mentor_cc / ID: 8105823872) uchun xavfsiz boshqaruv API va WebApp xizmati.
"""

import os
import time
import secrets
import logging
from pathlib import Path
from aiohttp import web
from config import config
from services.memory_service import memory_service
from services.ai_service import ai_service
from handlers.auto_reply import RECENT_ACTIVITY_LOGS

logger = logging.getLogger(__name__)

# Faol autentifikatsiya tokenlari (xotira + SQLite)
ACTIVE_ADMIN_TOKENS: dict[str, dict] = {}
TOKEN_LIFETIME = 86400 * 3  # 72 soat

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


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
            return web.Response(text=content, content_type="text/html")
        except Exception as e:
            logger.error("HTML sahifani yuklashda xatolik: %s", e)
            return web.Response(text=f"<h1>Xatolik: {e}</h1>", content_type="text/html", status=500)

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

        # Telegram WebApp ID si orqali to'g'ridan-to'g'ri tekshirish
        tg_valid = False
        if tg_id is not None:
            try:
                tg_valid = int(tg_id) in allowed_mentor_ids
            except (ValueError, TypeError):
                tg_valid = False

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

        # Muvaffaqiyatli: yangi yoki mavjud tokenni qaytaramiz
        if not token_valid:
            token = generate_admin_token(user_id=int(tg_id))

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
    # -----------------------------------------------------------
    async def handle_api_status(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)

        client = get_client_func()
        telegram_me = "Teacher (@mentor_cc) ID:8105823872"
        telegram_authorized = False
        if client:
            try:
                telegram_authorized = await client.is_user_authorized()
                if telegram_authorized:
                    me = await client.get_me()
                    telegram_me = f"{getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')}) ID:{getattr(me, 'id', '')}"
            except Exception as e:
                telegram_me = f"Xatolik: {e}"

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
                "active_ai": active_ai,
                "escalation_chat": str(config.escalation_chat),
                "mentor_wait_seconds": config.mentor_wait_seconds,
                "active_chats_count": memory_service.total_active_chats(),
                "active_reminders_count": len(memory_service.get_active_reminders(100)),
                "ignored_users_count": len(memory_service.get_ignored_users()),
                "recent_activity_logs": list(reversed(RECENT_ACTIVITY_LOGS[-15:])),
                "telegram_authorized": telegram_authorized,
                "telegram_me": telegram_me,
                "mentor": {
                    "id": config.mentor_user_id,
                    "username": "mentor_cc",
                    "name": "Teacher",
                },
            }
        )

    # -----------------------------------------------------------
    # 4. Avto-javoblarni yoqish / o'chirish (Toggle)
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

        if feature == "auto_reply":
            config.auto_reply_enabled = enabled
            memory_service.set_setting("auto_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali auto_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "group_reply":
            config.group_reply_enabled = enabled
            memory_service.set_setting("group_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali group_reply_enabled o'zgartirildi: %s", enabled)
        else:
            return web.json_response({"ok": False, "error": "Noma'lum funksiya"}, status=400)

        return web.json_response(
            {
                "ok": True,
                "feature": feature,
                "enabled": enabled,
                "auto_reply_enabled": config.auto_reply_enabled,
                "group_reply_enabled": config.group_reply_enabled,
            }
        )

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
            remind_at = (data.get("remind_at") or "").strip()
            if not text or not remind_at:
                return web.json_response({"ok": False, "error": "Matn va vaqt talab qilinadi"}, status=400)

            target = config.escalation_chat or "me"
            s = str(target).strip()
            chat_id = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else config.mentor_user_id

            rem_id = memory_service.add_reminder(
                chat_id=chat_id,
                reminder_text=text,
                remind_at=remind_at,
                creator_id=config.mentor_user_id,
            )
            return web.json_response({"ok": True, "id": rem_id})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_api_delete_reminder(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            rem_id = int(data.get("id"))
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
            return web.json_response({"ok": success})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    # -----------------------------------------------------------
    # 7. AI Co-Pilot (Tech Lead Chat)
    # -----------------------------------------------------------
    async def handle_api_ai_chat(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        try:
            data = await request.json()
            msg = (data.get("message") or "").strip()
            if not msg:
                return web.json_response({"ok": False, "error": "Xabar bo'sh bo'lishi mumkin emas"}, status=400)

            reply = await ai_service.generate_reply(
                chat_id=config.mentor_user_id,
                user_message=msg,
                is_group=False,
                sender_name="Teacher (Mentor)",
            )
            return web.json_response({"ok": True, "reply": reply})
        except Exception as e:
            logger.error("AI Chat xatolik: %s", e)
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

    # Routerga qo'shish
    app.router.add_get("/app", handle_app_page)
    app.router.add_post("/api/auth", handle_api_auth)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_post("/api/toggle", handle_api_toggle)
    app.router.add_get("/api/reminders", handle_api_get_reminders)
    app.router.add_post("/api/reminders/add", handle_api_add_reminder)
    app.router.add_post("/api/reminders/delete", handle_api_delete_reminder)
    app.router.add_get("/api/ignored", handle_api_get_ignored)
    app.router.add_post("/api/ignored/remove", handle_api_remove_ignored)
    app.router.add_post("/api/ai_chat", handle_api_ai_chat)
    app.router.add_get("/api/backup", handle_api_backup)

    logger.info("Telegram Mini App Admin Panel routerlari muvaffaqiyatli o'rnatildi (/app, /api/*).")
