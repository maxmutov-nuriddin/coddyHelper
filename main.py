"""
coddyHelper - Shaxsiy Telegram AI Yordamchisi (Userbot)
Kirish nuqtasi va Render.com Web Service serveri
"""

import asyncio
import logging
import sys
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


async def start_render_web_server(port: int):
    """Render.com Web Service uchun HTTP healthcheck serveri."""
    async def handle_ping(request):
        return web.json_response({
            "status": "online",
            "service": "coddyHelper AI Mentor Agent",
            "active_ai": "Groq Multi-Key Cluster",
        })

    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

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
