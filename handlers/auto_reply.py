"""
Kelgan shaxsiy xabarlarga avtomatik AI javob qaytarish logikasi
"""

import asyncio
import logging
import time
from telethon import TelegramClient, events
from config import config
from services.ai_service import ai_service

logger = logging.getLogger(__name__)

# Foydalanuvchilar bo'yicha spam/flood himoyasi (so'nggi javob berilgan vaqt)
LAST_REPLY_TIME: dict[int, float] = {}
MIN_INTERVAL_SECONDS = 2.0  # Bir foydalanuvchiga ketma-ket javob berish orasidagi minimal tanaffus


def register_auto_reply_handlers(client: TelegramClient) -> None:
    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming_message(event: events.NewMessage.Event):
        # 1. Avto-javob funksiyasi yoqilganligini tekshirish
        if not config.auto_reply_enabled:
            return

        # 2. Faqat shaxsiy (DM / Lichka) xabarlar uchun ishlash
        if not event.is_private:
            return

        # 3. Yuboruvchi ma'lumotlarini olish va botlarni inkor qilish
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return

        # 4. Matn yoki rasm/skrinshot mavjudligini tekshirish
        message_text = event.raw_text or event.message.message or ""
        has_photo = bool(
            event.message.photo
            or (
                event.message.document
                and event.message.file
                and getattr(event.message.file, "mime_type", "").startswith("image/")
            )
        )

        if not message_text.strip() and not has_photo:
            return

        sender_id = event.sender_id or event.chat_id

        # 5. Flood himoyasi
        now = time.time()
        last_time = LAST_REPLY_TIME.get(sender_id, 0.0)
        if now - last_time < MIN_INTERVAL_SECONDS:
            logger.info("Foydalanuvchi %s uchun flood himoyasi faollashdi, kutilmoqda.", sender_id)
            return

        LAST_REPLY_TIME[sender_id] = now

        # Agar xabar biror boshqa xabarga reply qilingan bo'lsa
        reply_context = None
        if event.is_reply:
            parent = await event.get_reply_message()
            if parent and parent.text:
                reply_context = parent.text

        logger.info("Yangi xabar keldi [%s] (Rasm: %s): %s", sender_id, has_photo, message_text[:50])

        try:
            # Telegram'da "yozmoqda..." (typing) animatsiyasini ko'rsatish
            async with client.action(event.chat_id, "typing"):
                # Agar rasm bo'lsa, xotiraga yuklab olish
                image_bytes = None
                if has_photo:
                    image_bytes = await event.message.download_media(bytes)

                # AI javobini olish (matn + rasm)
                answer = await ai_service.generate_reply(
                    chat_id=sender_id,
                    user_message=message_text,
                    reply_to_context=reply_context,
                    image_bytes=image_bytes,
                )

                # Javobni yuborish
                await event.reply(answer)
                logger.info("Foydalanuvchi %s ga AI javobi yuborildi.", sender_id)

                # 6. Agar mentor aralashuvi lozim bo'lsa (Eskalyatsiya)
                if getattr(answer, "escalation", None):
                    sender_name = getattr(sender, "first_name", "") or "Noma'lum"
                    if getattr(sender, "last_name", None):
                        sender_name += f" {sender.last_name}"
                    sender_user = f"@{sender.username}" if getattr(sender, "username", None) else "Mavjud emas"

                    alert_text = (
                        "🚨 **O'quvchi murojaati (Mentor aralashuvi kerak):**\n\n"
                        f"👤 **O'quvchi:** {sender_name} ({sender_user})\n"
                        f"🆔 **ID:** `{sender_id}`\n\n"
                        f"❓ **O'quvchi yozgan xabar:**\n\"{message_text}\"\n\n"
                        f"📋 **AI Xulosasi:**\n{answer.escalation}"
                    )

                    try:
                        target = config.escalation_chat
                        if target.isdigit() or (target.startswith("-") and target[1:].isdigit()):
                            target = int(target)
                        await client.send_message(target, alert_text)
                        logger.info("Eskalyatsiya xabari '%s' ga yetkazildi.", config.escalation_chat)
                    except Exception as exc:
                        logger.error("Eskalyatsiya xabarini yetkazishda xatolik: %s", exc)

        except Exception as e:
            logger.exception("Avto-javob berishda xatolik yuz berdi: %s", e)
