"""
coddyHelper - Shaxsiy Telegram AI Yordamchisi (Userbot)
Kirish nuqtasi va Render.com Web Service serveri
"""

import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import config
from handlers.commands import register_command_handlers
from handlers.auto_reply import register_auto_reply_handlers

# Logging sozlamalari
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coddyHelper")


async def start_reminder_worker(client: TelegramClient):
    """
    Doimiy eslatmalar tekshiruvchisi (Asia/Tashkent vaqti bilan).
    Har 25 soniyada SQLite bazasidan vaqti yetgan eslatmalarni olib,
    tegishli chatga ogohlantirish yuboradi.
    """
    logger.info("Eslatmalar tekshiruvchi fon xizmati (Toshkent vaqti) faollashdi.")
    await asyncio.sleep(10)  # Telethon to'liq ulanishi uchun
    from services.memory_service import memory_service

    tashkent_tz = ZoneInfo("Asia/Tashkent")
    while True:
        try:
            current_time = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
            due_reminders = memory_service.get_due_reminders(current_time)
            for rem in due_reminders:
                rem_id = rem["id"]
                chat_id = rem["chat_id"]
                task_text = rem["text"]
                remind_at = rem["remind_at"]

                alert_text = (
                    "🔔 **DIQQAT, ESLATMA VAQTI KELDI!**\n\n"
                    f"📌 **Vazifa:** {task_text}\n"
                    f"⏰ **Rejalashtirilgan vaqt:** `{remind_at}`\n"
                    f"🆔 **ID:** `{rem_id}`"
                )
                try:
                    await client.send_message(chat_id, alert_text)
                    logger.info("Eslatma muvaffaqiyatli yuborildi (ID: %d, Chat: %s)", rem_id, chat_id)
                except Exception as send_err:
                    logger.warning("Eslatmani chatga yuborishda xatolik (%s), me ga urinilmoqda: %s", chat_id, send_err)
                    try:
                        await client.send_message("me", alert_text)
                    except Exception as me_err:
                        logger.error("Eslatmani 'me' ga ham yuborib bo'lmadi: %s", me_err)

                memory_service.mark_reminder_sent(rem_id)
        except Exception as e:
            logger.error("Reminder workerda kutilmagan xatolik: %s", e)

        await asyncio.sleep(25)


async def start_backup_worker(client: TelegramClient):
    """
    SQLite ma'lumotlar bazasini har 24 soatda avtomatik Telegram guruhiga
    (Vazifalar / Escalation chat) yoki Saved Messages ga backup qilib yuboradi.
    """
    logger.info("SQLite avto-backup fon xizmati faollashdi.")
    await asyncio.sleep(60)  # Telethon to'liq ulanishi uchun 1 daqiqa kutish
    from pathlib import Path

    tashkent_tz = ZoneInfo("Asia/Tashkent")
    while True:
        try:
            db_path = Path("coddy_memory.db")
            if db_path.exists():
                now_str = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
                target = config.escalation_chat or "me"
                s = str(target).strip()
                if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                    target = int(s)

                caption = (
                    "💾 **coddy_memory.db Avtomatik Zaxira Nusxasi (Auto-Backup)**\n\n"
                    f"⏰ **Vaqt:** `{now_str}` (Toshkent vaqti)\n"
                    f"📦 **Hajm:** {db_path.stat().st_size / 1024:.1f} KB\n"
                    "ℹ️ Xotira bazasi har 24 soatda avtomatik zaxiralanadi."
                )
                try:
                    await client.send_file(target, str(db_path), caption=caption)
                    logger.info("SQLite avto-backup yuborildi: %s", target)
                except Exception as send_err:
                    logger.warning("Backupni %s ga yuborishda xatolik, 'me' ga urinilmoqda: %s", target, send_err)
                    try:
                        await client.send_file("me", str(db_path), caption=caption)
                    except Exception as me_err:
                        logger.error("Backupni 'me' ga ham yuborib bo'lmadi: %s", me_err)
        except Exception as e:
            logger.error("Auto-backup workerda kutilmagan xatolik: %s", e)

        await asyncio.sleep(86400)  # Har 24 soatda bir marta



CURRENT_CLIENT: TelegramClient | None = None


async def start_render_web_server(port: int):
    """Render.com Web Service uchun HTTP healthcheck va diagnostika serveri."""
    async def handle_ping(request):
        global CURRENT_CLIENT
        is_auth = False
        me_info = "Kutilmoqda..."
        if CURRENT_CLIENT:
            try:
                is_auth = await CURRENT_CLIENT.is_user_authorized()
                if is_auth:
                    me = await CURRENT_CLIENT.get_me()
                    me_info = f"{getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')}) ID:{getattr(me, 'id', '')}"
                else:
                    me_info = "Avtorizatsiyadan o'tilmagan (Session kerak)"
            except Exception as e:
                me_info = f"Xatolik: {e}"

        from handlers.auto_reply import RECENT_ACTIVITY_LOGS
        return web.json_response({
            "status": "online",
            "version": "v2.7.0",
            "service": "coddyHelper AI Mentor Agent",
            "active_ai": "Groq Multi-Key Cluster",
            "telegram_authorized": is_auth,
            "telegram_me": me_info,
            "auto_reply_enabled": config.auto_reply_enabled,
            "group_reply_enabled": config.group_reply_enabled,
            "escalation_chat": str(config.escalation_chat),
            "has_string_session": bool(config.string_session),
            "recent_activity_logs": list(reversed(RECENT_ACTIVITY_LOGS[-15:])),
        })

    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    app.router.add_get("/status", handle_ping)

    # Telegram Mini App (Admin Panel) routerlarini ulash
    from web_app import setup_web_app_routes
    setup_web_app_routes(app, lambda: CURRENT_CLIENT)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Render Web Service serveri 0.0.0.0:%d portida ishga tushdi.", port)


