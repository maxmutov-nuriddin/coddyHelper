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
    ovozli va faol push-uvidomleniya bilan mentorga va chatga yetkazadi.
    """
    logger.info("Eslatmalar tekshiruvchi fon xizmati (Toshkent vaqti) faollashdi.")
    await asyncio.sleep(10)  # Telethon to'liq ulanishi uchun
    from services.memory_service import memory_service
    from services.reminder_service import send_due_reminder_notification

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

                await send_due_reminder_notification(
                    rem_id=rem_id,
                    chat_id=chat_id,
                    task_text=task_text,
                    remind_at=remind_at,
                    client=client,
                )
        except Exception as e:
            logger.error("Reminder workerda kutilmagan xatolik: %s", e)

        await asyncio.sleep(25)


async def start_backup_worker(client: TelegramClient):
    """
    SQLite ma'lumotlar bazasini har 24 soatda avtomatik Telegram Botiga (@coddyassistanstbot)
    yuboradi. Eskisini o'chirib, barcha yangi va eski ma'lumotlarni o'z ichiga olgan
    yangi faylni qoldiradi. Izbrannoe (Saved Messages) ga tashlamaydi.
    """
    logger.info("SQLite avto-backup fon xizmati faollashdi.")
    await asyncio.sleep(60)  # Tizim to'liq ulanishi uchun 1 daqiqa kutish
    from services.bot_service import send_or_update_database_backup

    while True:
        try:
            ok, err = await send_or_update_database_backup()
            if ok:
                logger.info("SQLite avto-backup botga muvaffaqiyatli yuborildi va avvalgisi tozalandi.")
            else:
                logger.warning("Auto-backup botga yuborishda ogohlantirish: %s", err)
        except Exception as e:
            logger.error("Auto-backup workerda kutilmagan xatolik: %s", e)

        await asyncio.sleep(3600)  # Har 1 soatda bir marta avto-backup


async def auto_restore_database_on_startup(client: TelegramClient):
    """
    Render qayta ishga tushganda yoki yangi commit push bo'lganda,
    bot chatidagi va 'me' (Saved Messages) dagi eng so'nggi zaxira (coddy_memory.db)
    faylini avtomatik topib, barcha eski ma'lumotlarni joriy bazaga to'liq tiklaydi va birlashtiradi.
    """
    from services.memory_service import memory_service
    logger.info("⏳ Avto-tiklash: So'nggi zaxira xotirasini qidirish...")
    try:
        from pathlib import Path
        import tempfile
        targets = []
        if config.bot_username:
            targets.append(config.bot_username)
        if config.mentor_user_id:
            targets.append(config.mentor_user_id)
        targets.append("me")

        restored = False
        for target in targets:
            try:
                async for message in client.iter_messages(target, limit=20):
                    if message.document and getattr(message.file, "name", "") == "coddy_memory.db":
                        logger.info("🔍 '%s' chatidan so'nggi coddy_memory.db topildi (ID: %d). Tiklanmoqda...", target, message.id)
                        tmp_dir = Path(tempfile.gettempdir()) / "coddy_restore"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        tmp_file = tmp_dir / f"restore_{message.id}.db"

                        await message.download_media(file=str(tmp_file))
                        if tmp_file.exists() and tmp_file.stat().st_size > 0:
                            ok, msg = memory_service.merge_database(tmp_file)
                            if ok:
                                logger.info("🎉 Baza muvaffaqiyatli tiklandi va birlashtirildi: %s", msg)
                                restored = True
                            tmp_file.unlink(missing_ok=True)
                            break
            except Exception as target_err:
                logger.debug("Chat %s ni tekshirishda ogohlantirish: %s", target, target_err)
            if restored:
                break
    except Exception as e:
        logger.warning("Startupda avto-tiklashda ogohlantirish: %s", e)


def setup_shutdown_handlers(client: TelegramClient, loop: asyncio.AbstractEventLoop):
    """Render to'xtash signali (SIGTERM/SIGINT) yuborganda oxirgi bazani zaxiralab chiqish."""
    import signal

    async def shutdown(sig_name):
        logger.info("🛑 Signal %s qabul qilindi. Render o'chishi oldidan oxirgi zaxirani botga yuborish...", sig_name)
        try:
            from services.autonomous_brain_service import autonomous_brain_service
            await autonomous_brain_service.stop()
        except Exception:
            pass
        try:
            from services.bot_service import send_or_update_database_backup
            ok, err = await send_or_update_database_backup()
            if ok:
                logger.info("🎉 Render o'chishi oldidan oxirgi zaxira muvaffaqiyatli botga yuborildi!")
            else:
                logger.warning("Shutdown zaxirasida ogohlantirish: %s", err)
        except Exception as e:
            logger.error("Shutdown zaxirada xatolik: %s", e)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name)))
        except (NotImplementedError, RuntimeError):
            pass


