"""
Foydalanuvchi buyruqlari (Userbot komandalari)
"""

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from config import config
from services.ai_service import ai_service
from services.memory_service import memory_service

logger = logging.getLogger(__name__)


def register_command_handlers(client: TelegramClient) -> None:
    prefix = config.command_prefix

    @client.on(events.NewMessage(outgoing=True))
    async def handle_user_command(event: events.NewMessage.Event):
        raw_text = (event.raw_text or "").strip()
        lower_text = raw_text.lower()

        # -----------------------------------------------------------
        # 0. Xavfsizlik: Sirli so'zlar orqali to'liq to'xtatish va yoqish
        # Masalan: "ai stop", "ai start", yoki .env dagi maxsus so'zlar
        # -----------------------------------------------------------
        stop_triggers = {
            config.secret_stop_word,
            "ai stop",
            "coddy stop",
            f"{prefix}ai stop",
            f"{prefix}ai off",
            f"{prefix}stop",
        }
        start_triggers = {
            config.secret_start_word,
            "ai start",
            "coddy start",
            f"{prefix}ai start",
            f"{prefix}ai on",
            f"{prefix}start",
        }

        group_stop_triggers = {
            config.secret_group_stop_word,
            "guruh stop",
            "guruhlar stop",
            "group stop",
            "ai group stop",
            "ai guruh stop",
            f"{prefix}group off",
            f"{prefix}group stop",
            f"{prefix}guruh off",
            f"{prefix}guruh stop",
        }
        group_start_triggers = {
            config.secret_group_start_word,
            "guruh start",
            "guruhlar start",
            "group start",
            "ai group start",
            "ai guruh start",
            f"{prefix}group on",
            f"{prefix}group start",
            f"{prefix}guruh on",
            f"{prefix}guruh start",
        }

        help_triggers = {
            "help",
            "yordam",
            "komandalar",
            "commands",
            f"{prefix}help",
            f"{prefix}yordam",
        }
        status_triggers = {
            "status",
            "holat",
            f"{prefix}status",
            f"{prefix}holat",
        }
        panel_triggers = {
            "panel",
            "app",
            "admin",
            "webapp",
            f"{prefix}panel",
            f"{prefix}app",
            f"{prefix}admin",
            f"{prefix}webapp",
            "/panel",
            "/app",
            "/admin",
            "button",
            "tugma",
            f"{prefix}button",
            f"{prefix}tugma",
            "/button",
        }

        # Telegram Mini App Admin Panel ochish
        if lower_text in panel_triggers:
            from web_app import generate_admin_token
            sender_id = event.sender_id or config.mentor_user_id
            token = generate_admin_token(user_id=sender_id)
            app_url = f"{config.web_app_url}/app?token={token}"

            if event.is_private:
                await event.edit(
                    "🎛 **coddyHelper — Telegram Mini App (Admin Panel)**\n\n"
                    "Boshqaruv panelingiz muvaffaqiyatli ochildi!\n\n"
                    f"👉 **[Admin Panelni Ochish (Mini App)]({app_url})**\n\n"
                    "🛡 *Xavfsizlik: Ushbu havola faqat siz (@mentor_cc) uchun shaxsiy token bilan himoyalangan.*"
                )
            else:
                try:
                    await client.send_message(
                        "me",
                        "🎛 **coddyHelper — Admin Panel Xavfsiz Havolasi**\n\n"
                        f"Guruhdan ({event.chat_id}) chaqirilgan boshqaruv paneli:\n"
                        f"👉 **[Admin Panelni Ochish (Mini App)]({app_url})**\n\n"
                        "🛡 *Ushbu havola faqat siz uchun faol.*"
                    )
                except Exception as me_err:
                    logger.warning("Saved messages ga yuborib bo'lmadi: %s", me_err)

                # Agar Telegram Bot ulangan bo'lsa, guruhga haqiqiy tugmali xabar chiqarib, pin qilamiz
                if config.bot_token:
                    try:
                        from services.bot_service import post_group_panel_button
                        ok, _ = await post_group_panel_button(event.chat_id)
                        if ok:
                            await event.delete()
                            return
                    except Exception as b_err:
                        logger.warning("Bot orqali tugma chiqarishda ogohlantirish: %s", b_err)

                await event.edit(
                    "🔐 **coddyHelper Admin Panel**\n\n"
                    "Boshqaruv paneli havolasi shaxsiy xabarlaringizga ([Saved Messages](tg://user?id=8105823872)) yuborildi!\n"
                    f"👉 To'g'ridan-to'g'ri ochish: [Boshqaruv Paneli]({app_url})\n\n"
                    "⚠️ *Xavfsizlik: Begona foydalanuvchilar kira olmaydi (Faqat @mentor_cc ruxsat etilgan).* "
                )
            return

        # Guruhlar avto-javobini boshqarish
        if lower_text in group_stop_triggers:
            config.group_reply_enabled = False
            memory_service.set_setting("group_reply_enabled", "false")
            await event.edit(
                "👥 **Guruhlar avto-javobi TO'XTATILDI (STOP)!**\n"
                "• AI endi guruhlardagi savollarga javob bermaydi.\n"
                "• Faqat shaxsiy xabarlarga (lichka) javob beradi.\n"
                "• Server restart bo'lsa ham bu holat saqlanadi.\n\n"
                "Qayta yoqish uchun: `guruh start` deb yozing."
            )
            return

        if lower_text in group_start_triggers:
            config.group_reply_enabled = True
            memory_service.set_setting("group_reply_enabled", "true")
            await event.edit(
                "👥 **Guruhlar avto-javobi ISHGA TUSHIRILDI (START)!**\n"
                "• AI guruhlardagi savollarga ham 5 soniya kutib javob beradi.\n"
                "• Agar 5 soniya ichida o'zingiz yozsangiz, AI to'xtaydi.\n"
                "• Server restart bo'lsa ham bu holat saqlanadi.\n\n"
                "O'chirish uchun: `guruh stop` deb yozing."
            )
            return

        if lower_text in stop_triggers:
            config.auto_reply_enabled = False
            memory_service.set_setting("auto_reply_enabled", "false")
            await event.edit(
                "🔒 **XAVFSIZLIK: AI Agent to'liq to'xtatildi!**\n"
                "• Avto-javob: O'chirilgan (shaxsiy va guruhlar)\n"
                "• Barcha xabarlar faqat siz tomondan qo'lda boshqariladi.\n"
                "• Server restart bo'lsa ham start deb yozmaguningizcha ISHLAMAYDI.\n\n"
                "Qayta faollashtirish uchun: `ai start` deb yozing."
            )
            return

        if lower_text in start_triggers:
            config.auto_reply_enabled = True
            memory_service.set_setting("auto_reply_enabled", "true")
            await event.edit(
                "🔓 **XAVFSIZLIK: AI Agent qayta faollashtirildi!**\n"
                "• Avto-javob: Yoqilgan\n"
                "• O'quvchilar xabarlariga 120B AI yordam berishni boshladi."
            )
            return

        # -----------------------------------------------------------
        # help va status buyruqlari (nuqtasiz ham ishlaydi, masalan "Vazifalar"da)
        # -----------------------------------------------------------
        if lower_text in help_triggers:
            help_text = (
                "🤖 **coddyHelper AI Yordamchi — Barcha Buyruqlar Ro'yxati:**\n\n"
                "🎛 **Asosiy Boshqaruv (Start / Stop):**\n"
                "• `ai stop` — AI'ni butunlay to'xtatish (lichka va guruhlarda to'xtaydi, server restart bo'lsa ham qayta yonmaydi)\n"
                "• `ai start` — AI'ni qayta ishga tushirish\n"
                "• `guruh start` — Guruhlardagi savollarga javob berishni yoqish\n"
                "• `guruh stop` — Guruhlarga javob berishni to'xtatish (faqat lichkada ishlaydi)\n\n"
                "⏰ **Aqlli Eslatmalar (Reminders):**\n"
                "• `ai eslatma <vaqt va vazifa>` — Eslatma o'rnatish (masalan: `ai eslatma ertaga 10:00 da dars`)\n"
                "• `eslatmalar` — Barcha faol eslatmalar ro'yxati\n"
                "• `ai eslatma bekor <ID>` — Eslatmani bekor qilish\n\n"
                "📚 **Ta'lim va Kod Tahlili:**\n"
                "• `tushuntir <mavzu>` — Mavzuni analogiya, kod va mini-mashq bilan tushuntirish\n"
                "• `review <github_link>` yoki reply qilib `review` — GitHub repozitoriy tahlili (Code Review)\n"
                "• `backup` — SQLite xotira bazasini Telegram fayl ko'rinishida yuklab olish\n\n"
                "📊 **Tizim va Mentor Analitikasi:**\n"
                "• `report` yoki `ai report` — O'quvchilar xatoliklari bo'yicha haftalik tahliliy hisobot\n"
                "• `status` yoki `.status` — Tizim holati (Lichka va Guruhlar holati, xotiradagi o'quvchilar soni)\n"
                "• `help` yoki `.help` — Ushbu buyruqlar ro'yxatini ko'rsatish\n\n"
                "🚫 **Spam / Hazilkashlardan Himoya (Ignore):**\n"
                "• `ai ignore @username` — O'quvchini bloklash (AI javob bermaydi)\n"
                "• `ai unignore @username` — Blokdan chiqarish\n"
                "• `ai ignored` — Bloklanganlar ro'yxati\n\n"
                "🛠 **Qo'lda Tezkor Ishlatish:**\n"
                f"• `{prefix}ai <savol>` — Tezkor AI javobini olish\n"
                f"• Biror xabar, rasm, audio yoki faylga reply qilib `{prefix}ai` deb yozish — O'sha xabarni AI orqali tahlil qilish\n"
                f"• `{prefix}clear` — Joriy chatdagi o'quvchi suhbat tarixini tozalash"
            )
            await event.edit(help_text)
            return

        if lower_text in status_triggers:
            auto_status = "🟢 Yoqilgan" if config.auto_reply_enabled else "🔴 O'chirilgan"
            group_status = "🟢 Yoqilgan" if config.group_reply_enabled else "🔴 O'chirilgan"
            active_chats = memory_service.total_active_chats()
            active_model = f"Groq ({config.groq_model})" if (config.groq_api_keys or config.groq_api_key) else f"Gemini ({config.gemini_model})"
            status_text = (
                "📊 **coddyHelper Tizim Holati**\n\n"
                f"- **Shaxsiy xabarlar (Lichka):** {auto_status}\n"
                f"- **Guruhlarda javob berish:** {group_status}\n"
                f"- **AI Modeli:** `{active_model}`\n"
                f"- **Kutish vaqti:** {config.mentor_wait_seconds} soniya\n"
                f"- **Xotiradagi faol chatlar:** {active_chats} ta\n"
                f"- **Buyruqlar prefiksi:** `{config.command_prefix}`\n"
                f"- **Xotira chegarasi:** {config.memory_limit} ta xabar"
            )
            await event.edit(status_text)
            return

        # -----------------------------------------------------------
        # Analitika (Mentor Hisoboti)
        # -----------------------------------------------------------
        if lower_text in ("report", "ai report", ".report", f"{prefix}report", "hisobot", ".hisobot"):
            await event.edit("📊 **Oxirgi haftalik o'quvchilar xatoliklari tahlil qilinmoqda...**")
            questions = memory_service.get_recent_user_questions(limit=50)
            report_text = await ai_service.generate_mentor_report(questions)
            await event.edit(report_text)
            return

        # -----------------------------------------------------------
        # Ignore / Bloklash buyruqlari
        # -----------------------------------------------------------
        if lower_text in ("ai ignored", "ignored", ".ignored", f"{prefix}ignored"):
            ignored_list = memory_service.get_ignored_users()
            if not ignored_list:
                await event.edit("ℹ️ Hozirda hech qanday foydalanuvchi bloklanmagan.")
            else:
                lines = [f"• `{u['user_id']}` ({u['username'] or 'Noma\'lum'})" for u in ignored_list]
                await event.edit("🚫 **Bloklangan (AI javob bermaydigan) foydalanuvchilar:**\n\n" + "\n".join(lines))
            return

        is_ignore = False
        is_unignore = False
        target_arg = ""

        for kw in ["ai ignore", "ignore", f"{prefix}ignore"]:
            if lower_text.startswith(kw):
                is_ignore = True
                target_arg = raw_text[len(kw):].strip()
                break

        if not is_ignore:
            for kw in ["ai unignore", "unignore", f"{prefix}unignore"]:
                if lower_text.startswith(kw):
                    is_unignore = True
                    target_arg = raw_text[len(kw):].strip()
                    break

        if is_ignore:
            target_id = None
            target_uname = ""
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg:
                    target_id = reply_msg.sender_id
                    sender_ent = await reply_msg.get_sender()
                    if sender_ent and getattr(sender_ent, "username", None):
                        target_uname = f"@{sender_ent.username}"
            elif target_arg:
                try:
                    entity = await client.get_entity(target_arg)
                    target_id = entity.id
                    target_uname = f"@{entity.username}" if getattr(entity, "username", None) else ""
                except Exception:
                    if target_arg.isdigit():
                        target_id = int(target_arg)
                    elif target_arg.startswith("@"):
                        target_uname = target_arg
            else:
                target_id = event.chat_id

            if target_id:
                memory_service.ignore_user(target_id, target_uname)
                await event.edit(
                    f"🚫 **Foydalanuvchi `{target_id}` {target_uname} bloklandi!**\n"
                    "• AI endi bu foydalanuvchiga javob bermaydi.\n\n"
                    f"Qayta ochish uchun: `ai unignore {target_id}`"
                )
            else:
                await event.edit("ℹ️ **Foydalanish:** `ai ignore @username` yoki xabarga reply qilib `ai ignore` deb yozing.")
            return

        if is_unignore:
            target_id = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.sender_id:
                    target_id = reply_msg.sender_id
            elif target_arg:
                try:
                    entity = await client.get_entity(target_arg)
                    target_id = entity.id
                except Exception:
                    if target_arg.isdigit():
                        target_id = int(target_arg)
            else:
                target_id = event.chat_id

            if target_id:
                res = memory_service.unignore_user(target_id)
                if res:
                    await event.edit(f"✅ **Foydalanuvchi `{target_id}` blokdan chiqarildi!**\n• AI yana uning savollariga javob beradi.")
                else:
                    await event.edit(f"ℹ️ Foydalanuvchi `{target_id}` bloklanganlar ro'yxatida topilmadi.")
            else:
                await event.edit("ℹ️ **Foydalanish:** `ai unignore @username`")
            return

        # -----------------------------------------------------------
        # Eslatmalar (Reminders)
        # -----------------------------------------------------------
        if lower_text in ("eslatmalar", "ai eslatmalar", ".eslatmalar", f"{prefix}eslatmalar"):
            active = memory_service.get_active_reminders()
            if not active:
                await event.edit("ℹ️ Hozirda hech qanday faol eslatma yo'q.\n\nYangi eslatma qo'shish: `ai eslatma ertaga 10:00 da dars o'tish`")
            else:
                lines = [
                    f"• **ID `{r['id']}`**: {r['text']}\n  🕒 `{r['remind_at']}`"
                    for r in active
                ]
                text = (
                    "⏰ **Faol Eslatmalar Ro'yxati (Toshkent vaqti):**\n\n"
                    + "\n\n".join(lines)
                    + "\n\nBekor qilish uchun: `ai eslatma bekor <ID>`"
                )
                await event.edit(text)
            return

        # Eslatmani bekor qilish
        is_cancel_reminder = False
        cancel_id_str = ""
        for kw in ["ai eslatma bekor", "eslatma bekor", f"{prefix}eslatma bekor"]:
            if lower_text.startswith(kw):
                is_cancel_reminder = True
                cancel_id_str = raw_text[len(kw):].strip()
                break

        if is_cancel_reminder:
            if cancel_id_str.isdigit():
                rem_id = int(cancel_id_str)
                deleted = memory_service.delete_reminder(rem_id)
                if deleted:
                    await event.edit(f"✅ **ID `{rem_id}` bo'lgan eslatma muvaffaqiyatli bekor qilindi!**")
                else:
                    await event.edit(f"ℹ️ ID `{rem_id}` bo'lgan faol eslatma topilmadi.")
            else:
                await event.edit("ℹ️ **Foydalanish:** `ai eslatma bekor <ID>`\nMasalan: `ai eslatma bekor 3`")
            return

        # Yangi eslatma qo'shish
        is_add_reminder = False
        reminder_query = ""
        for kw in ["ai eslatma", "eslatma", f"{prefix}eslatma"]:
            if lower_text.startswith(kw):
                is_add_reminder = True
                reminder_query = raw_text[len(kw):].strip()
                break

        if is_add_reminder:
            if not reminder_query:
                await event.edit(
                    "ℹ️ **Eslatma yaratish bo'yicha qo'llanma:**\n\n"
                    "Misollar:\n"
                    "• `ai eslatma 25 09 2026 15:00 da dars boshlanishi`\n"
                    "• `ai eslatma 25.09.2026 14:00 da imtihon`\n"
                    "• `ai eslatma ertaga 10:00 da AnyDesk orqali dars`\n"
                    "• `ai eslatma 15 daqiqadan keyin o'quvchiga yozish`\n"
                    "• `ai eslatma bugun soat 20:30 da guruhda e'lon berish`"
                )
                return

            await event.edit("⏳ **AI eslatma vaqti va vazifasini tahlil qilmoqda...**")
            now_tashkent = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
            parsed = await ai_service.parse_reminder_text(reminder_query, current_tashkent_time=now_tashkent)

            task_val = (parsed.get("reminder_text") or parsed.get("task")) if parsed else None
            if parsed and parsed.get("remind_at") and task_val:
                remind_at = parsed["remind_at"]
                task = task_val
                rem_id = memory_service.add_reminder(event.chat_id, task, remind_at)
                await event.edit(
                    "⏰ **Eslatma muvaffaqiyatli saqlandi!**\n\n"
                    f"📌 **Vazifa:** {task}\n"
                    f"🕒 **Vaqti:** `{remind_at}` (Toshkent vaqti)\n"
                    f"🆔 **ID:** `{rem_id}`\n\n"
                    "_Vaqti kelganda AI ushbu chatda eslatma xabarini yuboradi._"
                )
            else:
                await event.edit(
                    "❌ **Eslatmani aniqlab bo'lmadi!**\n"
                    "Iltimos, vaqt yoki muddatni aniqroq yozing.\n"
                    "Masalan: `ai eslatma 20 daqiqadan keyin dars boshlash` yoki `ai eslatma 18:00 da tekshirish`"
                )
            return

        # -----------------------------------------------------------
        # GitHub Code Review
        # -----------------------------------------------------------
        is_review = False
        review_arg = ""
        for kw in ["ai review", "review", f"{prefix}review"]:
            if lower_text.startswith(kw):
                is_review = True
                review_arg = raw_text[len(kw):].strip()
                break

        if is_review:
            github_url = None
            github_match = re.search(r"https?://github\.com/[^\s]+", review_arg)
            if github_match:
                github_url = github_match.group(0)
            elif event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.text:
                    rep_match = re.search(r"https?://github\.com/[^\s]+", reply_msg.text)
                    if rep_match:
                        github_url = rep_match.group(0)

            if not github_url:
                await event.edit(
                    "ℹ️ **GitHub Code Review ishlatish:**\n"
                    f"• `{prefix}review https://github.com/foydalanuvchi/loyiha`\n"
                    "• Yoki GitHub havolasi bor xabarga reply qilib `review` deb yozing."
                )
                return

            await event.edit(f"🔍 **GitHub repozitoriysi tahlil qilinmoqda:**\n`{github_url}`\n_Kodlar va arxitektura o'rganilmoqda..._")
            review_result = await ai_service.analyze_github_link(github_url)
            await event.edit(review_result)
            return

        # -----------------------------------------------------------
        # SQLite Database Backup
        # -----------------------------------------------------------
        if lower_text in ("backup", ".backup", "ai backup", f"{prefix}backup"):
            await event.edit("⏳ **Baza zaxiralanmoqda va botga yuborilmoqda...**")
            try:
                from services.bot_service import send_or_update_database_backup
                ok, err = await send_or_update_database_backup()
                if ok:
                    await event.edit(
                        "✅ **coddy_memory.db zaxira nusxasi botingizga (@coddyassistanstbot) yuborildi!**\n\n"
                        "Oldingi barcha eski nusxalar o'chirilib, faqat eng yangi to'liq baza saqlandi."
                    )
                else:
                    await event.edit(f"⚠️ Zaxira yuborishda xatolik: {err}")
            except Exception as e:
                logger.error("Backup yuborishda xatolik: %s", e)
                await event.edit(f"⚠️ Backup faylni yuborishda xatolik: {e}")
            return

        # -----------------------------------------------------------
        # Mavzu Tushuntirish (Topic Explainer)
        # -----------------------------------------------------------
        is_explain = False
        topic_arg = ""
        for kw in ["ai tushuntir", "tushuntir", f"{prefix}tushuntir"]:
            if lower_text.startswith(kw):
                is_explain = True
                topic_arg = raw_text[len(kw):].strip()
                break

        if is_explain:
            if not topic_arg:
                await event.edit(
                    "ℹ️ **Mavzu tushuntirish qo'llanmasi:**\n"
                    "Foydalanish: `tushuntir <mavzu_nomi>`\n\n"
                    "Misollar:\n"
                    "• `tushuntir python oop vorislik`\n"
                    "• `tushuntir recursion nima`\n"
                    "• `tushuntir decorators`\n"
                    "• `tushuntir fastAPI routers`"
                )
                return

            await event.edit(f"📚 **\"{topic_arg}\" mavzusi bo'yicha dars tayyorlanmoqda...**\n_Hayotiy analogiya, kod va amaliy mashq tuzilmoqda..._")
            explanation = await ai_service.explain_topic(topic_arg)
            await event.edit(explanation)
            return

        # -----------------------------------------------------------
        # AI Suhbat / Chat Co-Pilot (ai <savol>, coddy <savol>, .ai <savol>)
        # -----------------------------------------------------------
        is_ai_cmd = False
        ai_prompt = ""
        for trigger in (f"{prefix}ai", "ai", "coddy"):
            if lower_text == trigger:
                is_ai_cmd = True
                ai_prompt = ""
                break
            elif lower_text.startswith(f"{trigger} "):
                is_ai_cmd = True
                ai_prompt = raw_text[len(trigger) :].strip()
                break

        if is_ai_cmd:
            if ai_prompt.lower() in ("on", "1", "start", "enable"):
                config.auto_reply_enabled = True
                await event.edit("🤖 **Avto-javob rejimi faollashtirildi!**\nKelgan shaxsiy xabarlarga AI avtomatik javob beradi.")
                return

            if ai_prompt.lower() in ("off", "0", "stop", "disable"):
                config.auto_reply_enabled = False
                await event.edit("⏸ **Avto-javob rejimi to'xtatildi.**\nXabarlar faqat qo'lda boshqariladi.")
                return

            reply_text = None
            image_bytes = None

            if event.is_reply:
                reply_message = await event.get_reply_message()
                if reply_message:
                    if reply_message.text:
                        reply_text = reply_message.text
                    if reply_message.photo or (
                        reply_message.document
                        and reply_message.file
                        and getattr(reply_message.file, "mime_type", "").startswith("image/")
                    ):
                        image_bytes = await reply_message.download_media(bytes)
            elif event.message.photo:
                image_bytes = await event.message.download_media(bytes)

            prompt = ai_prompt
            if not prompt and not reply_text and not image_bytes:
                await event.edit(f"ℹ️ **Foydalanish:** `ai <savolingiz>` yoki biror rasm/xabarga reply qilib `ai` deb yozing.")
                return

            await event.edit("⏳ **AI javob tayyorlamoqda...**")

            user_input = prompt if prompt else "Ushbu rasm/skrinshotdagi vazifa yoki xatolikni tahlil qilib, to'liq va aniq yechim ber."
            try:
                answer = await asyncio.wait_for(
                    ai_service.generate_reply(
                        chat_id=event.chat_id,
                        user_message=user_input,
                        reply_to_context=reply_text,
                        image_bytes=image_bytes,
                    ),
                    timeout=35.0,
                )
            except asyncio.TimeoutError:
                await event.edit("⚠️ **Kechirasiz, AI javob berishda vaqt tugadi (timeout 35s). Iltimos, qaytadan urinib ko'ring.**")
                return
            except Exception as e:
                logger.error("AI buyrug'ida xatolik: %s", e)
                await event.edit("⚠️ **AI javob berishda kutilmagan xatolik yuz berdi.**")
                return

            # Telegram xabar uzunligi chegarasi (4096 belgi)
            try:
                if len(answer) > 4000:
                    await event.edit(answer[:4000])
                    await client.send_message(event.chat_id, answer[4000:])
                else:
                    await event.edit(answer)
            except Exception as e:
                logger.error("Xabarni chiqarishda xatolik: %s", e)
                await event.reply(answer)
            return

        if not raw_text.startswith(prefix):
            return

        command_body = raw_text[len(prefix) :].strip()
        parts = command_body.split(maxsplit=1)
        if not parts:
            return

        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # -----------------------------------------------------------
        # 2. .status - Bot va tizim holati
        # -----------------------------------------------------------
        if cmd == "status":
            auto_status = "🟢 Yoqilgan" if config.auto_reply_enabled else "🔴 O'chirilgan"
            group_status = "🟢 Yoqilgan" if config.group_reply_enabled else "🔴 O'chirilgan"
            active_chats = memory_service.total_active_chats()
            active_model = f"Groq ({config.groq_model})" if (config.groq_api_keys or config.groq_api_key) else f"Gemini ({config.gemini_model})"
            status_text = (
                "📊 **coddyHelper Tizim Holati**\n\n"
                f"- **Shaxsiy xabarlar (Lichka):** {auto_status}\n"
                f"- **Guruhlarda javob berish:** {group_status}\n"
                f"- **AI Modeli:** `{active_model}`\n"
                f"- **Kutish vaqti:** {config.mentor_wait_seconds} soniya\n"
                f"- **Xotiradagi faol chatlar:** {active_chats} ta\n"
                f"- **Buyruqlar prefiksi:** `{config.command_prefix}`\n"
                f"- **Xotira chegarasi:** {config.memory_limit} ta xabar"
            )
            await event.edit(status_text)
            return

        # -----------------------------------------------------------
        # 3. .clear - Ushbu chat xotirasini tozalash
        # -----------------------------------------------------------
        if cmd == "clear":
            cleared = memory_service.clear(event.chat_id)
            if cleared:
                await event.edit("🧹 **Ushbu chat uchun suhbat tarixi tozalandi.**")
            else:
                await event.edit("ℹ️ Bu chat uchun xotirada saqlangan ma'lumot yo'q.")
            return

        # -----------------------------------------------------------
        # 4. .help - Yordam menyusi
        # -----------------------------------------------------------
        if cmd == "help":
            help_text = (
                "🤖 **coddyHelper AI Yordamchi — Buyruqlar:**\n\n"
                "**Boshqaruv (Admin & Mini App):**\n"
                "- `panel` / `app` — Telegram Mini App (Admin Panel) ochish\n"
                "- `ai stop` / `ai start` — AI avto-javobini to'liq to'xtatish / yoqish\n"
                "- `guruh start` / `guruh stop` — Guruhlarga javob berishni yoqish / to'xtatish\n\n"
                "**Aqlli Eslatmalar:**\n"
                "- `ai eslatma <vaqt va vazifa>` — Eslatma o'rnatish\n"
                "- `eslatmalar` — Barcha faol eslatmalar\n"
                "- `ai eslatma bekor <ID>` — Eslatmani bekor qilish\n\n"
                "**GitHub Code Review:**\n"
                f"- `{prefix}review <link>` yoki reply qilib `review` — Repozitoriy tahlili\n\n"
                "**Qo'shimcha komandalar:**\n"
                f"- `{prefix}ai <matn>` — Tezkor AI javobini olish\n"
                f"- `reply + {prefix}ai` — Xabarni tahlil qilish yoki unga javob yozish\n"
                "- `report` / `ai report` — Mentor haftalik analitikasi\n"
                f"- `{prefix}status` — Tizim va xotira holatini ko'rish\n"
                f"- `{prefix}clear` — Joriy chatdagi suhbat tarixini o'chirish\n"
                f"- `{prefix}help` — Ushbu yordam oynasini ko'rsatish"
            )
            await event.edit(help_text)
            return

    # -----------------------------------------------------------
    # 5. Guruhdan (Vazifalar) kelgan panel/app buyruqlari
    # -----------------------------------------------------------
    @client.on(events.NewMessage(incoming=True, pattern=r"(?i)^([./])?(panel|app|admin|webapp|button|tugma)($|\s)"))
    async def handle_incoming_panel_command(event: events.NewMessage.Event):
        from config import is_escalation_chat
        if not (is_escalation_chat(event.chat_id) or event.is_private):
            return

        sender_id = event.sender_id or 0
        if sender_id != config.mentor_user_id and sender_id != 8105823872:
            await event.reply("🚫 **Kechirasiz, ushbu buyruq va Admin Panel faqat mentor (@mentor_cc) uchun ochiq.**")
            return

        from web_app import generate_admin_token
        token = generate_admin_token(user_id=sender_id)
        app_url = f"{config.web_app_url}/app?token={token}"

        try:
            await client.send_message(
                "me",
                "🎛 **coddyHelper — Admin Panel Xavfsiz Havolasi**\n\n"
                f"Guruhdan ({event.chat_id}) chaqirilgan boshqaruv paneli:\n"
                f"👉 **[Admin Panelni Ochish (Mini App)]({app_url})**\n\n"
                "🛡 *Faqat siz (@mentor_cc) uchun xavfsiz token.*"
            )
        except Exception:
            pass

        # Agar Telegram Bot ulangan bo'lsa, guruhga haqiqiy tugmali xabar chiqarib, pin qilamiz
        if config.bot_token and not event.is_private:
            try:
                from services.bot_service import post_group_panel_button
                ok, _ = await post_group_panel_button(event.chat_id)
                if ok:
                    return
            except Exception as b_err:
                logger.warning("Incoming handlerda bot tugmasi chiqarishda xatolik: %s", b_err)

        await event.reply(
            "🔐 **coddyHelper Admin Panel**\n\n"
            "Boshqaruv paneli havolasi shaxsiy xabarlaringizga ([Saved Messages](tg://user?id=8105823872)) yuborildi!\n"
            f"👉 To'g'ridan-to'g'ri ochish: [Boshqaruv Paneli]({app_url})\n\n"
            "⚠️ *Eslatma: Faqat @mentor_cc boshqarishi mumkin.*"
        )

