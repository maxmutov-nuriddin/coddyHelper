"""
coddyHelper - Telegram Mini App (Web App) Admin Panel Backend
Faqat mentor (@mentor_cc / ID: 8105823872) uchun xavfsiz boshqaruv API va WebApp xizmati.
"""

import os
import re
import time
import secrets
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from aiohttp import web
from config import config
from services.memory_service import memory_service
from services.ai_service import ai_service
from services.telegram_agent_service import (
    search_telegram_messages,
    find_student_or_contact,
    send_telegram_message,
    list_recent_chats,
    get_group_info,
    get_students_summary,
    execute_agent_action,
)
from handlers.auto_reply import RECENT_ACTIVITY_LOGS

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
                "voice_reply_enabled": memory_service.get_setting("voice_reply_enabled", "true").lower() == "true",
                "private_quiet_window": memory_service.get_private_quiet_window(),
                "students_count": len(memory_service.get_students(limit=1000)),
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

        if feature == "auto_reply":
            config.auto_reply_enabled = enabled
            memory_service.set_setting("auto_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali auto_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "group_reply":
            config.group_reply_enabled = enabled
            memory_service.set_setting("group_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali group_reply_enabled o'zgartirildi: %s", enabled)
        elif feature == "voice_reply":
            memory_service.set_setting("voice_reply_enabled", "true" if enabled else "false")
            logger.info("Admin Panel orqali voice_reply_enabled o'zgartirildi: %s", enabled)
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

            target = config.escalation_chat or "me"
            s = str(target).strip()
            chat_id = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else config.mentor_user_id

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

            raw_reply = await ai_service.generate_reply(
                chat_id=config.mentor_user_id,
                user_message=msg,
                reply_to_context=chats_context,
            )

            # Execute agent actions if present or detected
            final_reply = await execute_agent_action(str(raw_reply), client, msg)

            if final_reply != str(raw_reply):
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
    app.router.add_get("/api/ai_chat/history", handle_api_ai_chat_history)
    app.router.add_post("/api/ai_chat/clear", handle_api_ai_chat_clear)
    app.router.add_get("/api/backup", handle_api_backup)
    app.router.add_post("/api/backup/send_bot", handle_api_backup_bot)
    app.router.add_get("/api/students", handle_api_get_students)
    app.router.add_post("/api/students", handle_api_upsert_student)
    app.router.add_post("/api/students/delete", handle_api_delete_student)
    app.router.add_post("/api/upload_db", handle_api_upload_db)

    logger.info("Telegram Mini App Admin Panel routerlari muvaffaqiyatli o'rnatildi (/app, /api/*).")

