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
        raw_text = (event.raw_text or "").strip()
        lower_text = raw_text.lower()

        # -----------------------------------------------------------
        # 0. Xavfsizlik: Sirli so'zlar orqali to'liq to'xtatish va yoqish
        # Masalan: "ai stop", "ai start", yoki .env dagi maxsus so'zlar
        # -----------------------------------------------------------
        stop_triggers = {
            config.secret_stop_word,
            "ai stop",
            "coddy stop",
            f"{prefix}ai stop",
            f"{prefix}ai off",
            f"{prefix}stop",
        }
        start_triggers = {
            config.secret_start_word,
            "ai start",
            "coddy start",
            f"{prefix}ai start",
            f"{prefix}ai on",
            f"{prefix}start",
        }

        group_stop_triggers = {
            config.secret_group_stop_word,
            "guruh stop",
            "guruhlar stop",
            "group stop",
            "ai group stop",
            "ai guruh stop",
            f"{prefix}group off",
            f"{prefix}group stop",
            f"{prefix}guruh off",
            f"{prefix}guruh stop",
        }
        group_start_triggers = {
            config.secret_group_start_word,
            "guruh start",
            "guruhlar start",
            "group start",
            "ai group start",
            "ai guruh start",
            f"{prefix}group on",
            f"{prefix}group start",
            f"{prefix}guruh on",
            f"{prefix}guruh start",
        }

        # Guruhlar avto-javobini boshqarish
        if lower_text in group_stop_triggers:
            config.group_reply_enabled = False
            await event.edit(
                "👥 **Guruhlar avto-javobi TO'XTATILDI (STOP)!**\n"
                "• AI endi guruhlardagi savollarga javob bermaydi.\n"
                "• Faqat shaxsiy xabarlarga (lichka) javob beradi.\n\n"
                "Qayta yoqish uchun: `guruh start` deb yozing."
            )
            return

        if lower_text in group_start_triggers:
            config.group_reply_enabled = True
            await event.edit(
                "👥 **Guruhlar avto-javobi ISHGA TUSHIRILDI (START)!**\n"
                "• AI guruhlardagi savollarga ham 5 soniya kutib javob beradi.\n"
                "• Agar 5 soniya ichida o'zingiz yozsangiz, AI to'xtaydi.\n\n"
                "O'chirish uchun: `guruh stop` deb yozing."
            )
            return

        if lower_text in stop_triggers:
            config.auto_reply_enabled = False
            await event.edit(
                "🔒 **XAVFSIZLIK: AI Agent to'liq to'xtatildi!**\n"
                "• Avto-javob: O'chirilgan (shaxsiy va guruhlar)\n"
                "• Barcha xabarlar faqat siz tomondan qo'lda boshqariladi.\n\n"
                "Qayta faollashtirish uchun: `ai start` deb yozing."
            )
            return

        if lower_text in start_triggers:
            config.auto_reply_enabled = True
            await event.edit(
                "🔓 **XAVFSIZLIK: AI Agent qayta faollashtirildi!**\n"
                "• Avto-javob: Yoqilgan\n"
                "• O'quvchilar xabarlariga 120B AI yordam berishni boshladi."
            )
            return

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
            group_status = "🟢 Yoqilgan" if config.group_reply_enabled else "🔴 O'chirilgan"
            active_chats = memory_service.total_active_chats()
            active_model = f"Groq ({config.groq_model})" if (config.groq_api_keys or config.groq_api_key) else f"Gemini ({config.gemini_model})"
            status_text = (
                "📊 **coddyHelper Tizim Holati**\n\n"
                f"- **Shaxsiy xabarlar (Lichka):** {auto_status}\n"
                f"- **Guruhlarda javob berish:** {group_status}\n"
                f"- **AI Modeli:** `{active_model}`\n"
                f"- **Kutish vaqti:** {config.mentor_wait_seconds} soniya\n"
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
                "**Boshqaruv (Maxfiy buyruqlar):**\n"
                "- `ai stop` / `ai start` — AI avto-javobini to'liq to'xtatish / yoqish\n"
                "- `guruh start` / `guruh stop` — Guruhlarga javob berishni yoqish / to'xtatish\n\n"
                "**Qo'shimcha komandalar:**\n"
                f"- `{prefix}ai <matn>` — Tezkor AI javobini olish\n"
                f"- `reply + {prefix}ai` — Xabarni tahlil qilish yoki unga javob yozish\n"
                f"- `{prefix}status` — Tizim va xotira holatini ko'rish\n"
                f"- `{prefix}clear` — Joriy chatdagi suhbat tarixini o'chirish\n"
                f"- `{prefix}help` — Ushbu yordam oynasini ko'rsatish"
            )
            await event.edit(help_text)
            return
