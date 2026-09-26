"""
coddyHelper - Telegram Bot versiyasi (aiogram 3 asosida)
"""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from config import config
from services.ai_service import ai_service
from services.memory_service import memory_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coddyHelperBot")

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    greeting = (
        f"Assalomu alaykum, **{message.from_user.first_name}**!\n\n"
        "Men **coddyHelper** — sizning shaxsiy aqlli AI yordamchingizman.\n"
        "Menga har qanday texnik, tahliliy yoki kundalik savollaringizni yuborishingiz mumkin.\n\n"
        "📌 **Mavjud buyruqlar:**\n"
        "• `/clear` — Suhbat tarixini tozalash\n"
        "• `/help` — Yordam ma'lumotlari"
    )
    await message.answer(greeting, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    memory_service.clear(message.chat.id)
    await message.answer("🧹 **Suhbat tarixi tozalandi.** Yangi mavzuni boshlashingiz mumkin!")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "ℹ️ **Qanday foydalanish mumkin?**\n\n"
        "1. Menga to'g'ridan-to'g'ri xabar yoki savol yozing.\n"
        "2. Har qanday xatoni, kodni yoki masalani tahlil qilib berishim mumkin.\n"
        "3. Kontekstni eslab qolaman, suhbatni erkin davom ettirishingiz mumkin."
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@dp.message()
async def handle_message(message: Message, bot: Bot):
    if not message.text:
        return

    # Typing holatini ko'rsatish
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    # Reply xabarini tekshirish
    reply_context = None
    if message.reply_to_message and message.reply_to_message.text:
        reply_context = message.reply_to_message.text

    # AI javobini olish
    answer = await ai_service.generate_reply(
        chat_id=message.chat.id,
        user_message=message.text,
        reply_to_context=reply_context,
    )

    try:
        await message.answer(answer, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer(answer)

    # Eskalyatsiya xabari
    if getattr(answer, "escalation", None):
        user = message.from_user
        username = f"@{user.username}" if user.username else "Mavjud emas"
        alert_text = (
            "🚨 **O'quvchi murojaati (Mentor aralashuvi kerak):**\n\n"
            f"👤 **O'quvchi:** {user.full_name} ({username})\n"
            f"🆔 **ID:** `{user.id}`\n\n"
            f"❓ **Xabar:**\n\"{message.text}\"\n\n"
            f"📋 **AI Xulosasi:**\n{answer.escalation}"
        )
        try:
            if config.escalation_chat and config.escalation_chat != "me":
                target = int(config.escalation_chat) if config.escalation_chat.isdigit() or config.escalation_chat.startswith("-") else config.escalation_chat
                await bot.send_message(chat_id=target, text=alert_text)
        except Exception as exc:
            logger.error("Bot orqali eskalyatsiya yuborishda xatolik: %s", exc)


async def main():
    if not config.bot_token:
        print("\n❌ Xatolik: BOT_TOKEN topilmadi!")
        print("Iltimos, @BotFather orqali olingan tokenni '.env' faylidagi BOT_TOKEN qatoriga kiriting.")
        sys.exit(1)

    bot = Bot(token=config.bot_token)
    print("=" * 60)
    print("🚀 coddyHelper Telegram Boti muvaffaqiyatli ishga tushdi!")
    print("=" * 60)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Bot to'xtatildi.")
