"""
Telegram Bot xizmati (aiogram 3)
Faqat tizim administratori (@mentor_cc / ID: 8105823872) uchun:
- Guruhga Mini App Admin Panel tugmasini chiqarish va qadash (Pin)
- Lichkada WebApp Menu Button va Inline Button taqdim etish
- Begona foydalanuvchilar urinishlarini to'liq bloklash
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
)
from config import config, is_escalation_chat
from web_app import generate_admin_token

logger = logging.getLogger("coddyHelper.bot_service")

bot: Bot | None = None
dp: Dispatcher | None = None
_polling_task: asyncio.Task | None = None


def is_admin(user_id: int | None) -> bool:
    """Faqat belgilangan mentor ID si ruxsat etilganini tekshiradi."""
    if not user_id:
        return False
    return user_id == config.mentor_user_id or user_id == 8105823872


def get_private_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Lichka uchun WebApp ochuvchi tugmalar to'plami."""
    token = generate_admin_token(user_id=user_id)
    app_url = f"{config.web_app_url}/app?token={token}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Admin Panelni Ochish (Mini App)",
                    web_app=WebAppInfo(url=app_url),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📌 Vazifalar Guruhiga Tugma Qo'yish",
                    callback_data="post_group_button",
                )
            ],
        ]
    )


def get_group_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Guruh uchun tugmalar to'plami."""
    token = generate_admin_token(user_id=user_id)
    app_url = f"{config.web_app_url}/app?token={token}"
    bot_link = f"https://t.me/{config.bot_username}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Admin Panelni Ochish (Mini App)",
                    url=app_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Shaxsiy Botga O'tish",
                    url=bot_link,
                )
            ],
        ]
    )


async def setup_bot_handlers(d: Dispatcher) -> None:
    """Bot handlerlarini ro'yxatga oladi va qat'iy admin tekshiruvini o'rnatadi."""

    @d.message.outer_middleware
    async def admin_only_middleware(handler, event: types.Message, data):
        sender = event.from_user
        sender_id = sender.id if sender else None

        if not is_admin(sender_id):
            if event.chat.type == "private":
                await event.answer(
                    "🚫 **Ruxsat berilmagan!**\n\n"
                    "Ushbu bot faqat tizim administratori (@mentor_cc) uchun shaxsiy boshqaruv boti hisoblanadi.\n"
                    f"Sizning Telegram ID ingiz: `{sender_id}`"
                )
            return

        return await handler(event, data)

    @d.callback_query.outer_middleware
    async def admin_callback_middleware(handler, event: types.CallbackQuery, data):
        sender = event.from_user
        sender_id = sender.id if sender else None

        if not is_admin(sender_id):
            await event.answer(
                "🚫 Ushbu amal faqat administrator (@mentor_cc) uchun ruxsat etilgan!",
                show_alert=True,
            )
            return

        return await handler(event, data)

    @d.message(F.chat.type == "private", Command(commands=["start", "panel", "app", "admin", "menu"]))
    async def cmd_start_private(message: types.Message):
        user_id = message.from_user.id
        kb = get_private_keyboard(user_id)

        try:
            token = generate_admin_token(user_id=user_id)
            app_url = f"{config.web_app_url}/app?token={token}"
            await message.bot.set_chat_menu_button(
                chat_id=user_id,
                menu_button=MenuButtonWebApp(
                    text="📱 Admin Panel",
                    web_app=WebAppInfo(url=app_url),
                ),
            )
        except Exception as mb_err:
            logger.warning("Menu buttonni sozlashda ogohlantirish: %s", mb_err)

        await message.answer(
            "👋 **Assalomu alaykum, Ustoz (@mentor_cc)!**\n\n"
            "coddyHelper tizimining shaxsiy boshqaruv botiga xush kelibsiz.\n\n"
            "Quyidagi tugma orqali to'g'ridan-to'g'ri **Telegram Mini App** boshqaruv panelini ochishingiz mumkin:\n"
            "• Lichka va Guruhlar avto-javobini boshqarish\n"
            "• Eslatmalarni (xx xx xxxx sanali) ko'rish va sozlash\n"
            "• Senior AI bilan maslahatlashish\n"
            "• SQLite ma'lumotlar bazasini yuklab olish\n\n"
            "Pastdagi tugmani bosing 👇",
            reply_markup=kb,
        )

    @d.message(F.chat.type.in_(["group", "supergroup"]), Command(commands=["panel", "button", "pin_button", "app", "admin"]))
    async def cmd_group_panel(message: types.Message):
        user_id = message.from_user.id
        kb = get_group_keyboard(user_id)

        group_text = (
            "🎛 **coddyHelper — Boshqaruv Paneli (Mini App)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Assalomu alaykum, Ustoz (@mentor_cc)!\n\n"
            "Guruhdan turib tizimni boshqarish uchun pastdagi tugmani bosing:\n\n"
            "🛡 *Xavfsizlik: Faqat sizning akkauntingiz uchun kirish ochiq.*"
        )

        sent = await message.answer(group_text, reply_markup=kb)
        try:
            await message.bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=sent.message_id,
                disable_notification=True,
            )
            logger.info("Admin Panel tugmasi guruhga joylashtirildi va qadaldi (Chat: %s)", message.chat.id)
        except Exception as pin_err:
            logger.warning("Xabarni pin qilib bo'lmadi: %s", pin_err)

    @d.callback_query(F.data == "post_group_button")
    async def on_post_group_button(call: types.CallbackQuery):
        target_chat = config.escalation_chat
        if not target_chat or target_chat == "me":
            await call.answer("⚠️ ESCALATION_CHAT guruhi belgilanmagan!", show_alert=True)
            return

        success, err = await post_group_panel_button(target_chat)
        if success:
            await call.answer("✅ Guruhga tugma joylandi va qadaldi!", show_alert=True)
            await call.message.answer(
                f"✅ **Boshqaruv paneli tugmasi guruhga ({target_chat}) muvaffaqiyatli yuborildi va qadaldi!**"
            )
        else:
            await call.answer(f"❌ Xatolik: {err}", show_alert=True)


