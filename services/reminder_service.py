"""
Eslatmalar xizmati (Reminder Service).
Eslatmalarni o'z vaqtida ovozli va faol push-uvidomleniya (notification) bilan
ham Telegram Bot (@coddyassistanstbot) orqali to'g'ridan-to'g'ri mentorga,
ham Vazifalar guruhiga yetkazadi.
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
    Vaqti yetgan eslatmani OVOZLI PUSH UVIDOMLENIYA bilan yetkazadi.
    1. Dublikat bo'lmasligi uchun SQLite da atomar tarzda is_sent=1 deb qulflaydi.
    2. Telegram Bot (@coddyassistanstbot) orqali to'g'ridan-to'g'ri mentorga
       disable_notification=False parametri bilan yuboradi (ekranni yoqadi, ovoz chiqaradi, tebranish qiladi).
    3. Agar chat_id guruh bo'lsa, Vazifalar guruhiga ham xabarni yuboradi va mentorni tag qiladi.
    """
    # 1. Atomar qulflash: Agar boshqa task allaqachon jo'natgan bo'lsa, takrorlamaslik
    if not memory_service.mark_reminder_sent_if_pending(rem_id):
        logger.debug("Eslatma #%d allaqachon yuborilgan, o'tkazib yuborildi.", rem_id)
        return False

    # 2. Matnni tozalash
    clean_task = task_text
    clean_task = re.sub(r"^\[.*?ga xabar\]:\s*", "", clean_task, flags=re.I)
    clean_task = re.sub(r"^🔔\s*(?:Eslatma|Напоминание):\s*", "", clean_task, flags=re.I).strip()

    alert_text = (
        "🔔 **DIQQAT, ESLATMA VAQTI KELDI!**\n\n"
        f"📌 **Vazifa:** {clean_task}\n"
        f"⏰ **Rejalashtirilgan vaqt:** `{remind_at}`\n"
        f"🆔 **ID:** `{rem_id}`"
    )

    sent_any = False
    target_user = config.mentor_user_id or 8105823872

    # 3. 🚨 ASOSIY UVIDOMLENIYA: Telegram Bot (@coddyassistanstbot) orqali to'g'ridan-to'g'ri mentorga
    # Bot orqali kelgan xabar Telegramda INCOMING hisoblanadi va 100% ovozli push notification beradi!
    if config.bot_token:
        try:
            bot_inst = Bot(token=config.bot_token)
            try:
                await bot_inst.send_message(
                    chat_id=target_user,
                    text=alert_text,
                    parse_mode="Markdown",
                    disable_notification=False,  # Ovozli va faol uvidomleniya!
                )
                sent_any = True
                logger.info("🔔 Eslatma #%d bot orqali ovozli uvidomleniya bilan mentorga yetkazildi.", rem_id)
            finally:
                await bot_inst.session.close()
        except Exception as b_err:
            logger.warning("Bot orqali eslatma yuborishda ogohlantirish: %s", b_err)

    # 4. Telethon (Vazifalar guruhi yoki tegishli chatga joylashtirish)
    if client:
        try:
            c_id = chat_id
            if isinstance(c_id, str):
                c_id_str = c_id.strip()
                if c_id_str.lstrip("-").isdigit():
                    c_id = int(c_id_str)
                elif c_id_str in ("me", "o'zim", "o'zimga"):
                    c_id = "me"

            if c_id and str(c_id).strip() not in ("0", ""):
                # Agar guruh bo'lsa (c_id < 0), mentorni tag qilamiz (shunda guruh ovozsiz bo'lsa ham @ notification keladi)
                group_text = alert_text
                if isinstance(c_id, int) and c_id < 0:
                    group_text = (
                        f"🔔 **DIQQAT, ESLATMA!** [Nuriddin aka](tg://user?id={target_user})\n\n"
                        f"📌 **Vazifa:** {clean_task}\n"
                        f"⏰ **Rejalashtirilgan vaqt:** `{remind_at}`\n"
                        f"🆔 **ID:** `{rem_id}`"
                    )

                await client.send_message(c_id, group_text, silent=False)
                sent_any = True
                logger.info("🔔 Eslatma #%d Telethon orqali chatga (%s) yuborildi.", rem_id, c_id)
        except Exception as c_err:
            logger.warning("Telethon orqali eslatmani chatga yuborishda xatolik (%s): %s", chat_id, c_err)
            if not sent_any:
                try:
                    await client.send_message("me", alert_text, silent=False)
                    sent_any = True
                except Exception:
                    pass

    return sent_any
