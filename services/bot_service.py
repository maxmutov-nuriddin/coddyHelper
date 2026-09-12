"""
Telegram Bot xizmati (aiogram 3)
Faqat tizim administratori (@mentor_cc / ID: 8105823872) uchun:
- Guruhga Mini App Admin Panel tugmasini chiqarish va qadash (Pin)
- Lichkada WebApp Menu Button va Inline Button taqdim etish
- Begona foydalanuvchilar urinishlarini to'liq bloklash
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    MenuButtonDefault,
    FSInputFile,
)
from config import config, is_escalation_chat
from web_app import generate_admin_token, MASTER_ADMIN_TOKEN

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
    token = MASTER_ADMIN_TOKEN if is_admin(user_id) else generate_admin_token(user_id=user_id)
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
                    text="💾 Baza Zaxirasini Yangilash (Backup)",
                    callback_data="refresh_backup",
                )
            ],
        ]
    )


def get_group_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """Guruh uchun tugmalar to'plami (Faqat Mini App ochish tugmasi)."""
    token = MASTER_ADMIN_TOKEN
    app_url = f"{config.web_app_url}/app?token={token}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Admin Panelni Ochish (Mini App)",
                    url=app_url,
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
                try:
                    await event.bot.set_chat_menu_button(
                        chat_id=sender_id,
                        menu_button=MenuButtonDefault(),
                    )
                except Exception:
                    pass
                await event.answer("Sizga ruxsat berilmagan.")
            return

        return await handler(event, data)

    @d.callback_query.outer_middleware
    async def admin_callback_middleware(handler, event: types.CallbackQuery, data):
        sender = event.from_user
        sender_id = sender.id if sender else None

        if not is_admin(sender_id):
            await event.answer(
                "Sizga ruxsat berilmagan.",
                show_alert=True,
            )
            return

        return await handler(event, data)

    @d.message(F.chat.type == "private", Command(commands=["start", "panel", "app", "admin", "menu"]))
    async def cmd_start_private(message: types.Message):
        user_id = message.from_user.id
        kb = get_private_keyboard(user_id)

        try:
            token = MASTER_ADMIN_TOKEN if is_admin(user_id) else generate_admin_token(user_id=user_id)
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
            "🎛 <b>coddyHelper — Boshqaruv Paneli (Mini App)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Assalomu alaykum, Ustoz (<b>@mentor_cc</b>)!\n\n"
            "Guruhdan turib botni boshqarish uchun pastdagi tugmani bosing:\n\n"
            "🛡 <i>Xavfsizlik: Faqat mentor (<b>@mentor_cc</b>) uchun ruxsat etilgan.</i>"
        )

        sent = await message.answer(group_text, reply_markup=kb, parse_mode="HTML")
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

    # 6. Callback Query: "💾 Baza Zaxirasini Yangilash (Backup)"
    @d.callback_query(F.data == "refresh_backup")
    async def on_refresh_backup(call: types.CallbackQuery):
        await call.answer("⏳ Zaxira yangilanmoqda...")
        ok, err = await send_or_update_database_backup()
        if ok:
            await call.answer("✅ Baza botga yuborildi va eski xabar tozalandi!", show_alert=True)
        else:
            await call.answer(f"❌ Xatolik: {err}", show_alert=True)

    # 7. Lichka: /backup buyrug'i
    @d.message(F.chat.type == "private", Command(commands=["backup", "db", "baza"]))
    async def cmd_backup_private(message: types.Message):
        await message.answer("⏳ **Baza zaxiralanmoqda va yangilanmoqda...**")
        ok, err = await send_or_update_database_backup()
        if not ok:
            await message.answer(f"❌ Xatolik yuz berdi: {err}")

    # 8. Lichka: Eslatmalar ro'yxati
    @d.message(F.chat.type == "private", Command(commands=["eslatmalar", "reminders"]))
    async def cmd_reminders_list(message: types.Message):
        from services.memory_service import memory_service
        reminders = memory_service.get_active_reminders(limit=20)
        if not reminders:
            await message.answer("ℹ️ Hozirda hech qanday faol eslatma yo'q.\n\nYangi eslatma qo'shish uchun: `ai eslatma 2 soatdan keyin dars` deb yozing.")
            return

        lines = ["⏰ **Faol Eslatmalar Ro'yxati:**\n"]
        for r in reminders:
            lines.append(f"• **[ID: {r['id']}]** `{r['remind_at']}`: {r['task']}")
        lines.append("\nBekor qilish uchun: `/bekor <ID>`")
        await message.answer("\n".join(lines), parse_mode="Markdown")

    # 9. Lichka: Eslatmani bekor qilish
    @d.message(F.chat.type == "private", Command(commands=["bekor", "cancel"]))
    async def cmd_reminder_cancel(message: types.Message):
        from services.memory_service import memory_service
        args = (message.text or "").split()
        if len(args) > 1 and args[1].isdigit():
            rem_id = int(args[1])
            success = memory_service.delete_reminder(rem_id)
            if success:
                await message.answer(f"✅ **ID `{rem_id}` bo'lgan eslatma bekor qilindi.**")
            else:
                await message.answer(f"ℹ️ ID `{rem_id}` bo'lgan faol eslatma topilmadi.")
        else:
            await message.answer("ℹ️ Foydalanish: `/bekor <ID>`\nMasalan: `/bekor 3`")

    # 10. Lichka: Yangi eslatma qo'shish yoki matnli xabarlar
    @d.message(F.chat.type == "private")
    async def cmd_reminder_create(message: types.Message):
        text = (message.text or "").strip()
        lower = text.lower()

        # Eslatma qo'shish prefikslari
        is_rem = False
        query = text
        for prefix in ["/eslatma", "ai eslatma", "eslatma"]:
            if lower.startswith(prefix):
                is_rem = True
                query = text[len(prefix):].strip()
                break

        if not is_rem:
            for time_word in ["soatdan", "minutdan", "daqiqadan", "kundan", "ertaga", "bugun", "soat"]:
                if time_word in lower and any(x in lower for x in ["elsat", "eslat", "keyin", "song", "so'ng"]):
                    is_rem = True
                    break

        if is_rem:
            from services.ai_service import extract_smart_reminder
            from services.memory_service import memory_service
            parsed = extract_smart_reminder(query)
            if parsed and parsed.get("remind_at") and parsed.get("reminder_text"):
                rem_id = memory_service.add_reminder(
                    chat_id=message.chat.id,
                    reminder_text=parsed["reminder_text"],
                    remind_at=parsed["remind_at"],
                )
                await message.answer(
                    "⏰ **Eslatma muvaffaqiyatli saqlandi!**\n\n"
                    f"📌 **Vazifa:** {parsed['reminder_text']}\n"
                    f"🕒 **Vaqti:** `{parsed['remind_at']}` (Toshkent vaqti)\n"
                    f"🆔 **ID:** `{rem_id}`\n\n"
                    "_Vaqti kelganda bot sizga eslatma xabarini yuboradi._",
                    parse_mode="Markdown",
                )
                return

        # Boshqa hollarda menyuni eslatish
        kb = get_private_keyboard(message.from_user.id)
        await message.answer(
            "👋 **coddyHelper Admin Bot**\n\n"
            "Eslatma o'rnatish uchun:\n"
            "• `eslatma 2 soatdan keyin dars`\n"
            "• `eslatma 30 minutdan song kitob o'qish`\n"
            "• `eslatma ertaga 10:00 da imtihon`\n\n"
            "Boshqaruv panelini ochish uchun quyidagi tugmani bosing 👇",
            reply_markup=kb,
        )


