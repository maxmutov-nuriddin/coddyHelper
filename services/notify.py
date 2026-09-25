"""
Bot (@coddyassistanstbot) orqali foydalanuvchilarga tizim bildirishnomalarini yuborish.
Mijozlarga: sessiya holati, obuna muddati, eslatmalar. Super Admin'ga: muhim hodisalar.
"""

import logging

from config import config

logger = logging.getLogger(__name__)


async def notify_user(user_id: int, text: str) -> bool:
    """Foydalanuvchining bot bilan shaxsiy chatiga xabar yuboradi (u avval /start bosgan bo'lishi kerak)."""
    if not config.bot_token or not user_id:
        return False
    try:
        from aiogram import Bot
        bot_inst = Bot(token=config.bot_token)
        try:
            await bot_inst.send_message(chat_id=int(user_id), text=text, parse_mode="HTML")
            return True
        finally:
            await bot_inst.session.close()
    except Exception as e:
        logger.debug("Bildirishnoma yuborilmadi (user_id=%s): %s", user_id, e)
        return False


async def notify_super_admin(text: str) -> bool:
    return await notify_user(config.mentor_user_id or 8105823872, text)