CURRENT_CLIENT: TelegramClient | None = None
CACHED_IS_AUTH: bool = False
CACHED_ME_INFO: str = "Boshlanmoqda..."


async def start_render_web_server(port: int):
    """Render.com Web Service uchun HTTP healthcheck va diagnostika serveri."""
    async def handle_ping(request):
        global CURRENT_CLIENT, CACHED_IS_AUTH, CACHED_ME_INFO
        from handlers.auto_reply import RECENT_ACTIVITY_LOGS
        return web.json_response({
            "status": "online",
            "version": "v2.7.0",
            "service": "coddyHelper AI Mentor Agent",
            "active_ai": "Groq Multi-Key Cluster",
            "telegram_authorized": CACHED_IS_AUTH,
            "telegram_me": CACHED_ME_INFO,
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
    """Render Web Service uxlab qolmasligi va xotira to'lib ketmasligi uchun keep-alive va GC xizmati."""
    await asyncio.sleep(45)
    import aiohttp
    import gc
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Ichki healthcheck
                url = f"http://127.0.0.1:{port}/health"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.debug("Local keep-alive ping muvaffaqiyatli.")

                # 2. Tashqi Render public URL ga ping (Render 15 daqiqada uxlab qolmasligi uchun)
                ext_url = (config.web_app_url or "").strip().rstrip("/")
                if ext_url and "onrender.com" in ext_url:
                    ping_url = f"{ext_url}/health"
                    try:
                        async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=15)) as ext_resp:
                            logger.debug("Tashqi Render keep-alive ping: %s", ext_resp.status)
                    except Exception as ext_err:
                        logger.debug("Tashqi pingda ogohlantirish: %s", ext_err)

                # 3. 512 MB RAM chegarasidan oshib ketmaslik uchun davriy xotirani tozalash (GC)
                gc.collect()
            except Exception as e:
                logger.debug("Keep-alive ogohlantirish: %s", e)
            await asyncio.sleep(240)  # Har 4 daqiqada (15 daqiqalik uxlab qolish chegarasidan oldin)


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
        device_model="Agent Assistent",
        system_version="Executive AI Co-Pilot",
        app_version="coddyHelper 2.0",
        lang_code="uz",
        system_lang_code="uz",
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

    # Render restartida bazani avtomatik zaxiradan tiklash (agar baza yangi/bo'sh bo'lsa)
    await auto_restore_database_on_startup(client)
    restored_auto = memory_service.get_setting("auto_reply_enabled")
    if restored_auto is not None:
        config.auto_reply_enabled = (restored_auto == "true")
    restored_group = memory_service.get_setting("group_reply_enabled")
    if restored_group is not None:
        config.group_reply_enabled = (restored_group == "true")

    # Render o'chishi (SIGTERM/SIGINT) oldidan oxirgi bazani zaxiraga yuborish tinglovchisi
    try:
        setup_shutdown_handlers(client, asyncio.get_running_loop())
    except Exception as sh_err:
        logger.debug("Shutdown handler sozlashda ogohlantirish: %s", sh_err)

    # Doimiy eslatmalar, tongi brifing va avto-backup xizmatlarini fonda ishga tushirish
    asyncio.create_task(start_reminder_worker(client))
    asyncio.create_task(start_backup_worker(client))
    from services.morning_service import start_morning_worker
    asyncio.create_task(start_morning_worker(client))
    from services.autonomous_brain_service import autonomous_brain_service
    asyncio.create_task(autonomous_brain_service.start(client))

    # Telegram Bot xizmatini fonda ishga tushirish (Guruh Mini App tugmasi va faqat admin boshqaruvi)
    if config.bot_token:
        from services.bot_service import start_bot_service
        asyncio.create_task(start_bot_service())

    # Barcha mijoz sessionlarini ishga tushirish (har biri o'z akkauntidan ishlaydi)
    try:
        from services.client_session_manager import client_session_manager
        asyncio.create_task(client_session_manager.start_all_saved_sessions())
        logger.info("🔄 Mijoz sessionlari startup'da ishga tushirilmoqda...")
    except Exception as csm_err:
        logger.warning("Client session manager ishga tushirishda ogohlantirish: %s", csm_err)

    me = await client.get_me()
    first_name = getattr(me, "first_name", "Foydalanuvchi")
    username = f"@{me.username}" if getattr(me, "username", None) else f"ID: {me.id}"
    global CACHED_IS_AUTH, CACHED_ME_INFO
    CACHED_IS_AUTH = True
    CACHED_ME_INFO = f"{first_name} ({username}) ID:{me.id}"

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