async def send_or_update_database_backup() -> tuple[bool, str]:
    """
    coddy_memory.db faylini bot (@coddyassistanstbot) orqali adminga yuboradi.
    Muhim: Izbrannoe (Saved Messages) ga tashlamaydi.
    Eski xabarni o'chirib, yangi ma'lumotlar qo'shilgan yangi faylni tashlaydi.
    Shunday qilib, bot chatida faqat bitta, eng so'nggi va to'liq baza saqlanadi.
    """
    global bot
    if not bot:
        if config.bot_token:
            bot = Bot(token=config.bot_token)
        else:
            return False, "BOT_TOKEN mavjud emas"

    db_path = Path("coddy_memory.db")
    if not db_path.exists():
        return False, "coddy_memory.db fayli topilmadi"

    try:
        from services.memory_service import memory_service
        # SQLite xotirasini diskka to'liq flush/checkpoint qilish
        try:
            with memory_service._get_connection() as conn:
                conn.commit()
                conn.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass

        tashkent_tz = ZoneInfo("Asia/Tashkent")
        now_str = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = db_path.stat().st_size / 1024.0

        # Statistikani hisoblash
        total_chats = memory_service.total_active_chats()
        active_reminders = len(memory_service.get_active_reminders(100))

        caption = (
            "💾 **coddy_memory.db Zaxira Nusxasi (Eng so'nggi)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ **Vaqt:** `{now_str}` (Toshkent vaqti)\n"
            f"📦 **Hajm:** `{size_kb:.1f} KB`\n"
            f"📊 **Baza ko'rsatkichlari:**\n"
            f"  • Saqlangan chatlar: {total_chats} ta\n"
            f"  • Faol eslatmalar: {active_reminders} ta\n\n"
            "ℹ️ *Ushbu fayl barcha avvalgi va yangi ma'lumotlarni o'zida to'liq saqlaydi. "
            "Yangi zaxira kelganda ushbu xabar o'rniga yangisi kelib, eskisi avtomatik o'chiriladi.*"
        )

        doc_file = FSInputFile(str(db_path), filename="coddy_memory.db")
        new_msg = await bot.send_document(
            chat_id=config.mentor_user_id,
            document=doc_file,
            caption=caption,
        )

        # 2. Avvalgi barcha eski backup xabarlarini tozalash
        # A) Bazada saqlangan avvalgi aniq ID
        old_msg_id = memory_service.get_setting("last_backup_bot_msg_id")
        if old_msg_id and str(old_msg_id).isdigit() and int(old_msg_id) != new_msg.message_id:
            try:
                await bot.delete_message(chat_id=config.mentor_user_id, message_id=int(old_msg_id))
            except Exception:
                pass

        # B) Bot chatidagi barcha oldingi xabarlarni to'liq tozalash (100 talik paketlarda)
        # Bu Render serveri qayta ishga tushganda ham oldingi deploylardan qolgan har qanday eski fayllarni tozalaydi
        start_id = max(1, new_msg.message_id - 200)
        ids_to_delete = [mid for mid in range(start_id, new_msg.message_id)]
        for i in range(0, len(ids_to_delete), 100):
            batch = ids_to_delete[i : i + 100]
            try:
                await bot.delete_messages(chat_id=config.mentor_user_id, message_ids=batch)
            except Exception as batch_err:
                logger.debug("Paketlab o'chirishda ogohlantirish: %s", batch_err)
                for mid in batch:
                    try:
                        await bot.delete_message(chat_id=config.mentor_user_id, message_id=mid)
                    except Exception:
                        pass

        # 3. Yangi xabar ID sini saqlash
        memory_service.set_setting("last_backup_bot_msg_id", str(new_msg.message_id))
        logger.info("Yangi backup bot orqali yuborildi (MsgID: %d), oldingi xabarlar tozalandi.", new_msg.message_id)
        return True, "OK"
    except Exception as e:
        logger.error("Database backup botga yuborishda xatolik: %s", e)
        return False, str(e)


