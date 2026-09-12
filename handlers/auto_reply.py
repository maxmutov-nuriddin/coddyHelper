"""
Kelgan shaxsiy xabarlarga avtomatik AI javob qaytarish logikasi.
Mentor ustuvorligi (Human-First): Agar mentor 5 soniya ichida o'zi yozsa, AI aralashmaydi.
"""

import asyncio
import logging
import time
from telethon import TelegramClient, events
from config import config
from services.ai_service import ai_service
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

# Kutilayotgan AI vazifalari va mentorning oxirgi faollik vaqti
PENDING_TASKS: dict[int, asyncio.Task] = {}
LAST_MENTOR_ACTIVITY: dict[int, float] = {}
LAST_REPLY_TIME: dict[int, float] = {}
MIN_INTERVAL_SECONDS = 2.0


def register_auto_reply_handlers(client: TelegramClient) -> None:
    my_id = None

    async def get_my_id() -> int:
        nonlocal my_id
        if my_id is None:
            me = await client.get_me()
            my_id = me.id
        return my_id

    # -----------------------------------------------------------
    # 1. Mentor o'zi xabar yuborganini kuzatish (Outgoing)
    # -----------------------------------------------------------
    @client.on(events.NewMessage(outgoing=True))
    async def on_mentor_message(event: events.NewMessage.Event):
        chat_id = event.chat_id
        LAST_MENTOR_ACTIVITY[chat_id] = time.time()

        # Agar ushbu chat uchun AI javob kutayotgan bo'lsa, darhol bekor qilish
        if chat_id in PENDING_TASKS and not PENDING_TASKS[chat_id].done():
            PENDING_TASKS[chat_id].cancel()
            logger.info("Mentor o'zi xabar yozdi [%s], AI kutish vazifasi bekor qilindi.", chat_id)

    # -----------------------------------------------------------
    # 2. Mentor yozishni boshlaganini (typing) kuzatish
    # -----------------------------------------------------------
    @client.on(events.UserUpdate)
    async def on_user_typing(event: events.UserUpdate.Event):
        try:
            if getattr(event, "typing", False):
                self_id = await get_my_id()
                if event.user_id == self_id:
                    chat_id = event.chat_id
                    LAST_MENTOR_ACTIVITY[chat_id] = time.time()
                    if chat_id in PENDING_TASKS and not PENDING_TASKS[chat_id].done():
                        PENDING_TASKS[chat_id].cancel()
                        logger.info("Mentor yozmoqda (typing) [%s], AI bekor qilindi.", chat_id)
        except Exception:
            pass

    # -----------------------------------------------------------
    # 3. Kelgan xabarni qabul qilish va 5 soniya kutish
    # -----------------------------------------------------------
    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming_message(event: events.NewMessage.Event):
        if not config.auto_reply_enabled:
            return

        if not event.is_private:
            return

        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return

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

        # Flood himoyasi
        now = time.time()
        last_time = LAST_REPLY_TIME.get(sender_id, 0.0)
        if now - last_time < MIN_INTERVAL_SECONDS:
            logger.info("Foydalanuvchi %s uchun flood himoyasi faollashdi, kutilmoqda.", sender_id)
            return

        LAST_REPLY_TIME[sender_id] = now

        # Agar oldinroq ushbu chat uchun kutilayotgan vazifa bo'lsa, bekor qilamiz
        if sender_id in PENDING_TASKS and not PENDING_TASKS[sender_id].done():
            PENDING_TASKS[sender_id].cancel()

        # Agar xabar reply qilingan bo'lsa
        reply_context = None
        if event.is_reply:
            parent = await event.get_reply_message()
            if parent and parent.text:
                reply_context = parent.text

        async def process_delayed_reply():
            try:
                wait_sec = config.mentor_wait_seconds or 5.0
                logger.info(
                    "Yangi xabar [%s]. Mentor yozishini %s soniya kutamiz...",
                    sender_id,
                    wait_sec,
                )
                await asyncio.sleep(wait_sec)

                # 5 soniya o'tdi: tekshiramiz, mentor o'zi yozdimi?
                if time.time() - LAST_MENTOR_ACTIVITY.get(sender_id, 0.0) < wait_sec:
                    logger.info("Mentor o'zi javob yozgan ekan [%s]. AI aralashmadi.", sender_id)
                    return

                if not config.auto_reply_enabled:
                    return

                logger.info("5 soniya ichida mentor yozmadi. AI ishga kirishmoqda [%s]", sender_id)

                # Telegram'da "yozmoqda..." (typing) animatsiyasini ko'rsatish
                async with client.action(event.chat_id, "typing"):
                    # Agar xotirada suhbat tarixi kam bo'lsa, Telegram'dagi oxirgi xabarlarni sinxronlash
                    if len(memory_service.get_history(sender_id)) < 3:
                        try:
                            past_messages = await client.get_messages(event.chat_id, limit=8)
                            for pm in reversed(past_messages[1:]):
                                if pm.text and pm.text.strip():
                                    r = "model" if pm.out else "user"
                                    memory_service.add_message(
                                        chat_id=sender_id, role=r, content=pm.text.strip()
                                    )
                        except Exception as hist_err:
                            logger.debug("Telegram chat tarixini o'qishda ogohlantirish: %s", hist_err)

                    # Agar rasm bo'lsa, yuklab olish
                    image_bytes = None
                    if has_photo:
                        image_bytes = await event.message.download_media(bytes)

                    # AI javobini olish
                    answer = await ai_service.generate_reply(
                        chat_id=sender_id,
                        user_message=message_text,
                        reply_to_context=reply_context,
                        image_bytes=image_bytes,
                    )

                    # Yakuniy tekshiruv: agar shu daqiqada mentor yozib qolgan bo'lsa, yubormaslik
                    if time.time() - LAST_MENTOR_ACTIVITY.get(sender_id, 0.0) < 2.0:
                        logger.info("Mentor so'nggi daqiqada yozdi, AI javobi yuborilmadi.")
                        return

                    # Javobni yuborish
                    await event.reply(answer)
                    logger.info("Foydalanuvchi %s ga AI javobi yuborildi.", sender_id)

                    # Mentorga yo'naltirish (Eskalyatsiya)
                    if getattr(answer, "escalation", None):
                        sender_name = getattr(sender, "first_name", "") or "Noma'lum"
                        if getattr(sender, "last_name", None):
                            sender_name += f" {sender.last_name}"
                        sender_user = (
                            f"@{sender.username}" if getattr(sender, "username", None) else "Mavjud emas"
                        )

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

            except asyncio.CancelledError:
                logger.info("AI kutish vazifasi bekor qilindi (Mentor yozdi) [%s].", sender_id)
            except Exception as e:
                logger.exception("Avto-javob berishda xatolik yuz berdi: %s", e)
            finally:
                if PENDING_TASKS.get(sender_id) is asyncio.current_task():
                    PENDING_TASKS.pop(sender_id, None)

        # 5 soniyalik vazifani boshlash
        task = asyncio.create_task(process_delayed_reply())
        PENDING_TASKS[sender_id] = task
