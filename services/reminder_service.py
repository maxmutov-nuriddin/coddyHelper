"""
Eslatmalar xizmati (Reminder Service).
Foydalanuvchi talabi:
- Barcha admin boshqaruvlari va eslatmalar FAQAT VA FAQAT 'Vazifalar' guruhida bo'ladi.
- Shaxsiy chat (lichka) va Izbrannoe (Saved Messages / "me") ga MUTLAQO hech narsa yuborilmaydi, o'z holicha toza qoladi.
- Vazifalar guruhiga Telegram Bot orqali ovozli PUSH-uvidomleniya va teglash bilan yetkaziladi.
"""

import logging
import re
from aiogram import Bot
from config import config
from services.memory_service import memory_service

logger = logging.getLogger("coddyHelper.reminder_service")


async def send_due_reminder_notification(
    rem_id: int,
    chat_id: int | str,
    task_text: str,
    remind_at: str,
    client=None,
) -> bool:
    """
    Vaqti yetgan eslatmani FAQAT 'Vazifalar' guruhiga ovozli push-uvidomleniya bilan yuboradi.
    1. Dublikat bo'lmasligi uchun SQLite da atomar tarzda is_sent=1 deb qulflaydi.
    2. Izbrannoe (Saved Messages) va shaxsiy chatlarga ASLO yubormaydi.
    3. Vazifalar guruhiga Telegram Bot (@coddyassistanstbot) orqali disable_notification=False
       va [Nuriddin aka](tg://user?id=...) tegi bilan yuboradi (bu guruh ichida ovozli push chiqaradi).
    4. Agar bot guruhda bo'lmasa, zaxira sifatida Telethon orqali Vazifalar guruhiga joylashtiradi.
    """
    # 1. Atomar qulflash: Agar boshqa task allaqachon jo'natgan bo'lsa, takrorlamaslik
    if not memory_service.mark_reminder_sent_if_pending(rem_id):
        logger.debug("Eslatma #%d allaqachon yuborilgan, o'tkazib yuborildi.", rem_id)
        return False

    # 2. Matnni tozalash
    clean_task = task_text
    clean_task = re.sub(r"^\[.*?ga xabar\]:\s*", "", clean_task, flags=re.I)
    clean_task = re.sub(r"^🔔\s*(?:Eslatma|Напоминание):\s*", "", clean_task, flags=re.I).strip()

    target_user = config.mentor_user_id or 8105823872

    # 3. Guruh ID sini aniqlash:
    # Foydalanuvchi talabi: Barcha eslatmalar FAQAT Vazifalar guruhida bo'lishi shart! (Izbrannoe ga ASLO emas)
    from config import get_vazifalar_chat_target_sync
    vazifalar_chat_id = get_vazifalar_chat_target_sync()
    target_chat = chat_id

    # Agar chat_id noto'g'ri bo'lsa (0, "me", o'zimga yoki shaxsiy id), Vazifalar guruhiga yo'naltirish
    if not target_chat or str(target_chat).strip().lower() in ("0", "me", "o'zim", "o'zimga", "self", "8105823872", str(config.mentor_user_id), ""):
        target_chat = vazifalar_chat_id

    if str(target_chat).strip().lower() in ("me", "self", "8105823872", str(config.mentor_user_id)):
        target_chat = vazifalar_chat_id

    if isinstance(target_chat, str) and target_chat.strip().lstrip("-").isdigit():
        target_chat = int(target_chat.strip())

    group_text = (
        f"🔔 **DIQQAT, ESLATMA!** [Nuriddin aka](tg://user?id={target_user})\n\n"
        f"📌 **Vazifa:** {clean_task}\n"
        f"⏰ **Rejalashtirilgan vaqt:** `{remind_at}`\n"
        f"🆔 **ID:** `{rem_id}`"
    )

    sent_any = False

    # 4. 🚨 VAZIFALAR GURUHIGA PUSH BILAN YUBORISH (Telegram Bot orqali):
    # Bot guruhga xabar yuborganda, guruh a'zosi bo'lgan mentorga rasmiy kiruvchi xabar bo'ladi
    # va Telegram telefonda push-uvidomleniya ko'rsatadi!
    if config.bot_token and isinstance(target_chat, int) and target_chat < 0:
        try:
            bot_inst = Bot(token=config.bot_token)
            try:
                await bot_inst.send_message(
                    chat_id=target_chat,
                    text=group_text,
                    parse_mode="Markdown",
                    disable_notification=False,  # Ovozli push-uvidomleniya!
                )
                sent_any = True
                logger.info("🔔 Eslatma #%d bot orqali Vazifalar guruhiga (%s) push bilan yuborildi.", rem_id, target_chat)
            finally:
                await bot_inst.session.close()
        except Exception as b_err:
            logger.debug("Bot orqali Vazifalar guruhiga yuborishda ogohlantirish (Telethon zaxirasi ishlatiladi): %s", b_err)

    # 5. Zaxira: Agar bot guruhga yubora olmasa, Telethon orqali Vazifalar guruhiga yuborish:
    if not sent_any and client:
        try:
            await client.send_message(target_chat, group_text, silent=False)
            sent_any = True
            logger.info("🔔 Eslatma #%d Telethon orqali Vazifalar guruhiga (%s) yuborildi.", rem_id, target_chat)
        except Exception as c_err:
            logger.error("Telethon orqali Vazifalar guruhiga eslatma yuborishda xatolik (%s): %s", target_chat, c_err)

    return sent_any