async def post_group_panel_button(chat_id: int | str) -> tuple[bool, str]:
    global bot
    if not bot:
        return False, "Bot ishga tushmagan (BOT_TOKEN kiritilmagan)"

    try:
        s = str(chat_id).strip()
        cid = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else s

        kb = get_group_keyboard(config.mentor_user_id)
        group_text = (
            "🎛 **coddyHelper — Boshqaruv Paneli (Mini App)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Assalomu alaykum, Ustoz (@mentor_cc)!\n\n"
            "Guruhdan turib botni boshqarish uchun pastdagi tugmani bosing:\n\n"
            "🛡 *Xavfsizlik: Faqat mentor (@mentor_cc) uchun ruxsat etilgan.*"
        )

        sent = await bot.send_message(chat_id=cid, text=group_text, reply_markup=kb)
        try:
            await bot.pin_chat_message(chat_id=cid, message_id=sent.message_id, disable_notification=True)
        except Exception as pin_err:
            logger.warning("Guruhda xabarni pin qilib bo'lmadi: %s", pin_err)

        return True, "OK"
    except Exception as e:
        logger.error("Guruhga tugma yuborishda xatolik: %s", e)
        return False, str(e)


async def start_bot_service() -> None:
    global bot, dp, _polling_task
    if not config.bot_token:
        logger.info("ℹ️ BOT_TOKEN topilmadi, bot xizmati o'chirilgan.")
        return

    logger.info("🤖 Telegram Bot xizmati ishga tushirilmoqda (@%s)...", config.bot_username)
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    await setup_bot_handlers(dp)

    try:
        token = generate_admin_token(user_id=config.mentor_user_id)
        app_url = f"{config.web_app_url}/app?token={token}"
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="📱 Admin Panel",
                web_app=WebAppInfo(url=app_url),
            )
        )
        logger.info("✅ Bot Menu Button muvaffaqiyatli sozlandi.")
    except Exception as e:
        logger.warning("Bot Menu Button sozlashda ogohlantirish: %s", e)

    async def post_initial_button():
        await asyncio.sleep(5)
        if config.escalation_chat and config.escalation_chat != "me":
            try:
                await post_group_panel_button(config.escalation_chat)
            except Exception as e:
                logger.info("Guruhga dastlabki tugmani yuborish keyinga qoldirildi: %s", e)

    asyncio.create_task(post_initial_button())

    logger.info("🚀 Telegram Bot polling xizmati faollashdi.")
    await dp.start_polling(bot, handle_signals=False)


async def stop_bot_service() -> None:
    global bot, dp
    if dp:
        await dp.stop_polling()
    if bot:
        await bot.session.close()
    logger.info("🛑 Telegram Bot xizmati to'xtatildi.")
