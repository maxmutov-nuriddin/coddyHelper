"""
Telegram Bot xizmati (aiogram 3)
Multi-User Obuna Tizimi:
- Super Admin (@mentor_cc) — to'liq boshqaruv, /grant, /revoke, /clients
- Obunali mijozlar — o'z guruhida shaxsiy AI yordamchi
- Ruxsatsiz foydalanuvchilar — bloklash
- Avtomatik guruh onboarding (ChatMemberUpdated)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    MenuButtonDefault,
    FSInputFile,
    LabeledPrice,
)
import os
from config import config, is_escalation_chat
from web_app import generate_admin_token
from services.tenant_context import tenant_scope

# Telegram Stars orqali obuna sotib olish (0 = o'chiq). Narx biznes qarori — env orqali yoqiladi.
SUBSCRIPTION_STARS_PRICE = int(os.getenv("SUBSCRIPTION_STARS_PRICE", "0") or 0)
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30") or 30)

logger = logging.getLogger("coddyHelper.bot_service")

bot: Bot | None = None
dp: Dispatcher | None = None
_polling_task: asyncio.Task | None = None


def is_admin(user_id: int | None) -> bool:
    """Faqat belgilangan mentor ID si ruxsat etilganini tekshiradi (Super Admin)."""
    if not user_id:
        return False
    return user_id == config.mentor_user_id or user_id == 8105823872


def is_authorized_user(user_id: int | None) -> bool:
    """Super Admin YOKI faol obunali foydalanuvchini tekshiradi."""
    if not user_id:
        return False
    if is_admin(user_id):
        return True
    try:
        from services.memory_service import memory_service
        return memory_service.is_subscription_active(user_id)
    except Exception:
        return False


def get_private_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Lichka uchun WebApp ochuvchi tugmalar to'plami."""
    # Shaxsiy (faqat shu foydalanuvchiga ko'rinadigan) tugma — shaxsiy, muddatli token bilan
    token = generate_admin_token(user_id=user_id)
    app_url = f"{config.web_app_url}/app?token={token}"
    buttons = [
        [
            InlineKeyboardButton(
                text="📱 Admin Panelni Ochish (Mini App)",
                web_app=WebAppInfo(url=app_url),
            )
        ]
    ]
    if is_admin(user_id):
        buttons.append([
            InlineKeyboardButton(
                text="💾 Baza Zaxirasini Yangilash (Backup)",
                callback_data="refresh_backup",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_group_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    """
    Guruh uchun tugma. XAVFSIZLIK: guruhdagi xabarni HAMMA ko'radi, shuning uchun unda token bo'lmaydi —
    tugma botning shaxsiy chatini ochadi, u yerda har kim faqat o'z huquqi bo'yicha panel oladi.
    """
    app_url = f"https://t.me/{(config.bot_username or 'coddyassistanstbot').lstrip('@')}?start=panel"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Admin Panelni Ochish (Mini App)",
                    url=app_url,
                )
            ],
        ],
    )


