"""
Kelgan shaxsiy xabarlarga avtomatik AI javob qaytarish logikasi.
Mentor ustuvorligi (Human-First): Agar mentor 5 soniya ichida o'zi yozsa, AI aralashmaydi.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from telethon import TelegramClient, events
from config import config, is_escalation_chat
from services.ai_service import ai_service
from services.memory_service import memory_service
from services.telegram_agent_service import (
    execute_agent_action,
    list_recent_chats,
    get_student_common_groups,
    check_group_schedule_and_announcements,
    is_russian_text,
)

logger = logging.getLogger(__name__)

# Kutilayotgan AI vazifalari va mentorning oxirgi faollik vaqti
PENDING_TASKS: dict[object, asyncio.Task] = {}
LAST_MENTOR_ACTIVITY: dict[int, float] = {}
LAST_REPLY_TIME: dict[int, float] = {}
BOT_SENT_MESSAGE_IDS: set[int] = set()
CURRENT_SENDING_CHATS: set[int] = set()
MIN_INTERVAL_SECONDS = 2.0
RECENT_ACTIVITY_LOGS: list[str] = []


def log_activity(msg: str) -> None:
    from zoneinfo import ZoneInfo
    now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%H:%M:%S")
    entry = f"[{now_str}] {msg}"
    RECENT_ACTIVITY_LOGS.append(entry)
    if len(RECENT_ACTIVITY_LOGS) > 30:
        RECENT_ACTIVITY_LOGS.pop(0)

# Xavfsizlik: Spamerlar uchun limit va fayl hajmi
USER_REQUEST_TIMESTAMPS: dict[int, list[float]] = {}
MAX_USER_REQUESTS_PER_MINUTE = 6
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

DANGEROUS_EXTS = {
    ".apk", ".xapk", ".apkm", ".exe", ".msi", ".bat",
    ".cmd", ".scr", ".com", ".vbs", ".jar", ".bin",
    ".dmg", ".iso", ".deb", ".rpm"
}


def is_token_abuse(text: str) -> bool:
    """
    AI tokenlarini qasddan sarflash, tugatish yoki trollik urinishlarini aniqlaydi.
    Dasturlashdagi JWT token, Bot token yoki Auth mavzularini aslo aralashtirmaydi.
    """
    t = text.lower().strip()
    if not t:
        return False

    # Dasturlash mavzulari (soxta pozitivlardan himoya):
    dev_exceptions = [
        "jwt", "csrf", "botfather", "bearer", "access token",
        "refresh token", "auth token", "telegram token", "bot tokeni", "botning tokeni", "api tokeni"
    ]
    if any(dev in t for dev in dev_exceptions):
        return False

    abuse_triggers = [
        r"\btoken(?:ing|ingni|larni|laringni|larini)?\s+(?:\w+\s+){0,3}(?:ishlat\w*|tugat\w*|sarfla\w*|yoq\w*|yondir\w*|erit\w*)",
        r"\b(?:ishlat\w*|tugat\w*|sarfla\w*|yoq\w*|yondir\w*)\s+(?:\w+\s+){0,3}token",
        r"\b(?:qancha|nechta)\s+(?:\w+\s+){0,2}token(?:ing)?\b",
        r"\btoken(?:ing)?\s+(?:\w+\s+){0,2}(?:qancha|nechta|qoldi|bormi|tugasin|yetadimi)\b",
        r"\blimit(?:ini|ingni)?\s+(?:\w+\s+){0,2}(?:tugat\w*|yoq\w*)\b",
        r"\b(?:слить|сжечь|потрать\w*|трать\w*|закончи\w*)\s+(?:\w+\s+){0,3}токен",
        r"\bтокен(?:ы|ов)?\s+(?:\w+\s+){0,3}(?:потрать\w*|слить\w*|сжечь\w*|закончи\w*)\b",
        r"\bсколько\s+(?:\w+\s+){0,2}токен(?:ов)?\b",
        r"\b(?:cheksiz|to'xtamasdan)\s+(?:yoz\w*|davom et\w*)\b",
        r"\bбесконечный\s+текст\b",
    ]
    return any(re.search(pat, t, re.I) for pat in abuse_triggers)


def is_absence_message(text: str) -> bool:
    """
    O'quvchining darsga kela olmasligi, kechikishi yoki dars qoldirishi haqidagi xabarni aniqlaydi.
    """
    t = text.lower().strip()
    if not t:
        return False

    absence_triggers = [
        # O'zbekcha darsga kelolmaslik / bormaslik / kechikish
        r"\b(?:kelolmay\w*|kelomiman\w*|kelolmas\w*|kelomas\w*)\b",
        r"\b(?:borolmay\w*|boromiman\w*|borolmas\w*)\b",
        r"\b(?:bor\w*|kel\w*|chiq\w*)\s+(?:olmay\w*|bo['’`]?lmay\w*)\b",
        r"\b(?:qatnasholmay\w*|qatnasha\s+olmay\w*)\b",
        r"\b(?:bo['’`]?lolmay\w*|bo['’`]?la\s+olmay\w*)\b",
        r"\b(?:darsga|darsda)\s+(?:\w+\s+){0,2}(?:bormay\w*|kelmay\w*|bo['’`]?l\w*|qatnash\w*)\b",
        r"\b(?:darsni|dars)\s+(?:qoldir\w*|otkaz\w*|o'tkaz\w*)\b",
        r"\b(?:kasal\s+bo['’`]?lib|kasalman|tobim\s+yo['’`]?q|mazam\s+yo['’`]?q|mazam\s+bo['’`]?lmayapti)\b",
        r"\b(?:kechikib\w*|kechikaman\w*|kech\s+qolaman\w*|kech\s+boraman\w*)\b",
        # Ruscha
        r"\b(?:не\s+смогу\s+(?:\w+\s+){0,2}(?:прийти|быть|присутствовать)|не\s+приду|не\s+буду\s+(?:\w+\s+){0,2}уроке)\b",
        r"\b(?:пропущу|пропускаю)\s+(?:урок|занятие)\b",
        r"\b(?:заболел\w*|плохо\s+себя\s+чувствую)\b",
        r"\b(?:опоздаю|задержусь)\s*(?:на\s+урок)?\b",
    ]
    return any(re.search(pat, t, re.I) for pat in absence_triggers)


def is_schedule_query(text: str) -> bool:
    """
    O'quvchining bugun dars bo'lishi, soat nechada ekanligi, jadval yoki bayram sababli dars qoldirilgani haqidagi
    savollarini aniqlaydi.
    """
    t = text.lower().strip()
    if not t:
        return False

    schedule_triggers = [
        # O'zbekcha dars bo'ladimi / bormi / soat nechada
        r"\b(?:bugun|ertaga)?\s*dars\s+(?:bo['’`]?ladimi|bo['’`]?lar\s+ekanmi|bo['’`]?larmikan|bormi|bormi\s+yo['’`]?qmi)\b",
        r"\bdars\s+(?:bormi|bo['’`]?ladimi)\b",
        r"\bdars\s+soat\s+nechada\b",
        r"\bsoat\s+nechada\s+dars\b",
        r"\bdars\s+nechida\b",
        r"\bdars\s+qachon\b",
        r"\b(?:bugun|ertaga)\s+dars\s+bormi\b",
        r"\bbayram(?:da)?\s+(?:dars\s+bormi|dars\s+bo['’`]?ladimi)\b",
        r"\bdars\s+(?:qoldirildimi|bekor\s+qilindimi)\b",
        # Ruscha
        r"\b(?:сегодня|завтра)?\s*(?:есть\s+ли\s+урок|есть\s+урок|будет\s+ли\s+урок|урок\s+будет|будут\s+ли\s+уроки)\b",
        r"\bво\s+сколько\s+(?:сегодня\s+)?(?:урок|занятие)\b",
        r"\bкогда\s+(?:урок|занятие)\b",
        r"\b(?:урок|занятия)\s+(?:отменили|будут|состоятся)\b",
        r"\b(?:отменили|отменен|отменяется)\s+(?:ли\s+)?(?:урок\w*|заняти\w*)\b",
        r"\bпраздник\s+(?:урок\s+будет|будут\s+ли\s+уроки)\b",
    ]
    return any(re.search(pat, t, re.I) for pat in schedule_triggers)



def extract_safe_zip_content(file_bytes: bytes, zip_name: str) -> tuple[str | None, str | None, str | None]:
    """
    ZIP arxivini faqat RAM xotirasida xavfsiz tekshiradi va kod fayllarini ajratib oladi.
    Qaytaradi: (file_name, file_text, error_message)
    """
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            namelist = zf.namelist()
            if not namelist:
                return None, None, "⚠️ ZIP arxiv bo'sh."

            # 1. Xavfli fayllar (.apk, .exe, .bat ...) skaneri
            for fn in namelist:
                fn_lower = fn.lower()
                fn_ext = Path(fn_lower).suffix
                if fn_ext in DANGEROUS_EXTS or fn_lower.endswith(
                    (".apk", ".xapk", ".apkm", ".exe", ".msi", ".bat", ".cmd", ".scr", ".com", ".vbs", ".jar", ".bin")
                ):
                    return None, None, (
                        f"🛡 **Xavfsizlik Ogohlantirishi:**\n"
                        f"Ushbu `.zip` arxiv ichida xavfli yoki ruxsat etilmagan fayl (`{fn}`) aniqlandi!\n"
                        "Xavfsizlik talablariga muvofiq bunday arxivlar ochilmaydi va tahlil qilinmaydi.\n\n"
                        "Iltimos, faqat toza kod fayllarini (`.py`, `.js`, `.html`) yoki GitHub havolasini yuboring."
                    )

            # 2. Zip bomb va umumiy hajm himoyasi
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            if total_uncompressed > 25 * 1024 * 1024 or len(namelist) > 200:
                return None, None, (
                    "⚠️ **Arxiv hajmi juda katta:** Arxiv ichidagi fayllar hajmi (25 MB dan ortiq) yoki soni me'yordan oshdi. "
                    "Iltimos, keraksiz papkalarsiz (`venv` va hokazolarsiz) faqat asosiy kodni yuboring."
                )

            # 3. Kod fayllarini ajratib olish
            safe_code_extensions = {
                ".py", ".txt", ".html", ".css", ".js", ".ts",
                ".json", ".sql", ".java", ".c", ".cpp", ".md"
            }
            ignored_dirs = {
                "venv", ".venv", "__pycache__", "node_modules", ".git",
                ".idea", ".vscode", "dist", "build", "env"
            }

            extracted_parts = []
            files_count = 0
            max_files = 5

            def priority_key(name: str):
                base = Path(name).name.lower()
                if base in ("main.py", "app.py", "bot.py", "manage.py", "index.js", "server.py"):
                    return 0
                return 1

            sorted_names = sorted(namelist, key=priority_key)

            for fn in sorted_names:
                parts = Path(fn).parts
                if any(p.lower() in ignored_dirs for p in parts):
                    continue
                ext = Path(fn).suffix.lower()
                if ext in safe_code_extensions and not fn.endswith("/"):
                    try:
                        with zf.open(fn) as cf:
                            content_bytes = cf.read(3500)
                            content_str = content_bytes.decode("utf-8", errors="ignore")
                            if content_str.strip():
                                extracted_parts.append(f"--- Fayl: {fn} ---\n{content_str}")
                                files_count += 1
                                if files_count >= max_files:
                                    break
                    except Exception:
                        continue

            if not extracted_parts:
                return None, None, (
                    "ℹ️ Ushbu `.zip` arxiv ichida tahlil qilish uchun dasturlash kod fayllari (`.py`, `.html`, `.js`, ...) topilmadi."
                )

            summary = f"--- ZIP Arxiv: {zip_name} ---\n" + "\n\n".join(extracted_parts)
            return zip_name, summary, None

    except zipfile.BadZipFile:
        return None, None, "⚠️ ZIP arxiv buzilgan yoki noto'g'ri formatda."
    except Exception as e:
        logger.error("ZIP faylni ochishda xatolik: %s", e)
        return None, None, "⚠️ ZIP arxivni o'qishda xatolik yuz berdi."


def is_escalation_chat(chat_id: int) -> bool:
    c_id = str(chat_id).strip()
    # Vazifalar / Boshqaruv markazi guruhining ma'lum ID lari
    if c_id in ("-5388159517", "-1005388159517", "5388159517"):
        return True
    target = str(config.escalation_chat).strip()
    if c_id == target:
        return True
    c_norm = c_id.replace("-100", "-")
    t_norm = target.replace("-100", "-")
    return c_norm == t_norm


def is_relevant_group_message(
    message_text: str,
    has_photo: bool,
    has_voice: bool,
    has_doc_file: bool,
    has_github: bool,
    reply_to_me: bool,
    is_dangerous: bool = False,
    is_mentioned: bool = False,
) -> bool:
    # Rasmlar, ovozli xabarlar, kod fayllari, xavfli fayllar, GitHub linki yoki mentorga qaratilgan xabarlar
    if has_photo or has_voice or has_doc_file or has_github or reply_to_me or is_dangerous or is_mentioned:
        return True

    text = message_text.lower().strip()
    if not text:
        return False

    # Guruhda faqat bitta so'zdan iborat bildirishnomalarni o'tkazib yuborish (keraksiz xabar bo'lmasligi uchun)
    ignored_standalone = {
        "ok", "ha", "yoq", "yo'q", "rahmat", "raxmat", "tushunarli",
        "bopti", "hop", "xop", "+", "++", "+++", "spasibo", "thanks", "thx", "zo'r", "zor",
        "хорошо", "ладно", "понял", "понятно", "ок", "да", "нет", "ясно", "спасибо"
    }
    if text in ignored_standalone:
        return False

    # Qolgan barcha savollar, vazifalar, salomlar va so'rovlar qabul qilinadi
    return True


async def check_is_vazifalar_chat(event) -> bool:
    """Xabar 'Vazifalar' (Mentorning Shaxsiy Boshqaruv Markazi) guruhida ekanini aniqlaydi."""
    chat_id = event.chat_id
    if is_escalation_chat(chat_id):
        return True
    if str(chat_id).strip() in ("-5388159517", "-1005388159517", "5388159517"):
        return True
    try:
        if getattr(event, "client", None):
            me = await event.client.get_me()
            if chat_id == me.id:
                return True
    except Exception:
        pass
    try:
        chat = await event.get_chat()
        title = (getattr(chat, "title", "") or "").lower()
        if any(w in title for w in ("vazifalar", "vazifa", "markaz", "boshqaruv", "admin", "co-pilot", "copilot")):
            return True
    except Exception:
        pass
    return False



def register_auto_reply_handlers(client: TelegramClient) -> None:
    my_id = None

    async def get_my_id() -> int:
        nonlocal my_id
        if my_id is None:
            me = await client.get_me()
            my_id = me.id
        return my_id

    async def handle_vazifalar_chat(event: events.NewMessage.Event):
        """
        'Vazifalar' (Mentorning Shaxsiy Boshqaruv Markazi) guruhidagi
        matnli va ovozli muloqotni xuddi Web App kabi qayta ishlaydi.
        Mentor bu yerda AI Co-Pilot bilan erkin muloqot qiladi, ideyalar oladi,
        ovozli xabar yuborsa ovozli javob oladi, va Telegram amallarini bajaradi.
        DIQQAT: Faqat va faqat mentorning o'zi uchun ishlaydi!
        """
        chat_id = event.chat_id
        if event.message.id in BOT_SENT_MESSAGE_IDS or chat_id in CURRENT_SENDING_CHATS:
            BOT_SENT_MESSAGE_IDS.discard(event.message.id)
            return

        # 🔒 FAQAT MENTOR UCHUN ISHLASHI SHART:
        # Ushbu guruhda AI FAQAT MENTOR (Nuriddin aka) ning xabarlariga javob beradi!
        # Begona foydalanuvchilar yoki boshqa a'zolar yozsa, AI ularga ASLO javob qaytarmaydi.
        sender_id = event.sender_id
        my_user_id = await get_my_id()
        is_mentor = event.out or (sender_id == my_user_id) or (sender_id in (config.mentor_user_id, 8105823872))
        if not is_mentor:
            logger.info("Vazifalar guruhida (%s) begona a'zo (%s) yozdi. Faqat mentor uchun ishlashi sababli e'tiborsiz qoldirildi.", chat_id, sender_id)
            return

        CURRENT_SENDING_CHATS.add(chat_id)
        try:
            message_text = event.raw_text or event.message.message or ""
            has_voice = bool(
                event.message.voice
                or (
                    event.message.audio
                    and getattr(event.message.file, "mime_type", "").startswith("audio/")
                )
            )
            has_photo = bool(
                event.message.photo
                or (
                    event.message.document
                    and event.message.file
                    and getattr(event.message.file, "mime_type", "").startswith("image/")
                )
            )
            has_doc = bool(event.message.document and not has_photo and not has_voice)

            input_text = message_text.strip()

            # 1. Ovozli xabar bo'lsa, Whisper orqali matnga o'girish
            if has_voice and not input_text:
                try:
                    audio_bytes = await event.message.download_media(bytes)
                    if audio_bytes:
                        transcribed = await ai_service.transcribe_audio(audio_bytes)
                        if transcribed:
                            input_text = transcribed.strip()
                            log_activity(f"Vazifalar ovozi o'qildi: {input_text[:60]}")
                except Exception as v_err:
                    logger.error("Vazifalar ovozli xabarni o'qishda xatolik: %s", v_err)

            # 2. Hujjat yoki fayl bo'lsa
            file_name = None
            file_text = None
            if has_doc:
                try:
                    file_bytes = await event.message.download_media(bytes)
                    if file_bytes:
                        file_name = getattr(event.message.file, "name", "file.txt")
                        file_text = file_bytes.decode("utf-8", errors="ignore")
                except Exception as f_err:
                    logger.debug("Vazifalar faylini o'qishda ogohlantirish: %s", f_err)

            # 3. Rasm bo'lsa
            image_bytes = None
            if has_photo:
                try:
                    image_bytes = await event.message.download_media(bytes)
                except Exception as p_err:
                    logger.debug("Vazifalar rasmini yuklashda ogohlantirish: %s", p_err)

            if not input_text and not file_text and not image_bytes:
                return

            # 4. Telegram kontaktlar va guruhlar kontekstini olish (faqat zarur bo'lganda)
            chats_context = None
            lower_in = input_text.lower()
            needs_context = any(w in lower_in for w in ("guruh", "kontakt", "lichka", "chat", "xabar", "o'quvchi", "oquvchi", "kim", "qidir", "top"))
            if needs_context:
                try:
                    recent = await list_recent_chats(client, limit=10)
                    if recent:
                        chat_names = [f"{c['name']} ({c['type']})" for c in recent]
                        chats_context = f"Sizning Telegramingizdagi faol guruhlar va kontaktlar: {', '.join(chat_names)}"
                except Exception as c_err:
                    logger.debug("Chatlar kontekstini olishda xatolik: %s", c_err)

            # 5. AI Co-Pilot javobini yaratish (Admin / Co-Pilot rejimida)
            raw_reply = await ai_service.generate_reply(
                chat_id=config.mentor_user_id,
                user_message=input_text,
                reply_to_context=chats_context,
                image_bytes=image_bytes,
                file_name=file_name,
                file_text=file_text,
                is_admin_mode=True,
            )

            # 6. Telegram Action amallarini bajarish (guruh statistikasi, kontakt qidirish, xabar yuborish)
            final_reply = await execute_agent_action(str(raw_reply), client, input_text)

            if final_reply != str(raw_reply):
                # Web App'dagi kabi xotiradagi oxirgi xabarni amaliy natija bilan yangilash:
                memory_service.update_last_message(config.mentor_user_id, final_reply)

            # 7. Javobni yuborish (agar ovozli bo'lsa, ovozli javob ham jo'natish)
            voice_reply_enabled = memory_service.get_setting("voice_reply_enabled", "true").lower() == "true"
            if (has_voice or "ovozli" in input_text.lower()) and voice_reply_enabled:
                try:
                    from services.tts_service import generate_voice_message
                    voice_path = await generate_voice_message(str(final_reply))
                    if voice_path and voice_path.exists():
                        sent_voice = await event.reply(file=str(voice_path), voice_note=True)
                        if sent_voice:
                            BOT_SENT_MESSAGE_IDS.add(sent_voice.id)
                        voice_path.unlink(missing_ok=True)
                except Exception as v_send_err:
                    logger.warning("Vazifalarda ovozli javob yuborishda ogohlantirish: %s", v_send_err)

            sent_msg = await event.reply(final_reply)
            if sent_msg:
                BOT_SENT_MESSAGE_IDS.add(sent_msg.id)
            log_activity(f"Vazifalar AI javobi berildi: {str(final_reply)[:50]}")

        except Exception as e:
            logger.error("Vazifalar xabarini qayta ishlashda xatolik: %s", e)
        finally:
            CURRENT_SENDING_CHATS.discard(chat_id)

    # -----------------------------------------------------------
    # 1. Mentor o'zi xabar yuborganini kuzatish (Outgoing)
    # -----------------------------------------------------------
    @client.on(events.NewMessage(outgoing=True))
    async def on_mentor_message(event: events.NewMessage.Event):
        # Agar bu botning o'zi hozir yuborayotgan xabari bo'lsa, e'tiborsiz qoldiramiz
        if event.message.id in BOT_SENT_MESSAGE_IDS or event.chat_id in CURRENT_SENDING_CHATS:
            BOT_SENT_MESSAGE_IDS.discard(event.message.id)
            return

        chat_id = event.chat_id
        is_vazifalar = await check_is_vazifalar_chat(event)

        # Agar bu "Vazifalar" guruhi bo'lsa:
        # Mentor shaxsiy AI Co-Pilot bilan muloqot qilmoqda (matn yoki ovozli xabar).
        if is_vazifalar:
            await handle_vazifalar_chat(event)
            return

        LAST_MENTOR_ACTIVITY[chat_id] = time.time()

        # Ushbu chatdagi barcha kutilayotgan AI vazifalarini bekor qilish
        for k in list(PENDING_TASKS.keys()):
            if k == chat_id or (isinstance(k, tuple) and k[0] == chat_id):
                task = PENDING_TASKS.pop(k, None)
                if task and not task.done():
                    task.cancel()
        logger.info("Mentor o'zi xabar yozdi [%s], AI kutish vazifalari bekor qilindi.", chat_id)

    # -----------------------------------------------------------
    # 3. Kelgan xabarni qabul qilish va 5 soniya kutish
    # -----------------------------------------------------------
    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming_message(event: events.NewMessage.Event):
        if not config.auto_reply_enabled:
            return

        if event.message.id in BOT_SENT_MESSAGE_IDS or event.chat_id in CURRENT_SENDING_CHATS:
            BOT_SENT_MESSAGE_IDS.discard(event.message.id)
            return

        is_private = event.is_private
        is_group = event.is_group or event.is_channel

        if not is_private and not is_group:
            return

        is_vazifalar = await check_is_vazifalar_chat(event)

        # Agar bu "Vazifalar" guruhi bo'lsa, darhol AI Co-Pilot bilan qayta ishlaymiz:
        if is_vazifalar:
            await handle_vazifalar_chat(event)
            return

        # Agar guruh bo'lsa, maxsus tekshiruvlar:
        if is_group:
            if not config.group_reply_enabled:
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
        clean_msg = message_text.strip().lower()
        if clean_msg in ("panel", "app", "admin", "webapp", ".panel", ".app", ".admin", "/panel", "/app", "/admin"):
            return

        # 🛡 XAVFSIZLIK: Telegram hisobini buzish, tasdiqlash kodi so'rash va phishing urinishlari
        phishing_patterns = [
            "kod keldi", "kodni ayt", "kodini ayt", "kodni ber", "kodini ber",
            "kodni tashla", "tasdiqlash kodi", "tasdiqlash kodini",
            "sms kod", "sms kodi", "sms keldi", "kelgan kod",
            "telegramingizga kod", "telegramingizga kelgan", "telegramga kod",
            "ulab ber", "ulab bering", "telegramini ulab", "telegramingizni ulab",
            "akkauntni ulab", "profilni ulab", "login code", "login kodi",
            "kirish kodi", "session fayl", "string_session"
        ]
        if any(pat in clean_msg for pat in phishing_patterns):
            s_name = getattr(sender, "first_name", "") or "Noma'lum"
            if getattr(sender, "last_name", None):
                s_name += f" {sender.last_name}"
            s_user = f"@{sender.username}" if getattr(sender, "username", None) else "Mavjud emas"
            
            memory_service.ignore_user(sender_id, getattr(sender, "username", "") or "", reason="Telegram kodi so'rash / hisobni buzish urinishi")
            log_activity(f"🚨 BUZIB KIRISH URINISHI! {s_name} ({s_user}) ID:{sender_id} butunlay bloklandi.")
            logger.warning("🚨 Phishing / Hisobni buzish urinishi aniqlandi! Foydalanuvchi %s bloklandi.", sender_id)
            
            alert = (
                "🚨 **XAVFSIZLIK OGOHLANTIRISHI: HISOBGA HUJUM / KOD SO'RASH ANIQLANDI!**\n\n"
                f"👤 **Foydalanuvchi:** {s_name} ({s_user})\n"
                f"🆔 **ID:** `{sender_id}`\n\n"
                f"💬 **Xabari:** \"{message_text}\"\n\n"
                "🛡 **Ko'rilgan chora:** Ushbu foydalanuvchi **butunlay va abadiy bloklandi** (ignored_users). Chatni o'chirgan taqdirda ham baza uni unutmaydi va bot unga boshqa aslo javob bermaydi."
            )
            try:
                target = config.escalation_chat
                if str(target).isdigit() or (str(target).startswith("-") and str(target)[1:].isdigit()):
                    target = int(target)
                await client.send_message(target, alert)
            except Exception as esc_err:
                logger.error("Xavfsizlik ogohlantirishini yuborishda xatolik: %s", esc_err)

            await event.reply("⛔️ **Xavfsizlik tizimi:** Xavfsizlik qoidalariga ko'ra hisob ma'lumotlari, tasdiqlash kodlari yoki sessiyalarni so'rash qat'iyan man etiladi. Hisobingiz butunlay bloklandi.")
            return

        # 🛡 XAVFSIZLIK: Tokenlarni qasddan sarflash, sun'iy cheksiz so'rovlar yoki trollik urinishlari
        is_admin_user = (sender_id in (config.mentor_user_id, 8105823872)) or is_escalation_chat(event.chat_id)
        if not is_admin_user and is_token_abuse(clean_msg):
            s_name = getattr(sender, "first_name", "") or "Noma'lum"
            if getattr(sender, "last_name", None):
                s_name += f" {sender.last_name}"
            s_user = f"@{sender.username}" if getattr(sender, "username", None) else "Mavjud emas"

            memory_service.ignore_user(sender_id, getattr(sender, "username", "") or "", reason="Tokenlarni qasddan sarflash / trollik urinishi")
            log_activity(f"⛔️ TOKEN ABUSE! {s_name} ({s_user}) ID:{sender_id} butunlay bloklandi.")
            logger.warning("🚨 Tokenlarni qasddan sarflash urinishi aniqlandi! Foydalanuvchi %s bloklandi.", sender_id)

            alert = (
                "🚨 **XAVFSIZLIK OGOHLANTIRISHI: TOKENLARNI QASDDAN SARFLASH / TROLLIK ANIQLANDI!**\n\n"
                f"👤 **Foydalanuvchi:** {s_name} ({s_user})\n"
                f"🆔 **ID:** `{sender_id}`\n\n"
                f"💬 **Xabari:** \"{message_text}\"\n\n"
                "🛡 **Ko'rilgan chora:** Ushbu foydalanuvchi **butunlay va abadiy bloklandi** (ignored_users). Tizim bitta ham token sarflamadi va bot unga boshqa aslo javob bermaydi."
            )
            try:
                target = config.escalation_chat
                if str(target).isdigit() or (str(target).startswith("-") and str(target)[1:].isdigit()):
                    target = int(target)
                await client.send_message(target, alert)
            except Exception as esc_err:
                logger.error("Xavfsizlik ogohlantirishini yuborishda xatolik: %s", esc_err)

            await event.reply("⛔️ **Xavfsizlik tizimi:** AI tizimidan g'arazli maqsadlarda foydalanish va tokenlarni qasddan sarflashga urinish aniqlandi. Siz butunlay bloklandingiz.")
            return

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

        # Xavfli fayllar (.apk, .exe, .bat, .cmd va h.k.) tekshiruvi
        doc_name = getattr(event.message.file, "name", "") or ""
        doc_ext = (Path(doc_name).suffix.lower() if doc_name else "") or (
            getattr(event.message.file, "ext", "").lower() if event.message.file else ""
        )
        mime_type = (getattr(event.message.file, "mime_type", "") or "").lower()

        DANGEROUS_EXTS = {
            ".apk", ".xapk", ".apkm", ".exe", ".msi", ".bat",
            ".cmd", ".scr", ".com", ".vbs", ".jar", ".bin",
            ".dmg", ".iso", ".deb", ".rpm"
        }
        is_apk = (
            doc_ext in {".apk", ".xapk", ".apkm"}
            or mime_type in ("application/vnd.android.package-archive", "application/x-authorware-bin")
            or doc_name.lower().endswith((".apk", ".xapk", ".apkm"))
        )
        is_dangerous = is_apk or (doc_ext in DANGEROUS_EXTS)

        # Fayl hajmi tekshiruvi (Maksimal 10 MB)
        file_size = getattr(event.message.file, "size", 0) or 0
        if file_size > MAX_FILE_SIZE:
            logger.warning("Fayl hajmi juda katta (%d bayt) [%s], yuklanmadi.", file_size, event.chat_id)
            await event.reply(
                "⚠️ **Fayl hajmi juda katta (maksimal 10 MB):**\n"
                "Server me'yorida ishlashi uchun iltimos faqat kerakli kod fayllarini yoki GitHub havolasini yuboring."
            )
            return

        # Kod yoki hujjat fayllarini aniqlash (.py, .txt, .html, .sql, .pdf, .zip, ...)
        supported_code_exts = {
            ".py", ".txt", ".html", ".css", ".js", ".ts",
            ".json", ".sql", ".java", ".c", ".cpp", ".md",
            ".xml", ".sh", ".yml", ".yaml", ".pdf", ".zip",
        }
        is_zip = (doc_ext == ".zip")
        has_doc_file = bool(
            event.message.document and not has_photo and not has_voice and doc_ext in supported_code_exts
        )
        has_github = bool("github.com/" in message_text)

        if not message_text.strip() and not has_photo and not has_voice and not has_doc_file and not is_dangerous:
            return

        # Spamerlardan himoya (Rate limiting: 1 daqiqada ko'pi bilan 6 ta so'rov)
        # Mentor va Vazifalar guruhiga HECH QANDAY rate limit yoki cheklov qo'llanilmaydi!
        is_mentor_user = (sender_id == config.mentor_user_id) or (sender_id in (8105823872, config.mentor_user_id))
        if not is_mentor_user and not is_vazifalar and not is_escalation_chat(event.chat_id):
            now_ts = time.time()
            user_times = USER_REQUEST_TIMESTAMPS.setdefault(sender_id, [])
            user_times = [t for t in user_times if now_ts - t < 60.0]
            USER_REQUEST_TIMESTAMPS[sender_id] = user_times
            if len(user_times) >= MAX_USER_REQUESTS_PER_MINUTE:
                logger.info("Foydalanuvchi %s uchun so'rovlar limiti oshdi (Rate Limit).", sender_id)
                await event.reply(
                    "⏳ **Iltimos, biroz kuting!**\n"
                    "Siz 1 daqiqa ichida juda ko'p savol yubordingiz. Tizim me'yorida ishlashi uchun 1 daqiqadan so'ng qayta yozing."
                )
                return
            user_times.append(now_ts)

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

        is_mentioned = bool(getattr(event.message, "mentioned", False))
        if "ustoz" in message_text.lower() or "mentor" in message_text.lower():
            is_mentioned = True

        # Qisqa tasdiq va loqayd so'zlar (AI jim turishi shart, bot aralashmaydi)
        clean_text = message_text.lower().strip().rstrip("!?.,~ ")
        ignored_acknowledgments = {
            "ok", "ha", "yoq", "yo'q", "tushunarli", "bopti", "hop", "xop", "+", "++", "+++",
            "yaxshi", "boladi", "bo'ladi", "tushundim", "mayli", "boldi", "bo'ldi",
            "aha", "xa", "eha", "voy", "hm", "hmm", "hmmm",
            "хорошо", "ладно", "понял", "понятно", "ок", "да", "нет", "ясно"
        }
        if clean_text in ignored_acknowledgments and not has_photo and not has_doc_file:
            logger.info("Chat [%s]: Qisqa tasdiq so'zi ('%s'), AI jim turadi.", event.chat_id, clean_text)
            return

        # Guruhlarda xabarning o'rinliligini tekshirish (Vazifalar admin guruhi bundan mustasno)
        if is_group and not is_escalation_chat(event.chat_id) and not is_relevant_group_message(
            message_text=message_text,
            has_photo=has_photo,
            has_voice=has_voice,
            has_doc_file=has_doc_file,
            has_github=has_github,
            reply_to_me=reply_to_me,
            is_dangerous=is_dangerous,
            is_mentioned=is_mentioned,
        ):
            return

        sender_id = event.sender_id or event.chat_id
        chat_id = event.chat_id
        message_received_time = time.time()
        debounce_key = (chat_id, sender_id) if is_group else chat_id
        log_activity(f"Kelgan xabar [{chat_id}]: {message_text[:35]}")

        # Agar oldinroq ushbu o'quvchi/chat uchun kutilayotgan vazifa bo'lsa, bekor qilamiz (debounce)
        if debounce_key in PENDING_TASKS and not PENDING_TASKS[debounce_key].done():
            PENDING_TASKS[debounce_key].cancel()

        async def process_delayed_reply():
            try:
                is_admin_chat = is_escalation_chat(chat_id)
                wait_sec = 0 if is_admin_chat else (config.mentor_wait_seconds or 5.0)

                # Shaxsiy chatda (Lichkada) aqlli kutish:
                # Agar mentor yaqinda xabar yozgan bo'lsa, AI darhol suhbatga aralashmaydi,
                # balki mentor yana yozishi uchun belgilangan vaqt (quiet_window, masalan 3 daqiqa) kutadi.
                # Agar mentor shu vaqt ichida boshqa yozmasa (chiqib ketgan bo'lsa), AI o'sha savolga o'zi avtomatik to'liq javob beradi!
                if is_private and not is_admin_chat:
                    last_m_time = LAST_MENTOR_ACTIVITY.get(chat_id, 0.0)
                    time_since_mentor = time.time() - last_m_time
                    quiet_window = float(memory_service.get_private_quiet_window())
                    if time_since_mentor < quiet_window:
                        remaining_wait = quiet_window - time_since_mentor
                        wait_sec = max(wait_sec, remaining_wait)
                        logger.info(
                            "Chat [%s]: Mentor yaqinda yozgan (%ds oldin). AI mentor javobini %ds kutadi...",
                            chat_id, int(time_since_mentor), int(wait_sec)
                        )

                if wait_sec > 0:
                    logger.info(
                        "Yangi xabar [%s]. Mentor yozishini %s soniya kutamiz...",
                        chat_id,
                        int(wait_sec),
                    )
                    await asyncio.sleep(wait_sec)

                    # Kutish vaqti tugadi: tekshiramiz, mentor ushbu xabardan keyin o'zi yozdimi?
                    last_m_time = LAST_MENTOR_ACTIVITY.get(chat_id, 0.0)
                    if last_m_time >= message_received_time:
                        log_activity(f"Mentor o'zi javob yozgani uchun AI aralashmadi [{chat_id}]")
                        logger.info("Mentor o'zi javob yozgan ekan [%s]. AI aralashmadi.", chat_id)
                        return

                if not config.auto_reply_enabled and not is_admin_chat:
                    log_activity(f"auto_reply_enabled o'chirilgan, javob berilmadi [{chat_id}]")
                    return
                if is_group and not config.group_reply_enabled and not is_admin_chat:
                    log_activity(f"group_reply_enabled o'chirilgan, javob berilmadi [{chat_id}]")
                    return

                log_activity(f"AI javob tayyorlamoqda [{chat_id}]...")
                logger.info("AI ishga kirishmoqda [%s]", chat_id)

                # Xavfsizlik: agar .apk yoki xavfli fayl bo'lsa, yuklamasdan ogohlantirish beramiz
                if is_dangerous:
                    logger.warning("Xavfsizlik: Xavfli fayl (%s) yuklanmadi [%s].", doc_name, chat_id)
                    if is_apk:
                        sec_msg = (
                            "🛡 **Xavfsizlik Ogohlantirishi:**\n"
                            "Xavfsizlik talablariga muvofiq `.apk` (Android ilovasi) fayllari AI tomonidan ochilmaydi va yuklab olinmaydi.\n\n"
                            "Iltimos, ilovangiz kodini (`.py`, `.java`, `.kt`, `.dart`), GitHub havolasini yoki xatolik skrinshotini yuboring. Mentor va AI sizga mamnuniyat bilan yordam beradi!"
                        )
                    else:
                        sec_msg = (
                            f"🛡 **Xavfsizlik Ogohlantirishi:**\n"
                            f"Xavfsizlik talablariga muvofiq bajariluvchi (`{doc_ext}`) fayllar ochilmaydi va yuklab olinmaydi.\n\n"
                            "Iltimos, dastur kodingizni toza matn, GitHub havolasi yoki skrinshot ko'rinishida yuboring."
                        )
                    await event.reply(sec_msg)
                    return

                # Agar xotirada suhbat tarixi kam bo'lsa, Telegram'dagi oxirgi xabarlarni sinxronlash
                if len(memory_service.get_history(chat_id)) < 3:
                    try:
                        past_messages = await client.get_messages(event.chat_id, limit=8)
                        for pm in reversed(past_messages[1:]):
                            if pm.text and pm.text.strip():
                                r = "model" if pm.out else "user"
                                memory_service.add_message(
                                    chat_id=chat_id, role=r, content=pm.text.strip()
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
                                logger.info("Ovozli xabar matnga o'girildi [%s]: %s", chat_id, transcribed[:80])
                    except Exception as v_err:
                        logger.warning("Ovozli xabarni tahlil qilishda xatolik: %s", v_err)

                # Agar kod yoki hujjat fayli bo'lsa (.py, .pdf, .txt, .zip va h.k.)
                file_name = None
                file_text = None
                if has_doc_file:
                    try:
                        file_bytes = await event.message.download_media(bytes)
                        if file_bytes:
                            if is_zip:
                                z_name, z_text, z_err = extract_safe_zip_content(file_bytes, doc_name or "project.zip")
                                if z_err:
                                    await event.reply(z_err)
                                    return
                                file_name = z_name
                                file_text = z_text
                                logger.info("ZIP arxiv muvaffaqiyatli tahlil qilindi [%s]: %s", chat_id, file_name)
                            elif doc_ext == ".pdf":
                                import io
                                from pypdf import PdfReader
                                reader = PdfReader(io.BytesIO(file_bytes))
                                file_text = "\n".join([p.extract_text() or "" for p in reader.pages[:10]])
                                file_name = doc_name or "document.pdf"
                            else:
                                file_text = file_bytes.decode("utf-8", errors="ignore")
                                file_name = doc_name or f"file{doc_ext}"
                            logger.info("Fayl muvaffaqiyatli o'qildi [%s]: %s (%d bayt)", chat_id, file_name, len(file_bytes))
                    except Exception as f_err:
                        logger.warning("Faylni o'qishda xatolik: %s", f_err)

                if not input_text.strip() and not has_photo and not file_text:
                    return

                # Agar rasm bo'lsa, yuklab olish
                image_bytes = None
                if has_photo:
                    image_bytes = await event.message.download_media(bytes)

                # GitHub linkini aniqlash
                github_match = re.search(r"https?://github\.com/[\w\-]+/[\w\-]+/?", input_text)

                # 📋 DAVOMAT: O'quvchi darsga kelolmasligi / dars qoldirishi haqidagi xabarlar
                if is_absence_message(input_text) and not is_admin_chat and not is_mentor_user:
                    try:
                        # 1. O'quvchining Telegram profili
                        sender_obj = await event.get_sender()
                        s_name = getattr(sender_obj, "first_name", "") or "Noma'lum"
                        if getattr(sender_obj, "last_name", None):
                            s_name += f" {sender_obj.last_name}"
                        s_user = f"@{sender_obj.username}" if getattr(sender_obj, "username", None) else "Username yo'q"

                        # 2. Guruhni aniqlash
                        group_hints = []
                        if is_group:
                            chat_obj = await event.get_chat()
                            g_title = getattr(chat_obj, "title", "")
                            if g_title:
                                group_hints.append(g_title)
                        else:
                            common_grps = await get_student_common_groups(client, sender_id)
                            if common_grps:
                                group_hints.extend(common_grps)

                        # 3. AI orqali xabarni tahlil qilish
                        clean_raw = input_text.replace("[Ovozli xabar]: ", "").strip()
                        analysis = await ai_service.analyze_absence_report(
                            message_text=clean_raw,
                            sender_name=s_name,
                            common_groups=group_hints,
                        )

                        student_name = analysis.get("student_name") or s_name
                        group_name = analysis.get("group_name") or (group_hints[0] if group_hints else "Aniqlanmadi (Shaxsiy chat)")
                        date_time = analysis.get("date_time") or "Bugun"
                        reason = analysis.get("reason") or "Sababi aytilmagan"

                        # 4. Rasmiy hisobot matnini shakllantirish
                        absence_report = (
                            "📋 #DAVOMAT #DARSGA_KELOLMAYDI\n\n"
                            f"👤 **O'quvchi:** {student_name} ({s_user})\n"
                            f"🆔 **ID:** `{sender_id}`\n"
                            f"📚 **Guruh:** {group_name}\n"
                            f"⏰ **Qachon:** {date_time}\n"
                            f"📝 **Sababi:** {reason}\n\n"
                            f"💬 **O'quvchining xabari:**\n\"{clean_raw}\""
                        )

                        # 5. @coddycamp_sergeli chatiga yuborish
                        try:
                            await client.send_message("@coddycamp_sergeli", absence_report)
                            logger.info("Davomat xabari @coddycamp_sergeli ga yuborildi: %s", student_name)
                            log_activity(f"📋 Davomat: {student_name} -> @coddycamp_sergeli")
                        except Exception as adm_err:
                            logger.error("@coddycamp_sergeli ga yuborishda xatolik: %s", adm_err)

                        # 6. Nusxasini Vazifalar (Mentor) guruhiga yuborish
                        try:
                            target = config.escalation_chat
                            if str(target).isdigit() or (str(target).startswith("-") and str(target)[1:].isdigit()):
                                target = int(target)
                            await client.send_message(
                                target,
                                f"📨 **@coddycamp_sergeli ma'muriyatiga o'quvchi dars qoldirishi haqida xabar yo'llandi:**\n\n{absence_report}"
                            )
                        except Exception as esc_err:
                            logger.error("Vazifalar guruhiga nusxa yuborishda xatolik: %s", esc_err)

                        # 7. O'quvchiga xushmuomala tasdiq javobi berish
                        if is_russian_text(clean_raw):
                            confirm_reply = (
                                "Здравствуйте! Информация о том, что вы не сможете прийти на урок, "
                                "принята и передана администрации (@coddycamp_sergeli) и учителю Нуриддину.\n\n"
                                "Выздоравливайте / ждем вас на следующем занятии! 😊"
                            )
                        else:
                            confirm_reply = (
                                "Assalomu alaykum! Darsga kela olmasligingiz haqidagi xabaringiz qabul qilindi "
                                "va CoddyCamp ma'muriyati (@coddycamp_sergeli) hamda Nuriddin ustozga yetkazildi.\n\n"
                                "Salomat bo'ling, keyingi darsda kutib qolamiz! 😊"
                            )

                        sent = await event.reply(confirm_reply)
                        if sent:
                            BOT_SENT_MESSAGE_IDS.add(sent.id)

                        memory_service.add_message(chat_id=chat_id, role="user", content=input_text)
                        memory_service.add_message(chat_id=chat_id, role="model", content=confirm_reply)
                        return
                    except Exception as abs_err:
                        logger.exception("Davomat xabarini qayta ishlashda xatolik: %s", abs_err)

                # 🕒 DARS JADVALI VA BAYRAM E'LONLARI (@coddycamp_sergeli)
                if is_schedule_query(input_text) and not is_admin_chat and not is_mentor_user:
                    try:
                        clean_raw = input_text.replace("[Ovozli xabar]: ", "").strip()
                        sched_res = await check_group_schedule_and_announcements(
                            client=client,
                            chat_id=chat_id,
                            is_group=is_group,
                            student_user_id=sender_id,
                        )
                        status = sched_res.get("status")
                        grp_name = sched_res.get("group_name") or "CoddyCamp guruhi"
                        ann_text = sched_res.get("announcement_text")
                        ann_date = sched_res.get("announcement_date") or "Yaqinda"

                        is_ru_sched = is_russian_text(clean_raw)

                        if status == "found_cancellation":
                            if is_ru_sched:
                                sched_reply = (
                                    "📢 **По объявлению администрации CoddyCamp (@coddycamp_sergeli):**\n\n"
                                    f"📚 Группа: **{grp_name}**\n"
                                    f"📅 Дата объявления: {ann_date}\n\n"
                                    f"💬 *Текст объявления:*\n\"{ann_text}\"\n\n"
                                    "В связи с праздником / выходным днём занятий сегодня не будет. "
                                    "Следующий урок состоится по обычному расписанию. Хорошего отдыха! 😊"
                                )
                            else:
                                sched_reply = (
                                    "📢 **CoddyCamp ma'muriyati (@coddycamp_sergeli) e'loni bo'yicha:**\n\n"
                                    f"📚 Guruh: **{grp_name}**\n"
                                    f"📅 E'lon sanasi: {ann_date}\n\n"
                                    f"💬 *E'lon matni:*\n\"{ann_text}\"\n\n"
                                    "Bayram / dam olish kuni munosabati bilan bugun guruhingizda darslar bo'lmaydi. "
                                    "Keyingi dars odatiy dars jadvalingiz bo'yicha davom etadi. Maroqli dam oling! 😊"
                                )
                        elif status == "normal_schedule":
                            if is_ru_sched:
                                sched_reply = (
                                    "🗓 **Информация о расписании:**\n\n"
                                    f"📚 Ваша группа: **{grp_name}**\n\n"
                                    "✅ Администрация (@coddycamp_sergeli) не публиковала объявлений об отмене занятий или праздниках.\n\n"
                                    "Сегодня урок пройдет в обычное время по утвержденному расписанию! Ждем вас на занятии 😊"
                                )
                            else:
                                sched_reply = (
                                    "🗓 **Dars jadvali ma'lumoti:**\n\n"
                                    f"📚 Sizning guruhingiz: **{grp_name}**\n\n"
                                    "✅ CoddyCamp ma'muriyati (@coddycamp_sergeli) tomonidan dars bekor qilinishi yoki bayram e'loni berilmagan.\n\n"
                                    "Bugun dars odatiy vaqtda va jadval bo'yicha bo'lib o'tadi! Darsda kutib qolamiz 😊"
                                )
                        else:
                            if is_ru_sched:
                                sched_reply = (
                                    "🗓 **Информация о расписании:**\n\n"
                                    "Чтобы точно узнать расписание уроков и праздничные дни, пожалуйста, уточните название вашей группы "
                                    "или обратитесь к администрации CoddyCamp (@coddycamp_sergeli) 😊"
                                )
                            else:
                                sched_reply = (
                                    "🗓 **Dars jadvali ma'lumoti:**\n\n"
                                    "Dars jadvali va bayram kunlarini aniq bilish uchun, iltimos, guruhingiz nomini yozing "
                                    "yoki CoddyCamp ma'muriyatiga (@coddycamp_sergeli) murojaat qiling 😊"
                                )

                        sent = await event.reply(sched_reply)
                        if sent:
                            BOT_SENT_MESSAGE_IDS.add(sent.id)

                        log_activity(f"🗓 Dars jadvali/bayram javobi berildi [{chat_id}]: {status}")
                        memory_service.add_message(chat_id=chat_id, role="user", content=input_text)
                        memory_service.add_message(chat_id=chat_id, role="model", content=sched_reply)
                        return
                    except Exception as sched_err:
                        logger.exception("Dars jadvali va bayram xabarini tahlil qilishda xatolik: %s", sched_err)

                # Agar mavzu tushuntirish so'ralgan bo'lsa (tushuntir <mavzu>)
                lower_input = input_text.strip().lower()
                if (
                    (lower_input.startswith("tushuntir ") or lower_input.startswith(".tushuntir "))
                    and not file_text
                    and not has_photo
                ):
                    raw_topic = input_text.strip().split(maxsplit=1)[1] if len(input_text.strip().split()) > 1 else ""
                    if raw_topic:
                        answer = await ai_service.explain_topic(raw_topic)
                    else:
                        answer = await ai_service.generate_reply(
                            chat_id=chat_id,
                            user_message=input_text,
                            reply_to_context=reply_context,
                            image_bytes=image_bytes,
                            file_name=file_name,
                            file_text=file_text,
                        )
                # Agar GitHub linki bo'lsa va alohida savol bo'lmasa, Auto-Review qilish
                elif github_match and not file_text and not has_photo and len(input_text.strip()) < 100:
                    answer = await ai_service.analyze_github_link(github_match.group(0))
                else:
                    # AI javobini olish
                    answer = await ai_service.generate_reply(
                        chat_id=chat_id,
                        user_message=input_text,
                        reply_to_context=reply_context,
                        image_bytes=image_bytes,
                        file_name=file_name,
                        file_text=file_text,
                    )

                # Yakuniy tekshiruv: agar shu orada mentor o'zi yozgan bo'lsa, yubormaslik
                last_m_time = LAST_MENTOR_ACTIVITY.get(chat_id, 0.0)
                if last_m_time >= message_received_time:
                    log_activity(f"Mentor o'zi yozgani aniqlandi [{chat_id}], AI javobi bekor qilindi.")
                    logger.info("Mentor o'zi javob yozgan ekan [%s]. AI javobi yuborilmadi.", chat_id)
                    return

                # Flood interval tekshiruvi (har bir chat uchun kamida 2 soniya)
                now_reply = time.time()
                if now_reply - LAST_REPLY_TIME.get(chat_id, 0.0) < MIN_INTERVAL_SECONDS:
                    await asyncio.sleep(MIN_INTERVAL_SECONDS)
                LAST_REPLY_TIME[chat_id] = time.time()

                # O'quvchi profiliga faollikni yozib qo'yish (Student CRM)
                if sender_id and sender_id != config.mentor_user_id and sender_id != 8105823872:
                    try:
                        s_name = getattr(sender, "first_name", "") or "O'quvchi"
                        if getattr(sender, "last_name", None):
                            s_name += f" {sender.last_name}"
                        s_user = getattr(sender, "username", "") or ""
                        memory_service.record_student_activity(
                            user_id=sender_id,
                            full_name=s_name,
                            username=s_user,
                            question_text=input_text,
                        )
                    except Exception as st_err:
                        logger.debug("Student faolligini yozishda ogohlantirish: %s", st_err)

                # Javob matnini tozalash (agar maxsus teglar bo'lsa)
                raw_ans = str(answer)
                if "<<<OFF_TOPIC>>>" in raw_ans:
                    raw_ans = raw_ans.replace("<<<OFF_TOPIC>>>", "").strip()
                answer = raw_ans

                # Javobni yuborish (reply tarzida, Voice-to-Voice va fallback bilan)
                sent_reply = None
                CURRENT_SENDING_CHATS.add(chat_id)
                try:
                    voice_reply_enabled = memory_service.get_setting("voice_reply_enabled", "true").lower() == "true"

                    # Agar ovozli xabar bo'lsa va voice_reply_enabled yoqilgan bo'lsa
                    if has_voice and voice_reply_enabled:
                        try:
                            from services.tts_service import generate_voice_message
                            voice_path = await generate_voice_message(str(answer))
                            if voice_path and voice_path.exists():
                                sent_voice = await event.reply(file=str(voice_path), voice_note=True)
                                if sent_voice:
                                    BOT_SENT_MESSAGE_IDS.add(sent_voice.id)
                                log_activity(f"Ovozli AI javobi yuborildi [{chat_id}]")
                                voice_path.unlink(missing_ok=True)
                        except Exception as v_send_err:
                            logger.warning("Ovozli javob yuborishda ogohlantirish: %s", v_send_err)

                    sent_reply = await event.reply(answer)
                    if sent_reply:
                        BOT_SENT_MESSAGE_IDS.add(sent_reply.id)
                    log_activity(f"Javob muvaffaqiyatli yuborildi [{chat_id}]: {str(answer)[:40]}")
                    logger.info("Chat %s ga AI javobi yuborildi.", chat_id)
                except Exception as reply_err:
                    log_activity(f"event.reply xatolik [{chat_id}]: {reply_err}, send_message bilan urinilmoqda")
                    try:
                        sent_reply = await client.send_message(chat_id, answer)
                        if sent_reply:
                            BOT_SENT_MESSAGE_IDS.add(sent_reply.id)
                        log_activity(f"send_message orqali yuborildi [{chat_id}]")
                    except Exception as fb_err:
                        log_activity(f"send_message ham xato berdi [{chat_id}]: {fb_err}")
                finally:
                    CURRENT_SENDING_CHATS.discard(chat_id)

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

                    if is_escalation_chat(event.chat_id):
                        logger.info("Murojaat 'Vazifalar' guruhining o'zida bo'lgani uchun qayta ogohlantirish yuborilmadi.")
                    else:
                        try:
                            target = config.escalation_chat
                            if target.isdigit() or (target.startswith("-") and target[1:].isdigit()):
                                target = int(target)
                            await client.send_message(target, alert_text)
                            logger.info("Eskalyatsiya xabari '%s' ga yetkazildi.", config.escalation_chat)
                        except Exception as exc:
                            logger.error("Eskalyatsiya xabarini yetkazishda xatolik: %s", exc)

            except asyncio.CancelledError:
                log_activity(f"Kutish bekor qilindi (Mentor yozdi) [{chat_id}]")
                logger.info("AI kutish vazifasi bekor qilindi (Mentor yozdi) [%s].", chat_id)
            except Exception as e:
                log_activity(f"Kutilmagan xatolik [{chat_id}]: {type(e).__name__} - {e}")
                logger.exception("Avto-javob berishda xatolik yuz berdi: %s", e)
            finally:
                if PENDING_TASKS.get(debounce_key) is asyncio.current_task():
                    PENDING_TASKS.pop(debounce_key, None)

        # 5 soniyalik vazifani boshlash
        task = asyncio.create_task(process_delayed_reply())
        PENDING_TASKS[debounce_key] = task