async def start_keep_alive_worker(port: int):
    """Render Web Service uxlab qolmasligi uchun fon rejimida har 10 daqiqada ping yuboradi."""
    await asyncio.sleep(45)
    import aiohttp
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url = f"http://127.0.0.1:{port}/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.debug("Keep-alive ping muvaffaqiyatli yuborildi.")
            except Exception as e:
                logger.debug("Keep-alive ogohlantirish: %s", e)
            await asyncio.sleep(600)  # Har 10 daqiqada


async def main():
    print("=" * 60)
    print("🚀 coddyHelper — Shaxsiy Telegram AI Yordamchisi ishga tushmoqda...")
    print("=" * 60)

    # Konfiguratsiyani tekshirish
    validation_errors = config.validate()
    if validation_errors:
        print("\n❌ Quyidagi konfiguratsiya xatoliklari aniqlandi:")
        for err in validation_errors:
            print(f"   • {err}")
        print("\nIltimos, '.env' faylini to'g'ri to'ldiring va qayta urinib ko'ring.\n")
        sys.exit(1)

    # Render.com uchun HTTP serverni fonda yurgizish
    try:
        await start_render_web_server(config.port)
        asyncio.create_task(start_keep_alive_worker(config.port))
    except Exception as e:
        logger.warning("Web serverni ishga tushirishda ogohlantirish: %s", e)

    # Telethon mijozini yaratish (StringSession yoki Faylli sessiya)
    if config.string_session:
        logger.info("TELEGRAM_STRING_SESSION orqali avtomatik ulanmoqda...")
        session = StringSession(config.string_session)
    else:
        session = config.session_name

    client = TelegramClient(
        session=session,
        api_id=config.api_id,
        api_hash=config.api_hash,
    )
    global CURRENT_CLIENT
    CURRENT_CLIENT = client

    # Doimiy SQLite sozlamalarini yuklash (restart bo'lganda ham to'xtagan holatda qolishi uchun)
    from services.memory_service import memory_service
    saved_auto = memory_service.get_setting("auto_reply_enabled")
    if saved_auto is not None:
        config.auto_reply_enabled = (saved_auto == "true")
        logger.info("Xotiradan avto-javob holati tiklandi: %s", config.auto_reply_enabled)

    saved_group = memory_service.get_setting("group_reply_enabled")
    if saved_group is not None:
        config.group_reply_enabled = (saved_group == "true")
        logger.info("Xotiradan guruhlar javobi holati tiklandi: %s", config.group_reply_enabled)

    # Handlerlarni ro'yxatga olish
    register_command_handlers(client)
    register_auto_reply_handlers(client)

    # Telegram akkauntiga ulanish
    phone = config.phone if config.phone else None
    await client.start(phone=phone)

    # Doimiy eslatmalar va avto-backup xizmatlarini fonda ishga tushirish
    asyncio.create_task(start_reminder_worker(client))
    asyncio.create_task(start_backup_worker(client))

    # Telegram Bot xizmatini fonda ishga tushirish (Guruh Mini App tugmasi va faqat admin boshqaruvi)
    if config.bot_token:
        from services.bot_service import start_bot_service
        asyncio.create_task(start_bot_service())

    me = await client.get_me()
    first_name = getattr(me, "first_name", "Foydalanuvchi")
    username = f"@{me.username}" if getattr(me, "username", None) else f"ID: {me.id}"

    print("-" * 60)
    print(f"✅ Muvaffaqiyatli ulandi: {first_name} ({username})")
    active_model = f"⚡ Groq ({config.groq_model})" if (config.groq_api_key or config.groq_api_keys) else f"Gemini ({config.gemini_model})"
    print(f"🤖 AI Modeli: {active_model}")
    print(f"📩 Lichka avto-javob: {'Yoqilgan' if config.auto_reply_enabled else 'O‘chirilgan'}")
    print(f"👥 Guruhlar javobi: {'Yoqilgan' if config.group_reply_enabled else 'O‘chirilgan'}")
    print(f"⌨️  Buyruqlar: 'help' yoki '{config.command_prefix}help' Telegram orqali yuborib ko'ring")
    print("-" * 60)
    print("Tizim faol ishlamoqda. To'xtatish uchun Ctrl+C bosing.\n")

    # Ulanishni ushlab turish
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 coddyHelper to'xtatildi.")
