"""
Render.com ga joylash uchun Telegram sessiyasini satr (StringSession) ko'rinishida olish
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import config


async def export_session():
    print("Mavjud sessiyani o'qish...")
    client = TelegramClient(
        config.session_name,
        config.api_id,
        config.api_hash,
        device_model="Agent Assistent",
        system_version="Executive AI Co-Pilot",
        app_version="coddyHelper 2.0",
        lang_code="uz",
        system_lang_code="uz",
    )
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Akkaunt avtorizatsiya qilinmagan. Avval 'python main.py' orqali kiring.")
        await client.disconnect()
        return

    string_session = StringSession.save(client.session)
    print("\n" + "=" * 70)
    print("🔑 RENDER UCHUN TELEGRAM_STRING_SESSION:")
    print("=" * 70)
    print(string_session)
    print("=" * 70)
    print("\nUshbu uzun qatorni Render'dagi Environment Variables bo'limiga:")
    print("Key:   TELEGRAM_STRING_SESSION")
    print("Value: [yuqoridagi qator]")
    print("ko'rinishida qo'shing. Shunda Render hech qachon kod so'ramasdan darhol ishga tushadi!\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(export_session())
