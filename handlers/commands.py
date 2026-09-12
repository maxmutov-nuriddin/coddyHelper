"""
Foydalanuvchi buyruqlari (Userbot komandalari)
"""

import logging
from telethon import TelegramClient, events
from config import config
from services.ai_service import ai_service
from services.memory_service import memory_service

logger = logging.getLogger(__name__)


def register_command_handlers(client: TelegramClient) -> None:
    prefix = config.command_prefix

    @client.on(events.NewMessage(outgoing=True))
    async def handle_user_command(event: events.NewMessage.Event):
        raw_text = event.raw_text or ""
        if not raw_text.startswith(prefix):
            return

        command_body = raw_text[len(prefix) :].strip()
        parts = command_body.split(maxsplit=1)
        if not parts:
            return

        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # -----------------------------------------------------------
        # 1. .ai on / .ai off / .ai <prompt>
        # -----------------------------------------------------------
        if cmd == "ai":
            if arg.lower() in ("on", "1", "start", "enable"):
                config.auto_reply_enabled = True
                await event.edit("🤖 **Avto-javob rejimi faollashtirildi!**\nKelgan shaxsiy xabarlarga AI avtomatik javob beradi.")
                return

            if arg.lower() in ("off", "0", "stop", "disable"):
                config.auto_reply_enabled = False
                await event.edit("⏸ **Avto-javob rejimi to'xtatildi.**\nXabarlar faqat qo'lda boshqariladi.")
                return

            # Agar biror xabarga reply qilingan bo'lsa
            reply_text = None
            image_bytes = None

            if event.is_reply:
                reply_message = await event.get_reply_message()
                if reply_message:
                    if reply_message.text:
                        reply_text = reply_message.text
                    if reply_message.photo or (
                        reply_message.document
                        and reply_message.file
                        and getattr(reply_message.file, "mime_type", "").startswith("image/")
                    ):
                        image_bytes = await reply_message.download_media(bytes)
            elif event.message.photo:
                image_bytes = await event.message.download_media(bytes)

            prompt = arg
            if not prompt and not reply_text and not image_bytes:
                await event.edit(f"ℹ️ **Foydalanish:** `{prefix}ai <savolingiz>` yoki biror rasm/xabarga reply qilib `{prefix}ai` deb yozing.")
                return

            # Xabarni "Javob tayyorlanmoqda..." ga o'zgartirish
            await event.edit("⏳ **AI vazifa/skrinshotni tahlil qilmoqda...**")

            # AI dan javob olish
            user_input = prompt if prompt else "Ushbu rasm/skrinshotdagi LMS vazifasi yoki xatolikni tahlil qilib, o'quvchiga to'g'ri yo'nalish va yechim ber."
            answer = await ai_service.generate_reply(
                chat_id=event.chat_id,
                user_message=user_input,
                reply_to_context=reply_text,
                image_bytes=image_bytes,
            )

            # Yakuniy javobni chiqarish
            try:
                await event.edit(answer)
            except Exception as e:
                logger.error("Xabarni tahrirlashda xatolik: %s", e)
                await event.reply(answer)
            return

        # -----------------------------------------------------------
        # 2. .status - Bot va tizim holati
        # -----------------------------------------------------------
        if cmd == "status":
            auto_status = "🟢 Yoqilgan" if config.auto_reply_enabled else "🔴 O'chirilgan"
            active_chats = memory_service.total_active_chats()
            status_text = (
                "📊 **coddyHelper Tizim Holati**\n\n"
                f"- **Avto-javob rejimi:** {auto_status}\n"
                f"- **AI Modeli:** `{config.gemini_model}`\n"
                f"- **Xotiradagi faol chatlar:** {active_chats} ta\n"
                f"- **Buyruqlar prefiksi:** `{config.command_prefix}`\n"
                f"- **Xotira chegarasi:** {config.memory_limit} ta xabar"
            )
            await event.edit(status_text)
            return

        # -----------------------------------------------------------
        # 3. .clear - Ushbu chat xotirasini tozalash
        # -----------------------------------------------------------
        if cmd == "clear":
            cleared = memory_service.clear(event.chat_id)
            if cleared:
                await event.edit("🧹 **Ushbu chat uchun suhbat tarixi tozalandi.**")
            else:
                await event.edit("ℹ️ Bu chat uchun xotirada saqlangan ma'lumot yo'q.")
            return

        # -----------------------------------------------------------
        # 4. .help - Yordam menyusi
        # -----------------------------------------------------------
        if cmd == "help":
            help_text = (
                "🤖 **coddyHelper AI Yordamchi — Buyruqlar:**\n\n"
                f"- `{prefix}ai <matn>` — Tezkor AI javobini olish\n"
                f"- `reply + {prefix}ai` — Xabarni tahlil qilish yoki unga javob yozish\n"
                f"- `{prefix}ai on` — Shaxsiy xabarlarga avto-javobni yoqish\n"
                f"- `{prefix}ai off` — Avto-javobni to'xtatish\n"
                f"- `{prefix}status` — Tizim va xotira holatini ko'rish\n"
                f"- `{prefix}clear` — Joriy chatdagi suhbat tarixini o'chirish\n"
                f"- `{prefix}help` — Ushbu yordam oynasini ko'rsatish"
            )
            await event.edit(help_text)
            return
