"""
Salomatlik va Dam Olish Nazorati Xizmati (Digital Well-being & Rest Reminder Service).
Agar Nuriddin Telegramda 90 daqiqadan (1.5 soat) ko'proq uzluksiz xabarlashsa,
Vazifalar guruhiga ovozli push bilan yoqimli dam olish eslatmasini yo'llaydi.
"""

import logging
import time
from config import config
from services.memory_service import memory_service

logger = logging.getLogger("coddyHelper.wellbeing_service")

SESSION_START_TIME: float = 0.0
LAST_ACTIVITY_TIME: float = 0.0
ALERTED_THIS_SESSION: bool = False
CONTINUOUS_THRESHOLD_SEC: float = 5400.0  # 90 daqiqa (1.5 soat)
SESSION_BREAK_GAP_SEC: float = 900.0       # 15 daqiqa tanaffus bo'lsa yangi seans deb hisoblanadi


async def record_mentor_activity_and_check(client=None):
    """
    Mentorning faolligini qayd etadi. Agar uzluksiz 1.5 soatdan oshsa,
    Vazifalar guruhiga dam olish eslatmasini yuboradi.
    """
    global SESSION_START_TIME, LAST_ACTIVITY_TIME, ALERTED_THIS_SESSION

    enabled = memory_service.get_setting("wellbeing_reminder_enabled", "true").lower() == "true"
    if not enabled:
        return

    now = time.time()

    # Agar oxirgi faollikdan beri 15 daqiqadan ko'p o'tgan bo'lsa, yangi seans boshlanadi
    if now - LAST_ACTIVITY_TIME > SESSION_BREAK_GAP_SEC:
        SESSION_START_TIME = now
        ALERTED_THIS_SESSION = False

    LAST_ACTIVITY_TIME = now

    # Agar uzluksiz ishlash 90 daqiqadan oshsa va hali ogohlantirilmagan bo'lsa
    duration_active = now - SESSION_START_TIME
    if duration_active >= CONTINUOUS_THRESHOLD_SEC and not ALERTED_THIS_SESSION:
        ALERTED_THIS_SESSION = True
        logger.info("☕️ Mentor uzluksiz 90 daqiqa faol bo'ldi. Dam olish eslatmasi yuborilmoqda...")

        from config import get_vazifalar_chat_target
        vazifalar_chat = await get_vazifalar_chat_target(client)
        if str(vazifalar_chat).strip().lower() in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
            vazifalar_chat = -1005388159517
        alert_msg = (
            "☕️ **Nuriddin aka, 1.5 soatdan beri Telegramda uzluksiz faolsiz!**\n\n"
            "Ko'zlaringiz toliqmasligi, miyangiz charchamasligi va sog'lig'ingiz uchun "
            "5-10 daqiqa ekrandan uzoqlashib, choy ichib yoki toza havoda nafas olib dam olishingizni tavsiya qilaman. "
            "Salomatlik har doim birinchi o'rinda! 😊🌿"
        )

        sent = False
        if config.bot_token:
            try:
                from aiogram import Bot
                b_inst = Bot(token=config.bot_token)
                try:
                    c_id = int(vazifalar_chat) if str(vazifalar_chat).lstrip("-").isdigit() else vazifalar_chat
                    await b_inst.send_message(
                        chat_id=c_id,
                        text=alert_msg,
                        parse_mode="Markdown",
                        disable_notification=False,
                    )
                    sent = True
                    logger.info("☕️ Dam olish eslatmasi bot orqali Vazifalar guruhiga yetkazildi.")
                finally:
                    await b_inst.session.close()
            except Exception as be:
                logger.debug("Bot orqali dam olish eslatmasi yuborishda ogohlantirish: %s", be)

        if not sent and client:
            try:
                await client.send_message(vazifalar_chat, alert_msg, silent=False)
                logger.info("☕️ Dam olish eslatmasi Telethon orqali Vazifalar guruhiga yetkazildi.")
            except Exception as ce:
                logger.error("Telethon orqali dam olish eslatmasi yuborishda xatolik: %s", ce)