async def post_group_panel_button(chat_id: int | str) -> tuple[bool, str]:
    global bot
    if not bot:
        return False, "Bot ishga tushmagan (BOT_TOKEN kiritilmagan)"

    try:
        s = str(chat_id).strip()
        cid = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else s

        kb = get_group_keyboard(config.mentor_user_id)
        group_text = (
            "🎛 <b>coddyHelper — Boshqaruv Paneli (Mini App)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Assalomu alaykum, Ustoz (<b>@mentor_cc</b>)!\n\n"
            "Guruhdan turib botni boshqarish uchun pastdagi tugmani bosing:\n\n"
            "🛡 <i>Xavfsizlik: Faqat mentor (<b>@mentor_cc</b>) uchun ruxsat etilgan.</i>"
        )

        sent = await bot.send_message(chat_id=cid, text=group_text, reply_markup=kb, parse_mode="HTML")
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
        # Begona foydalanuvchilar uchun standart bo'sh menyu
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

        # Faqat mentor (admin) uchun maxsus Admin Panel menu tugmasi
        admin_id = config.mentor_user_id or 8105823872
        token = MASTER_ADMIN_TOKEN
        app_url = f"{config.web_app_url}/app?token={token}"
        await bot.set_chat_menu_button(
            chat_id=admin_id,
            menu_button=MenuButtonWebApp(
                text="📱 Admin Panel",
                web_app=WebAppInfo(url=app_url),
            ),
        )
        logger.info("✅ Bot Menu Button faqat admin uchun muvaffaqiyatli sozlandi.")
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
