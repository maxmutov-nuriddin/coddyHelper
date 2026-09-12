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


def is_escalation_chat(chat_id: int) -> bool:
    target = str(config.escalation_chat).strip()
    c_id = str(chat_id).strip()
    if c_id == target:
        return True
    c_norm = c_id.replace("-100", "-")
    t_norm = target.replace("-100", "-")
    return c_norm == t_norm


def is_relevant_group_message(
    message_text: str, has_photo: bool, has_voice: bool, reply_to_me: bool
) -> bool:
    if has_photo or has_voice or reply_to_me:
        return True

    text = message_text.lower().strip()
    if not text:
        return False

    if "?" in text:
        return True

    code_indicators = [
        "error", "exception", "traceback", "syntaxerror",
        "indexerror", "keyerror", "nameerror", "typeerror", "valueerror",
    ]
    if any(ci in text for ci in code_indicators):
        return True

    help_keywords = [
        "ustoz", "mentor", "yordam", "ishlamayapti", "xato",
        "qanday", "tushunmadim", "vazifa", "kodim", "masala",
        "lms", "tekshir", "kod", "python", "def ", "class ",
    ]
    if any(kw in text for kw in help_keywords):
        return True

    casual_words = {
        "salom", "assalomu alaykum", "va alaykum assalom", "rahmat",
        "ok", "ha", "yoq", "yo'q", "kettik", "bopti", "hop", "xop",
    }
    if len(text) > 15 and text not in casual_words:
        return True

    return False


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

        is_private = event.is_private
        is_group = event.is_group or event.is_channel

        if not is_private and not is_group:
            return

        # Agar guruh bo'lsa, maxsus tekshiruvlar:
        if is_group:
            if not config.group_reply_enabled:
                return

            # "Vazifalar" (Eskalyatsiya) guruhi bo'lsa, aslo javob qaytarmaymiz
            if is_escalation_chat(event.chat_id):
                return

        # Mentorning o'z xabari bo'lsa o'tkazib yuborish
        if event.out:
            return

        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return

        sender_id = event.sender_id or event.chat_id

        # Bloklangan (ignore) foydalanuvchini tekshirish
        if memory_service.is_user_ignored(sender_id):
            logger.info("Foydalanuvchi %s bloklanganlar (ignored) ro'yxatida. AI javob bermaydi.", sender_id)
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
        has_voice = bool(
            getattr(event.message, "voice", False)
            or (
                event.message.document
                and event.message.file
                and getattr(event.message.file, "mime_type", "").startswith("audio/")
            )
        )

        if not message_text.strip() and not has_photo and not has_voice:
            return

        # Agar xabar reply qilingan bo'lsa
        reply_context = None
        reply_to_me = False
        if event.is_reply:
            parent = await event.get_reply_message()
            if parent:
                if parent.text:
                    reply_context = parent.text
                self_id = await get_my_id()
                if parent.sender_id == self_id:
                    reply_to_me = True

        # Guruhlarda faqat aniq savol yoki yordam so'rovlariga javob berish
        if is_group and not is_relevant_group_message(message_text, has_photo, has_voice, reply_to_me):
            return

        task_key = event.chat_id
        sender_id = event.sender_id or event.chat_id

        # Flood himoyasi
        now = time.time()
        last_time = LAST_REPLY_TIME.get(task_key, 0.0)
        if now - last_time < MIN_INTERVAL_SECONDS:
            logger.info("Chat %s uchun flood himoyasi faollashdi, kutilmoqda.", task_key)
            return

        LAST_REPLY_TIME[task_key] = now

        # Agar oldinroq ushbu chat uchun kutilayotgan vazifa bo'lsa, bekor qilamiz
        if task_key in PENDING_TASKS and not PENDING_TASKS[task_key].done():
            PENDING_TASKS[task_key].cancel()

        async def process_delayed_reply():
            try:
                wait_sec = config.mentor_wait_seconds or 5.0
                logger.info(
                    "Yangi xabar [%s]. Mentor yozishini %s soniya kutamiz...",
                    task_key,
                    wait_sec,
                )
                await asyncio.sleep(wait_sec)

                # 5 soniya o'tdi: tekshiramiz, mentor o'zi yozdimi?
                if time.time() - LAST_MENTOR_ACTIVITY.get(task_key, 0.0) < wait_sec:
                    logger.info("Mentor o'zi javob yozgan ekan [%s]. AI aralashmadi.", task_key)
                    return

                if not config.auto_reply_enabled:
                    return
                if is_group and not config.group_reply_enabled:
                    return

                logger.info("5 soniya ichida mentor yozmadi. AI ishga kirishmoqda [%s]", task_key)

                # Telegram'da "yozmoqda..." (typing) animatsiyasini ko'rsatish
                async with client.action(event.chat_id, "typing"):
                    # Agar xotirada suhbat tarixi kam bo'lsa, Telegram'dagi oxirgi xabarlarni sinxronlash
                    if len(memory_service.get_history(task_key)) < 3:
                        try:
                            past_messages = await client.get_messages(event.chat_id, limit=8)
                            for pm in reversed(past_messages[1:]):
                                if pm.text and pm.text.strip():
                                    r = "model" if pm.out else "user"
                                    memory_service.add_message(
                                        chat_id=task_key, role=r, content=pm.text.strip()
                                    )
                        except Exception as hist_err:
                            logger.debug("Telegram chat tarixini o'qishda ogohlantirish: %s", hist_err)

                    # Agar ovozli xabar bo'lsa, Whisper orqali matnga o'girish
                    input_text = message_text
                    if has_voice and not input_text.strip():
                        try:
                            audio_bytes = await event.message.download_media(bytes)
                            if audio_bytes:
                                transcribed = await ai_service.transcribe_audio(audio_bytes)
                                if transcribed:
                                    input_text = f"[Ovozli xabar]: {transcribed}"
                                    logger.info("Ovozli xabar matnga o'girildi [%s]: %s", task_key, transcribed[:80])
                        except Exception as v_err:
                            logger.warning("Ovozli xabarni tahlil qilishda xatolik: %s", v_err)

                    if not input_text.strip() and not has_photo:
                        return

                    # Agar rasm bo'lsa, yuklab olish
                    image_bytes = None
                    if has_photo:
                        image_bytes = await event.message.download_media(bytes)

                    # AI javobini olish
                    answer = await ai_service.generate_reply(
                        chat_id=task_key,
                        user_message=input_text,
                        reply_to_context=reply_context,
                        image_bytes=image_bytes,
                    )

                    # Yakuniy tekshiruv: agar shu daqiqada mentor yozib qolgan bo'lsa, yubormaslik
                    if time.time() - LAST_MENTOR_ACTIVITY.get(task_key, 0.0) < 2.0:
                        logger.info("Mentor so'nggi daqiqada yozdi, AI javobi yuborilmadi.")
                        return

                    # Javobni yuborish (reply tarzida)
                    await event.reply(answer)
                    logger.info("Chat %s ga AI javobi yuborildi.", task_key)

                    # Mentorga yo'naltirish (Eskalyatsiya)
                    if getattr(answer, "escalation", None):
                        sender_name = getattr(sender, "first_name", "") or "Noma'lum"
                        if getattr(sender, "last_name", None):
                            sender_name += f" {sender.last_name}"
                        sender_user = (
                            f"@{sender.username}" if getattr(sender, "username", None) else "Mavjud emas"
                        )

                        chat_source = "Shaxsiy xabar (Lichka)"
                        if is_group:
                            try:
                                chat_entity = await event.get_chat()
                                chat_source = f"Guruh: {getattr(chat_entity, 'title', 'Guruh')}"
                            except Exception:
                                chat_source = f"Guruh ID: `{event.chat_id}`"

                        alert_text = (
                            "🚨 **O'quvchi murojaati (Mentor aralashuvi kerak):**\n\n"
                            f"📍 **Manba:** {chat_source}\n"
                            f"👤 **O'quvchi:** {sender_name} ({sender_user})\n"
                            f"🆔 **ID:** `{sender_id}`\n\n"
                            f"❓ **O'quvchi xabari:**\n\"{input_text}\"\n\n"
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
                logger.info("AI kutish vazifasi bekor qilindi (Mentor yozdi) [%s].", task_key)
            except Exception as e:
                logger.exception("Avto-javob berishda xatolik yuz berdi: %s", e)
            finally:
                if PENDING_TASKS.get(task_key) is asyncio.current_task():
                    PENDING_TASKS.pop(task_key, None)

        # 5 soniyalik vazifani boshlash
        task = asyncio.create_task(process_delayed_reply())
        PENDING_TASKS[task_key] = task