async def setup_bot_handlers(d: Dispatcher) -> None:
    """Bot handlerlarini ro'yxatga oladi va multi-user ruxsat tizimini o'rnatadi."""

    @d.message.outer_middleware
    async def access_control_middleware(handler, event: types.Message, data):
        """Super Admin va obunali mijozlarni qo'yib beruvchi middleware."""
        sender = event.from_user
        sender_id = sender.id if sender else None

        # /start, /buy va to'lov xabarlarini DOIM qo'yib berish (obuna tekshiruvi handler ichida)
        text = (event.text or "").strip().lower()
        if text.startswith("/start") or text.startswith("/buy") or text.startswith("/tarif") or getattr(event, "successful_payment", None):
            return await handler(event, data)

        # Super Admin — to'liq dostup (asosiy baza)
        if is_admin(sender_id):
            return await handler(event, data)

        # Obunali foydalanuvchi — barcha amallar FAQAT o'z tenant bazasida
        # (avval eslatmalari mentor bazasiga tushardi, /bekor bilan mentorning eslatmasini o'chira olardi)
        if is_authorized_user(sender_id):
            with tenant_scope(sender_id):
                return await handler(event, data)

        # Ruxsatsiz foydalanuvchi
        if event.chat.type == "private":
            try:
                await event.bot.set_chat_menu_button(
                    chat_id=sender_id,
                    menu_button=MenuButtonDefault(),
                )
            except Exception:
                pass
            await event.answer(
                "⛔ Sizga hali ruxsat berilmagan.\n\n"
                "Obuna olish uchun Super Admin (@mentor_cc) ga murojaat qiling."
            )
        return

    @d.callback_query.outer_middleware
    async def access_callback_middleware(handler, event: types.CallbackQuery, data):
        """Callback-lar uchun multi-user ruxsat tekshiruvi."""
        sender = event.from_user
        sender_id = sender.id if sender else None

        if not is_authorized_user(sender_id):
            await event.answer(
                "⛔ Sizga ruxsat berilmagan. Obuna uchun @mentor_cc ga murojaat qiling.",
                show_alert=True,
            )
            return

        if is_admin(sender_id):
            return await handler(event, data)
        with tenant_scope(sender_id):
            return await handler(event, data)

    @d.message(F.chat.type == "private", Command(commands=["start", "panel", "app", "admin", "menu"]))
    async def cmd_start_private(message: types.Message):
        """Lichkada /start — Super Admin, Obunachi va Ruxsatsiz uchun turli xabarlar."""
        from services.memory_service import memory_service
        user_id = message.from_user.id

        # ——— 1. SUPER ADMIN ———
        if is_admin(user_id):
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
                "🔧 **Super Admin buyruqlari:**\n"
                "• `/grant <user_id> <kun> [biznes nomi]` — Mijozga dostup ochish\n"
                "• `/revoke <user_id>` — Dostupni yopish\n"
                "• `/clients` — Barcha mijozlar ro'yxati\n\n"
                "Pastdagi tugmani bosing 👇",
                reply_markup=kb,
            )
            return

        # ——— 2. OBUNALI FOYDALANUVCHI ———
        sub = memory_service.get_subscription(user_id)
        if sub and sub.get("active") and not sub.get("is_expired"):
            # Menu button sozlash
            try:
                token = generate_admin_token(user_id=user_id)
                app_url = f"{config.web_app_url}/app?token={token}"
                await message.bot.set_chat_menu_button(
                    chat_id=user_id,
                    menu_button=MenuButtonWebApp(
                        text="📱 Boshqaruv",
                        web_app=WebAppInfo(url=app_url),
                    ),
                )
            except Exception as mb_err:
                logger.warning("Menu buttonni sozlashda ogohlantirish: %s", mb_err)

            biz_name = sub.get("business_name") or "Mening Boshqaruvim"
            expires = sub.get("expires_at", "—")
            group_id = sub.get("group_id") or 0

            if group_id:
                # Guruhi allaqachon ulangan
                kb = get_private_keyboard(user_id)
                await message.answer(
                    f"👋 **Assalomu alaykum, {biz_name}!**\n\n"
                    f"✅ Obunangiz **{expires}** gacha faol.\n"
                    f"📌 Shaxsiy guruhingiz ulangan (ID: `{group_id}`).\n\n"
                    "🤖 Panelda **Mening Agentim** bo'limidan Telegram akkauntingizni ulab, "
                    "shaxsiy AI agentingizni ishga tushiring.\n\n"
                    "Boshqaruv panelini ochish uchun quyidagi tugmani bosing 👇",
                    reply_markup=kb,
                )
            else:
                # Guruhi hali ulanmagan — ko'rsatma berish
                kb = get_private_keyboard(user_id)
                await message.answer(
                    f"👋 **Assalomu alaykum, {biz_name}!**\n\n"
                    f"✅ Profilingiz faollashtirildi! Obunangiz **{expires}** gacha.\n\n"
                    "📋 **Boshlash uchun:**\n"
                    "1️⃣ Pastdagi tugma orqali panelni oching\n"
                    "2️⃣ **🤖 Mening Agentim** bo'limida Telegram akkauntingizni ulang (raqam + kod)\n"
                    "3️⃣ **Bilimlar** bo'limiga biznesingiz qoidalari, narxlar va ma'lumotlarni kiriting\n\n"
                    "💡 _Ixtiyoriy: o'zingiz uchun yopiq guruh ochib, meni admin qilib qo'shsangiz, "
                    "u sizning boshqaruv guruhingiz sifatida biriktiriladi._",
                    reply_markup=kb,
                )
            return

        # ——— 3. RUXSATSIZ FOYDALANUVCHI ———
        try:
            await message.bot.set_chat_menu_button(
                chat_id=user_id,
                menu_button=MenuButtonDefault(),
            )
        except Exception:
            pass

        buy_line = "💳 Onlayn obuna: /buy (Telegram Stars)\n" if SUBSCRIPTION_STARS_PRICE > 0 else ""
        await message.answer(
            "⛔ **Kechirasiz, sizda hali faol obuna yo'q.**\n\n"
            "Shaxsiy AI yordamchi olish uchun Super Admin bilan bog'laning:\n"
            "👉 @mentor_cc\n"
            f"{buy_line}\n"
            "Obuna olganingizdan so'ng, /start ni qaytadan bosing.",
        )

    @d.message(F.chat.type.in_(["group", "supergroup"]), Command(commands=["panel", "button", "pin_button", "app", "admin"]))
    async def cmd_group_panel(message: types.Message):
        """Guruhda /panel — foydalanuvchiga mos Mini App tugma chiqarish."""
        from services.memory_service import memory_service
        user_id = message.from_user.id
        kb = get_group_keyboard(user_id)

        # Foydalanuvchiga mos matn
        if is_admin(user_id):
            owner_name = "Ustoz (<b>@mentor_cc</b>)"
        else:
            sub = memory_service.get_subscription(user_id)
            owner_name = f"<b>{sub.get('business_name', 'Foydalanuvchi')}</b>" if sub else "Foydalanuvchi"

        group_text = (
            "🎛 <b>coddyHelper — Boshqaruv Paneli (Mini App)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Assalomu alaykum, {owner_name}!\n\n"
            "Guruhdan turib botni boshqarish uchun pastdagi tugmani bosing:\n\n"
            "🛡 <i>Xavfsizlik: Faqat ruxsat etilgan foydalanuvchilar uchun.</i>"
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

    # =========================================================================
    # Super Admin buyruqlari: /grant, /revoke, /clients
    # =========================================================================

    @d.message(F.chat.type == "private", Command(commands=["grant"]))
    async def cmd_grant(message: types.Message):
        """/grant <user_id> <kun> [biznes nomi] — Yangi mijozga obuna ochish."""
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Bu buyruq faqat Super Admin uchun.")
            return

        from services.memory_service import memory_service
        args = (message.text or "").split(maxsplit=3)
        # /grant <user_id_yoki_@username> <kunlar> [biznes_nomi]
        if len(args) < 3:
            await message.answer(
                "ℹ️ **Foydalanish:**\n"
                "`/grant <user_id> <kun> [biznes nomi]`\n\n"
                "**Misollar:**\n"
                "• `/grant 123456789 30 Akmal Mebel`\n"
                "• `/grant @akmal_ceo 90 Akmal IT Solutions`"
            )
            return

        target = args[1].strip().lstrip("@")
        try:
            days = int(args[2])
        except ValueError:
            await message.answer("❌ Kunlar soni raqam bo'lishi kerak. Masalan: `/grant 123456789 30`")
            return

        business_name = args[3].strip() if len(args) > 3 else ""

        # @username berilsa — mentorning Telegram clienti orqali raqamli ID ga aylantiramiz
        full_name = ""
        try:
            target_user_id = int(target)
        except ValueError:
            target_user_id = 0
            try:
                from services import runtime
                if runtime.main_client:
                    entity = await runtime.main_client.get_entity(target)
                    if getattr(entity, "bot", False) or not hasattr(entity, "first_name"):
                        raise ValueError("bu foydalanuvchi emas")
                    target_user_id = entity.id
                    full_name = " ".join(x for x in (entity.first_name, entity.last_name) if x).strip()
            except Exception as res_err:
                logger.info("Username'ni aniqlab bo'lmadi (%s): %s", target, res_err)
            if not target_user_id:
                await message.answer(
                    f"⚠️ @{target} topilmadi.\n\n"
                    "Raqamli Telegram ID bilan urinib ko'ring (foydalanuvchi @userinfobot ga yozib bilib oladi)."
                )
                return

        sub = memory_service.upsert_subscription(
            user_id=target_user_id,
            username=target if not target.isdigit() else "",
            full_name=full_name,
            days=days,
            business_name=business_name,
        )

        if sub:
            await message.answer(
                f"✅ **Obuna muvaffaqiyatli ochildi!**\n\n"
                f"👤 **User ID:** `{target_user_id}`\n"
                f"🏢 **Biznes:** {sub.get('business_name', '—')}\n"
                f"📅 **Muddat:** {days} kun ({sub.get('expires_at', '—')} gacha)\n"
                f"📌 **Guruh:** {'Ulangan ✅' if sub.get('group_id') else 'Hali ulanmagan ⏳'}\n\n"
                f"Foydalanuvchi endi @coddyassistanstbot ga kirib /start bosishi kerak.",
            )
        else:
            await message.answer("❌ Obuna ochishda xatolik yuz berdi.")

    @d.message(F.chat.type == "private", Command(commands=["revoke"]))
    async def cmd_revoke(message: types.Message):
        """/revoke <user_id> — Mijoz obunasini to'xtatish."""
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Bu buyruq faqat Super Admin uchun.")
            return

        from services.memory_service import memory_service
        args = (message.text or "").split()
        if len(args) < 2:
            await message.answer("ℹ️ **Foydalanish:** `/revoke <user_id>`\n\nMasalan: `/revoke 123456789`")
            return

        try:
            target_id = int(args[1])
        except ValueError:
            await message.answer("❌ User ID raqam bo'lishi kerak.")
            return

        ok = memory_service.revoke_subscription(target_id)
        if ok:
            await message.answer(f"✅ **User `{target_id}` obunasi to'xtatildi.**")
        else:
            await message.answer(f"❌ User `{target_id}` obunasini to'xtatishda xatolik.")

    @d.message(F.chat.type == "private", Command(commands=["clients", "mijozlar"]))
    async def cmd_clients(message: types.Message):
        """/clients — Barcha obunali mijozlar ro'yxati."""
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Bu buyruq faqat Super Admin uchun.")
            return

        from services.memory_service import memory_service
        subs = memory_service.get_all_subscriptions()
        if not subs:
            await message.answer("ℹ️ Hozircha hech qanday mijoz obunasi yo'q.\n\nYangi qo'shish: `/grant <user_id> <kun> [biznes nomi]`")
            return

        lines = ["📋 **Barcha Mijozlar:**\n"]
        for i, s in enumerate(subs, 1):
            status = "✅ Faol" if s.get("active") else "❌ To'xtatilgan"
            username = f"@{s['username']}" if s.get("username") else "—"
            group = f"✅ `{s['group_id']}`" if s.get("group_id") else "⏳ Ulanmagan"
            lines.append(
                f"**{i}.** `{s['user_id']}` ({username})\n"
                f"   🏢 {s.get('business_name', '—')} | {status}\n"
                f"   📅 {s.get('expires_at', '—')} gacha | Guruh: {group}"
            )
        lines.append(f"\n**Jami:** {len(subs)} ta mijoz")
        await message.answer("\n".join(lines))

    # =========================================================================
    # ChatMemberUpdated — Bot guruhga qo'shilganda avtomatik onboarding
    # =========================================================================

    @d.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
    async def on_bot_added_to_group(event: types.ChatMemberUpdated):
        """Bot yangi guruhga qo'shilganda — avtomatik ulash va Mini App pin qilish."""
        from services.memory_service import memory_service

        # Faqat guruh/superguruhda ishlaydi
        if event.chat.type not in ("group", "supergroup"):
            return

        # Kim qo'shganini aniqlash
        adder = event.from_user
        adder_id = adder.id if adder else None
        group_id = event.chat.id
        group_title = event.chat.title or "Nomsiz guruh"

        logger.info("Bot guruhga qo'shildi: chat=%s (%s), qo'shgan=%s", group_id, group_title, adder_id)

        # 1. Super Admin qo'shgan — doim ruxsat
        if is_admin(adder_id):
            # Super Admin uchun alohida — uni ham link qilish (agar hali yo'q bo'lsa)
            # lekin asosiy escalation_chat uchun emas
            if str(group_id) not in (str(config.escalation_chat), "-1005388159517", "-5388159517"):
                memory_service.link_user_group(adder_id, group_id)

            kb = get_group_keyboard(adder_id)
            group_text = (
                "🎛 <b>coddyHelper — Boshqaruv Paneli (Mini App)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Assalomu alaykum, Ustoz (<b>@mentor_cc</b>)!\n\n"
                "Guruhdan turib botni boshqarish uchun pastdagi tugmani bosing:\n\n"
                "🛡 <i>Xavfsizlik: Faqat ruxsat etilgan foydalanuvchilar uchun.</i>"
            )
            try:
                sent = await event.bot.send_message(
                    chat_id=group_id, text=group_text, reply_markup=kb, parse_mode="HTML"
                )
                await event.bot.pin_chat_message(
                    chat_id=group_id, message_id=sent.message_id, disable_notification=True
                )
                logger.info("Super Admin guruhi uchun Mini App pin qilindi: %s", group_id)
            except Exception as e:
                logger.warning("Guruhga xabar yuborishda xatolik: %s", e)
            return

        # 2. Obunali foydalanuvchi qo'shgan — tekshirish va ulash
        if is_authorized_user(adder_id):
            sub = memory_service.get_subscription(adder_id)
            if sub and sub.get("active") and not sub.get("is_expired"):
                # Guruhni foydalanuvchiga biriktirish
                memory_service.link_user_group(adder_id, group_id)
                biz_name = sub.get("business_name") or "Mening Boshqaruvim"

                kb = get_group_keyboard(adder_id)
                welcome_text = (
                    f"🎛 <b>{biz_name} — Shaxsiy Boshqaruv Paneli</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Guruh muvaffaqiyatli ulandi!\n\n"
                    "Botni boshqarish uchun pastdagi tugmani bosing:\n\n"
                    "💡 <i>Bu guruhda bot barcha xabarlarni AI yordamida tahlil qiladi.</i>"
                )
                try:
                    sent = await event.bot.send_message(
                        chat_id=group_id, text=welcome_text, reply_markup=kb, parse_mode="HTML"
                    )
                    await event.bot.pin_chat_message(
                        chat_id=group_id, message_id=sent.message_id, disable_notification=True
                    )
                    logger.info("Mijoz guruhi ulandi va Mini App pin qilindi: user=%s, group=%s", adder_id, group_id)
                except Exception as e:
                    logger.warning("Mijoz guruhiga xabar yuborishda xatolik: %s", e)
                return

        # 3. Ruxsatsiz foydalanuvchi — ogohlantirish va chiqib ketish
        try:
            await event.bot.send_message(
                chat_id=group_id,
                text=(
                    "⛔ <b>Kechirasiz, sizda botdan foydalanish uchun ruxsat yo'q.</b>\n\n"
                    "Obuna olish uchun @mentor_cc ga murojaat qiling.\n\n"
                    "<i>Bot guruhdan chiqmoqda...</i>"
                ),
                parse_mode="HTML",
            )
            await event.bot.leave_chat(group_id)
            logger.info("Ruxsatsiz foydalanuvchi guruhi tark etildi: user=%s, group=%s", adder_id, group_id)
        except Exception as e:
            logger.warning("Ruxsatsiz guruhdan chiqishda xatolik: %s", e)

    @d.callback_query(F.data == "post_group_button")
    async def on_post_group_button(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            await call.answer("⛔ Bu amal faqat Super Admin uchun.", show_alert=True)
            return

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
        if not is_admin(call.from_user.id):
            await call.answer("⛔ Bu amal faqat Super Admin uchun.", show_alert=True)
            return

        await call.answer("⏳ Zaxira yangilanmoqda...")
        ok, err = await send_or_update_database_backup()
        if ok:
            await call.answer("✅ Baza botga yuborildi va eski xabar tozalandi!", show_alert=True)
        else:
            await call.answer(f"❌ Xatolik: {err}", show_alert=True)

    # 7. Lichka: /backup buyrug'i
    @d.message(F.chat.type == "private", Command(commands=["backup", "db", "baza"]))
    async def cmd_backup_private(message: types.Message):
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Bu buyruq faqat Super Admin uchun.")
            return

        await message.answer("⏳ **Baza zaxiralanmoqda va yangilanmoqda...**")
        ok, err = await send_or_update_database_backup()
        if not ok:
            await message.answer(f"❌ Xatolik yuz berdi: {err}")

    # 8. Lichka: Eslatmalar ro'yxati
    @d.message(F.chat.type == "private", Command(commands=["eslatmalar", "reminders"]))
    async def cmd_reminders_list(message: types.Message):
        from services.memory_service import memory_service
        reminders = memory_service.get_active_reminders(limit=50)
        if not is_admin(message.from_user.id):
            reminders = [r for r in reminders if r.get("chat_id") == message.chat.id or r.get("creator_id") == message.from_user.id]
        if not reminders:
            await message.answer("ℹ️ Hozirda hech qanday faol eslatma yo'q.\n\nYangi eslatma qo'shish uchun: `ai eslatma 2 soatdan keyin dars` deb yozing.")
            return

        lines = ["⏰ **Faol Eslatmalar Ro'yxati:**\n"]
        for r in reminders[:20]:
            lines.append(f"• **[ID: {r['id']}]** `{r['remind_at']}`: {r.get('task') or r.get('text', '')}")
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

    # 10. Lichka: Mentor tomonidan .db fayl yuborilganda avtomatik qabul qilish va birlashtirish
    @d.message(F.chat.type == "private", F.document)
    async def handle_db_document(message: types.Message):
        if not is_admin(message.from_user.id):
            return

        doc = message.document
        if not doc or not doc.file_name:
            return

        file_name = doc.file_name.lower()
        if file_name.endswith(".db") or file_name.endswith(".sqlite") or file_name.endswith(".sqlite3"):
            await message.answer("⏳ **Ma'lumotlar bazasi qabul qilinmoqda va birlashtirilmoqda...**")
            try:
                import tempfile
                tmp_dir = Path(tempfile.gettempdir()) / "coddy_restore"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp_file = tmp_dir / f"uploaded_{doc.file_name}"
                await message.bot.download(doc.file_id, destination=tmp_file)

                from services.memory_service import memory_service
                ok, msg = memory_service.merge_database(tmp_file)
                if ok:
                    await message.answer(
                        f"✅ **Baza muvaffaqiyatli qabul qilindi va birlashtirildi!**\n\n"
                        f"📊 **Natija:** {msg}\n\n"
                        f"Barcha eski va yangi ma'lumotlar saqlab qolindi.",
                        parse_mode="Markdown",
                    )
                else:
                    await message.answer(f"❌ Bazani birlashtirishda xatolik: {msg}")
                tmp_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error("DB faylini yuklab olishda xatolik: %s", e)
                await message.answer(f"❌ Xatolik yuz berdi: {e}")

    # 10.5 Telegram Stars orqali obuna sotib olish / uzaytirish (SUBSCRIPTION_STARS_PRICE > 0 bo'lsa)
    @d.message(F.chat.type == "private", Command(commands=["buy", "tarif"]))
    async def cmd_buy(message: types.Message):
        if SUBSCRIPTION_STARS_PRICE <= 0:
            await message.answer("ℹ️ Onlayn to'lov hozircha yoqilmagan. Obuna uchun @mentor_cc ga murojaat qiling.")
            return
        uid = message.from_user.id
        await message.bot.send_invoice(
            chat_id=uid,
            title=f"AI Agent obunasi — {SUBSCRIPTION_DAYS} kun",
            description="Shaxsiy AI agent: Telegramingizda siz nomingizdan javob beradi, alohida xavfsiz baza, Mini App boshqaruvi.",
            payload=f"sub:{uid}:{SUBSCRIPTION_DAYS}",
            currency="XTR",
            prices=[LabeledPrice(label=f"{SUBSCRIPTION_DAYS} kunlik obuna", amount=SUBSCRIPTION_STARS_PRICE)],
            provider_token="",
        )

    @d.pre_checkout_query()
    async def on_pre_checkout(query: types.PreCheckoutQuery):
        ok = (
            SUBSCRIPTION_STARS_PRICE > 0
            and query.currency == "XTR"
            and query.total_amount == SUBSCRIPTION_STARS_PRICE
            and query.invoice_payload == f"sub:{query.from_user.id}:{SUBSCRIPTION_DAYS}"
        )
        await query.answer(ok=ok, error_message=None if ok else "To'lov ma'lumotlari mos kelmadi. Qaytadan /buy bosing.")

    @d.message(F.successful_payment)
    async def on_successful_payment(message: types.Message):
        from services.memory_service import memory_service
        pay = message.successful_payment
        uid = message.from_user.id
        charge_id = pay.telegram_payment_charge_id
        # Idempotentlik: bir to'lov ikki marta hisoblanmasin
        if memory_service.get_setting(f"payment_{charge_id}"):
            return
        if pay.currency != "XTR" or pay.invoice_payload != f"sub:{uid}:{SUBSCRIPTION_DAYS}":
            logger.warning("Shubhali to'lov payloadi: user=%s payload=%s", uid, pay.invoice_payload)
            return
        memory_service.set_setting(f"payment_{charge_id}", f"{uid}:{pay.total_amount}")
        sub = memory_service.upsert_subscription(
            user_id=uid,
            username=message.from_user.username or "",
            full_name=message.from_user.full_name or "",
            days=SUBSCRIPTION_DAYS,
        )
        await message.answer(
            f"✅ <b>To'lov qabul qilindi!</b>\n\nObunangiz <b>{sub.get('expires_at', '—')}</b> gacha faol.\n"
            "Boshlash uchun /start bosing.",
            parse_mode="HTML",
        )
        try:
            from services.notify import notify_super_admin
            await notify_super_admin(
                f"💰 <b>Yangi to'lov</b>: {message.from_user.full_name} (<code>{uid}</code>) — "
                f"{pay.total_amount} ⭐, obuna {sub.get('expires_at', '—')} gacha."
            )
        except Exception:
            pass

    # 11. Lichka: Yangi eslatma qo'shish yoki matnli xabarlar
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

        # AI bilan muloqot: agar xabar 'ai ' bilan boshlansa
        if lower.startswith("ai ") or lower.startswith("/ai "):
            ai_query = text[3:].strip() if lower.startswith("ai ") else text[4:].strip()
            if ai_query:
                from services.ai_service import ai_service
                try:
                    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
                    res = await ai_service.generate_reply(
                        chat_id=message.chat.id,
                        user_message=ai_query,
                        user_id=message.from_user.id,
                    )
                    # AIResult — bu str (avval `.text` chaqirilib AttributeError bo'lardi)
                    if res and str(res).strip():
                        await message.answer(str(res))
                        return
                except Exception as ai_err:
                    logger.warning("Botda AI javob olishda xatolik: %s", ai_err)

        # Boshqa hollarda menyuni eslatish
        kb = get_private_keyboard(message.from_user.id)
        await message.answer(
            "👋 **coddyHelper Admin Bot**\n\n"
            "Eslatma o'rnatish uchun:\n"
            "• `eslatma 2 soatdan keyin dars`\n"
            "• `eslatma 30 minutdan song kitob o'qish`\n"
            "• `eslatma ertaga 10:00 da imtihon`\n\n"
            "AI yordamchiga murojaat qilish uchun:\n"
            "• `ai <savolingiz yoki vazifangiz>`\n\n"
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

        # 2. Faqat avvalgi bitta eski backup xabarini tozalash (boshqa xabarlarga tegilmaydi)
        old_msg_id = memory_service.get_setting("last_backup_bot_msg_id")
        if old_msg_id and str(old_msg_id).isdigit() and int(old_msg_id) != new_msg.message_id:
            try:
                await bot.delete_message(chat_id=config.mentor_user_id, message_id=int(old_msg_id))
            except Exception as del_err:
                logger.debug("Avvalgi backup xabarini o'chirishda ogohlantirish: %s", del_err)

        # 3. Yangi xabar ID sini saqlash
        memory_service.set_setting("last_backup_bot_msg_id", str(new_msg.message_id))
        logger.info("Yangi backup bot orqali yuborildi (MsgID: %d).", new_msg.message_id)
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


async def ensure_vazifalar_panel_pinned() -> None:
    """
    Support (Vazifalar / Boshqaruv) guruhiga Admin Panel tugmasini yuborib, pin qiladi —
    ustoz shu yerdan bir tegishda panelga (Mini App) kira oladi.
    Idempotent: agar tugma allaqachon o'sha guruhda pin qilingan bo'lsa, qayta yuborilmaydi (spam bo'lmaydi).
    """
    global bot
    if not bot:
        return
    from services.memory_service import memory_service
    from config import get_vazifalar_chat_target_sync

    try:
        chat_target = get_vazifalar_chat_target_sync()
        s = str(chat_target).strip()
        if not s or s.lower() in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
            logger.info("Vazifalar guruhi aniqlanmadi — panel pin qilinmadi.")
            return
        cid = int(s) if (s.isdigit() or (s.startswith("-") and s[1:].isdigit())) else s

        # 1. Allaqachon pin qilinganmi? (restartda takror yubormaslik uchun)
        saved_id = memory_service.get_setting("vazifalar_panel_msg_id")
        if saved_id and str(saved_id).isdigit():
            try:
                chat = await bot.get_chat(cid)
                pinned = getattr(chat, "pinned_message", None)
                if pinned and pinned.message_id == int(saved_id):
                    logger.info("✅ Vazifalar guruhida Admin Panel tugmasi allaqachon pin qilingan (MsgID: %s).", saved_id)
                    return
            except Exception as chk_err:
                logger.debug("Pin holatini tekshirishda ogohlantirish: %s", chk_err)

        # 2. Yangi panel tugmasini yuborib pin qilish
        kb = get_group_keyboard(config.mentor_user_id)
        group_text = (
            "🎛 <b>coddyHelper — Boshqaruv Paneli</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Ustoz (<b>@mentor_cc</b>), boshqaruv panelini (Mini App) shu yerdan oching 👇\n\n"
            "🛡 <i>Faqat siz uchun. Boshqa a'zolar bossa, ularga ruxsat berilmaydi.</i>"
        )
        sent = await bot.send_message(chat_id=cid, text=group_text, reply_markup=kb, parse_mode="HTML")
        try:
            await bot.pin_chat_message(chat_id=cid, message_id=sent.message_id, disable_notification=True)
        except Exception as pin_err:
            logger.warning("Vazifalar guruhida panelni pin qilib bo'lmadi: %s", pin_err)
        # Eski panel xabarini tozalash
        old_id = memory_service.get_setting("vazifalar_panel_msg_id")
        if old_id and str(old_id).isdigit() and int(old_id) != sent.message_id:
            try:
                await bot.delete_message(chat_id=cid, message_id=int(old_id))
            except Exception:
                pass
        memory_service.set_setting("vazifalar_panel_msg_id", str(sent.message_id))
        logger.info("📌 Vazifalar guruhiga Admin Panel tugmasi yuborildi va pin qilindi (MsgID: %d).", sent.message_id)
    except Exception as e:
        logger.warning("Vazifalar guruhiga panel tugmasini o'rnatishda ogohlantirish: %s", e)


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
        token = generate_admin_token(user_id=admin_id)
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

    # Support (Vazifalar) guruhiga Admin Panel tugmasini yuborib pin qilish (idempotent)
    async def _pin_panel_after_start():
        await asyncio.sleep(8)  # bot ulanishi to'liq tayyor bo'lishi uchun
        await ensure_vazifalar_panel_pinned()
    asyncio.create_task(_pin_panel_after_start())

    logger.info("🚀 Telegram Bot polling xizmati faollashdi.")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=False,
    )


async def stop_bot_service() -> None:
    global bot, dp
    if dp:
        await dp.stop_polling()
    if bot:
        await bot.session.close()
    logger.info("🛑 Telegram Bot xizmati to'xtatildi.")
