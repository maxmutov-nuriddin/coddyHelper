"""
Foydalanuvchi buyruqlari (Userbot komandalari)
"""

import asyncio
import logging
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from config import config
from services.ai_service import ai_service
from services.memory_service import memory_service

logger = logging.getLogger(__name__)


async def handle_mentor_ai_task(
    client: TelegramClient,
    event: events.NewMessage.Event,
    raw_text: str,
    is_outgoing: bool = True,
) -> bool:
    """
    Mentorni o'zi chatlarda, guruhlarda yoki shaxsiyda agentga 'ai <vazifa>' deb murojaat qilganda
    vazifani tushunib, bajaradi.
    MUHIM: Bunda AI modeli va tokenlari MENTORNING O'ZINIKIDAN (Miya 2: VIP Klaster, GROQ_VIP_KEYS, 120B model)
    ketadi va barcha pedagogik cheklovlar (Socratic refusals) o'chiriladi.
    """
    ai_match = re.match(r"^(?:[./!]?ai|coddy)(?:[:,\s\n]+|$)", raw_text, re.I)
    if not ai_match:
        return False

    ai_prompt = raw_text[ai_match.end() :].strip()

    if ai_prompt.lower() in ("on", "1", "start", "enable"):
        config.auto_reply_enabled = True
        msg = "🤖 **Avto-javob rejimi faollashtirildi!**\nKelgan shaxsiy xabarlarga AI avtomatik javob beradi."
        if is_outgoing:
            try:
                await event.edit(msg)
            except Exception:
                await event.reply(msg)
        else:
            await event.reply(msg)
        return True

    if ai_prompt.lower() in ("off", "0", "stop", "disable"):
        config.auto_reply_enabled = False
        msg = "⏸ **Avto-javob rejimi to'xtatildi.**\nXabarlar faqat qo'lda boshqariladi."
        if is_outgoing:
            try:
                await event.edit(msg)
            except Exception:
                await event.reply(msg)
        else:
            await event.reply(msg)
        return True

    reply_text = None
    image_bytes = None
    file_name = None
    file_text = None

    if event.is_reply:
        reply_message = await event.get_reply_message()
        if reply_message:
            if reply_message.text:
                reply_text = reply_message.text

            # Rasm / Skrinshot bormi?
            r_doc_name = getattr(reply_message.file, "name", "") or ""
            r_doc_ext = (Path(r_doc_name).suffix.lower() if r_doc_name else "") or (
                getattr(reply_message.file, "ext", "").lower() if reply_message.file else ""
            )
            r_mime = (getattr(reply_message.file, "mime_type", "") or "").lower()
            is_img = reply_message.photo or r_mime.startswith("image/") or r_doc_ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".heic"}
            if is_img:
                try:
                    image_bytes = await reply_message.download_media(bytes)
                except Exception as img_err:
                    logger.warning("Reply rasmni yuklashda xatolik: %s", img_err)

            # Hujjat yoki kod bormi? (.py, .ipynb, .docx, .pdf, .txt, .zip...)
            if reply_message.document and not is_img:
                try:
                    f_bytes = await reply_message.download_media(bytes)
                    if f_bytes:
                        if r_doc_ext == ".ipynb":
                            import json
                            nb = json.loads(f_bytes.decode("utf-8", errors="ignore"))
                            cells_text = [
                                f"# [{c.get('cell_type')}]:\n{''.join(c.get('source', []))}"
                                for c in nb.get("cells", [])
                                if "".join(c.get("source", [])).strip()
                            ]
                            file_text = "\n\n".join(cells_text)
                            file_name = r_doc_name or "notebook.ipynb"
                        elif r_doc_ext == ".docx":
                            import zipfile, io, xml.etree.ElementTree as ET
                            with zipfile.ZipFile(io.BytesIO(f_bytes)) as z:
                                tree = ET.fromstring(z.read("word/document.xml"))
                                texts = [n.text for n in tree.iter() if n.tag.endswith("t") and n.text]
                                file_text = "\n".join(texts)
                                file_name = r_doc_name or "document.docx"
                        elif r_doc_ext == ".pdf":
                            import io
                            from pypdf import PdfReader
                            reader = PdfReader(io.BytesIO(f_bytes))
                            file_text = "\n".join([p.extract_text() or "" for p in reader.pages[:10]])
                            file_name = r_doc_name or "document.pdf"
                        else:
                            file_text = f_bytes.decode("utf-8", errors="ignore")
                            file_name = r_doc_name or f"file{r_doc_ext}"
                except Exception as f_err:
                    logger.warning("Reply faylni yuklashda xatolik: %s", f_err)

    # Agar mentor o'z xabariga rasm ilova qilgan bo'lsa
    if event.message.photo and not image_bytes:
        try:
            image_bytes = await event.message.download_media(bytes)
        except Exception as e:
            logger.warning("Xabar rasmini yuklashda xatolik: %s", e)

    # Agar mentor o'z xabariga fayl yoki notebook ilova qilgan bo'lsa
    if event.message.document and not image_bytes and not file_text:
        try:
            m_doc_name = getattr(event.message.file, "name", "") or ""
            m_doc_ext = (Path(m_doc_name).suffix.lower() if m_doc_name else "") or (
                getattr(event.message.file, "ext", "").lower() if event.message.file else ""
            )
            m_mime = (getattr(event.message.file, "mime_type", "") or "").lower()
            if not (m_mime.startswith("image/") or m_doc_ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".heic"}):
                f_bytes = await event.message.download_media(bytes)
                if f_bytes:
                    if m_doc_ext == ".ipynb":
                        import json
                        nb = json.loads(f_bytes.decode("utf-8", errors="ignore"))
                        cells_text = [
                            f"# [{c.get('cell_type')}]:\n{''.join(c.get('source', []))}"
                            for c in nb.get("cells", [])
                            if "".join(c.get("source", [])).strip()
                        ]
                        file_text = "\n\n".join(cells_text)
                        file_name = m_doc_name or "notebook.ipynb"
                    elif m_doc_ext == ".docx":
                        import zipfile, io, xml.etree.ElementTree as ET
                        with zipfile.ZipFile(io.BytesIO(f_bytes)) as z:
                            tree = ET.fromstring(z.read("word/document.xml"))
                            texts = [n.text for n in tree.iter() if n.tag.endswith("t") and n.text]
                            file_text = "\n".join(texts)
                            file_name = m_doc_name or "document.docx"
                    elif m_doc_ext == ".pdf":
                        import io
                        from pypdf import PdfReader
                        reader = PdfReader(io.BytesIO(f_bytes))
                        file_text = "\n".join([p.extract_text() or "" for p in reader.pages[:10]])
                        file_name = m_doc_name or "document.pdf"
                    else:
                        file_text = f_bytes.decode("utf-8", errors="ignore")
                        file_name = m_doc_name or f"file{m_doc_ext}"
        except Exception as f_err:
            logger.warning("Mentor xabaridagi faylni yuklashda xatolik: %s", f_err)

    prompt_clean = (ai_prompt or "").strip()
    lower_p = prompt_clean.lower()
    generic_triggers = {
        "", "javob", "javob ber", "javobini ayt", "javob berchi", "javob yoz",
        "yech", "yechib ber", "tushuntir", "tushuntirib ber", "reply", "answer", "help", "yordam", "tekshir", "tekshirib ber"
    }
    if not prompt_clean and not reply_text and not image_bytes and not file_text:
        help_msg = "ℹ️ **Foydalanish:** `ai <vazifangiz>` yoki biror rasm/kod/xabarga reply qilib `ai` deb yozing."
        if is_outgoing:
            try:
                await event.edit(help_msg)
            except Exception:
                await event.reply(help_msg)
        else:
            await event.reply(help_msg)
        return True

    status_text = "⏳ **AI vazifani tahlil qilmoqda...**"
    status_msg = None
    if is_outgoing:
        try:
            await event.edit(status_text)
        except Exception:
            status_msg = await event.reply(status_text)
    else:
        status_msg = await event.reply(status_text)

    if not prompt_clean or lower_p in generic_triggers:
        if reply_text or image_bytes or file_text:
            user_input = (
                "Ushbu o'quvchining yuborgan xabari, kodi, vazifasi yoki xatoligini to'liq tahlil qilib, "
                "unga to'g'ridan-to'g'ri tushunarli, aniq va professional yechim va yo'nalish ber."
            )
        else:
            user_input = "Savolga to'liq, aniq va professional yechim ber."
    else:
        user_input = prompt_clean

    mentor_user_id = config.mentor_user_id or 8105823872
    try:
        answer = await asyncio.wait_for(
            ai_service.generate_reply(
                chat_id=mentor_user_id,
                user_message=user_input,
                reply_to_context=reply_text,
                image_bytes=image_bytes,
                file_name=file_name,
                file_text=file_text,
                is_admin_mode=True,  # Mentorning shaxsiy VIP klasteri (openai/gpt-oss-120b, 0 cheklov)
                user_id=mentor_user_id,
            ),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        logger.warning("AI buyrug'ida timeout (40s) yuz berdi [chat_id: %s]", event.chat_id)
        err_to = "⚠️ **Kechirasiz, AI javob berishda vaqt tugadi (40s). Iltimos, qaytadan urinib ko'ring.**"
        if status_msg:
            try:
                await status_msg.edit(err_to)
            except Exception:
                pass
        elif is_outgoing:
            try:
                await event.edit(err_to)
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error("AI buyrug'ida xatolik: %s", e)
        err_gen = "⚠️ **AI javob berishda kutilmagan xatolik yuz berdi.**"
        if status_msg:
            try:
                await status_msg.edit(err_gen)
            except Exception:
                pass
        elif is_outgoing:
            try:
                await event.edit(err_gen)
            except Exception:
                pass
        return True

    ans_str = str(answer or "").strip()
    if not ans_str:
        ans_str = "⚠️ AI dan javob olinmadi. Iltimos, so'rovni qayta yuboring."

    from handlers.auto_reply import BOT_SENT_MESSAGE_IDS
    try:
        target_to_edit = status_msg if status_msg else (event if is_outgoing else None)
        if len(ans_str) > 4000:
            if target_to_edit:
                await target_to_edit.edit(ans_str[:4000])
                sent_more = await client.send_message(event.chat_id, ans_str[4000:], reply_to=event.message.id)
                if sent_more:
                    BOT_SENT_MESSAGE_IDS.add(sent_more.id)
            else:
                sent1 = await event.reply(ans_str[:4000])
                if sent1:
                    BOT_SENT_MESSAGE_IDS.add(sent1.id)
                sent_more = await client.send_message(event.chat_id, ans_str[4000:], reply_to=event.message.id)
                if sent_more:
                    BOT_SENT_MESSAGE_IDS.add(sent_more.id)
        else:
            if target_to_edit:
                await target_to_edit.edit(ans_str)
            else:
                sent = await event.reply(ans_str)
                if sent:
                    BOT_SENT_MESSAGE_IDS.add(sent.id)
    except Exception as e:
        logger.error("Xabarni chiqarishda xatolik: %s", e)
        try:
            sent = await event.reply(ans_str)
            if sent:
                BOT_SENT_MESSAGE_IDS.add(sent.id)
        except Exception as e2:
            logger.error("Xabarni reply qilishda ham xatolik: %s", e2)

    return True


def register_command_handlers(client: TelegramClient) -> None:
    prefix = config.command_prefix

    @client.on(events.NewMessage(outgoing=True))
    async def handle_user_command(event: events.NewMessage.Event):
        raw_text = (event.raw_text or "").strip()

        # Agar mentor ovozli xabar orqali buyruq bergan bo'lsa
        has_voice = bool(
            getattr(event.message, "voice", False)
            or (
                event.message.document
                and event.message.file
                and getattr(event.message.file, "mime_type", "").startswith("audio/")
            )
        )
        if not raw_text and has_voice:
            try:
                audio_bytes = await event.message.download_media(bytes)
                if audio_bytes:
                    transcribed = await ai_service.transcribe_audio(audio_bytes)
                    if transcribed:
                        raw_text = transcribed.strip()
            except Exception as v_err:
                logger.debug("Mentor ovozli xabarini STT qilishda ogohlantirish: %s", v_err)

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
                memory_service.ignore_user(target_id, target_uname, reason="Mentor buyrug'i (ai ignore)")
                await event.edit(
                    f"🔇 **Foydalanuvchi `{target_id}` {target_uname} ignore qilindi (Telegramda bloklanmadi)!**\n"
                    "• AI endi bu foydalanuvchiga javob bermaydi.\n"
                    "• Telegram hisobingizda bloklanmadi (shaxsiy yozishma ochiq qoladi).\n\n"
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
                memory_service.clear_user_quota(target_id)
                try:
                    from services.telegram_agent_service import unblock_telegram_user
                    await unblock_telegram_user(client, target_id)
                except Exception:
                    pass
                if res:
                    await event.edit(f"✅ **Foydalanuvchi `{target_id}` blokdan chiqarildi!**\n• Telegram qora ro'yxatidan ham chiqarildi.\n• AI yana uning savollariga javob beradi.")
                else:
                    await event.edit(f"✅ **Foydalanuvchi `{target_id}` Telegram blokidan chiqarildi.**")
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
        # 0-Token Veb-Inspektor va Skrinshot (.site / .audit / .web)
        # -----------------------------------------------------------
        if (
            lower_text.startswith(f"{prefix}site")
            or lower_text.startswith(f"{prefix}audit")
            or lower_text.startswith(f"{prefix}web")
            or lower_text.startswith(".site")
            or lower_text.startswith(".audit")
            or lower_text.startswith(".web")
        ):
            parts = text.split(maxsplit=1)
            target_url = None
            if len(parts) > 1:
                target_url = parts[1].strip()
            elif event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.text:
                    m = re.search(r"https?://[^\s]+", reply_msg.text)
                    if m:
                        target_url = m.group(0)

            if not target_url or not target_url.startswith("http"):
                await event.edit(
                    "ℹ️ **0-Token Veb-Inspektor ishlatish:**\n"
                    f"• `{prefix}site https://my-portfolio.vercel.app`\n"
                    "• Yoki sayt havolasi bor xabarga reply qilib `.site` deb yozing."
                )
                return

            await event.edit(f"🌐 **Sayt tekshirilmoqda va skrinshot olinmoqda (0 token):**\n`{target_url}`")
            from services.web_inspector_service import audit_website, format_audit_report, get_website_screenshot
            audit_data = await audit_website(target_url)
            report_text = format_audit_report(audit_data, target_url)
            ss_bytes = await get_website_screenshot(target_url)
            if ss_bytes:
                await event.delete()
                await event.respond(report_text, file=ss_bytes)
            else:
                await event.edit(report_text)
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
        # AI Suhbat / Chat Co-Pilot (ai <savol>, coddy <savol>, .ai <savol>, ai: <savol>)
        # -----------------------------------------------------------
        ai_match = re.match(r"^(?:[./!]?ai|coddy)(?:[:,\s\n]+|$)", raw_text, re.I)
        if ai_match:
            handled = await handle_mentor_ai_task(client, event, raw_text=raw_text, is_outgoing=True)
            if handled:
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
        # 3.1 .miya3 / .gemini / .zaxira - Miya 3 (Temir Zaxira Gemini) ni yoqish / o'chirish
        # -----------------------------------------------------------
        if cmd in ("miya3", "gemini", "zaxira"):
            clean_arg = (arg or "").lower().strip()
            if clean_arg in ("off", "0", "stop", "ochir", "o'chir", "disable", "no"):
                memory_service.set_setting("gemini_backup_enabled", "false")
                await event.edit("🔴 **Miya 3: Temir Zaxira (Google Gemini) o'chirildi!**\nEndi tizim faqat Groq klasteridan foydalanadi, Gemini zaxiraga umuman ulanmaydi.")
                return
            elif clean_arg in ("on", "1", "start", "yoq", "faol", "enable", "yes"):
                memory_service.set_setting("gemini_backup_enabled", "true")
                await event.edit("🟢 **Miya 3: Temir Zaxira (Google Gemini) yoqildi!**\nGroq limitga uchraganda Gemini favqulodda zaxira sifatida xizmat ko'rsatadi.")
                return
            else:
                curr_status = memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true"
                status_str = "🟢 Yoqilgan (Faol)" if curr_status else "🔴 O'chirilgan (Nofaol)"
                await event.edit(
                    f"ℹ️ **Miya 3 (Temir Zaxira - Google Gemini) holati:** {status_str}\n\n"
                    f"O'zgartirish uchun:\n"
                    f"• `{prefix}miya3 off` — Gemini zaxirasini o'chirish\n"
                    f"• `{prefix}miya3 on` — Gemini zaxirasini yoqish"
                )
                return

        # -----------------------------------------------------------
        # 3.2 .miya4 / .auto - Miya 4 (Avtonom Fikrlash Dvigateli 24/7) boshqaruvi
        # -----------------------------------------------------------
        if cmd in ("miya4", "auto", "avtonom"):
            from services.autonomous_brain_service import autonomous_brain_service
            clean_arg = (arg or "").lower().strip()
            if clean_arg in ("off", "0", "stop", "ochir", "o'chir", "disable", "no"):
                autonomous_brain_service.set_enabled(False)
                await event.edit("🔴 **Miya 4: Avtonom Fikrlash Dvigateli to'xtatildi (Pauza).**")
                return
            elif clean_arg in ("on", "1", "start", "yoq", "faol", "enable", "yes"):
                autonomous_brain_service.set_enabled(True)
                await event.edit("🟢 **Miya 4: Avtonom Fikrlash Dvigateli yoqildi!** (24/7 orqa fonda o'rganish faol).")
                return
            elif clean_arg in ("ultra", "1", "1m", "1daq", "1daqiqa", "chaqqon"):
                autonomous_brain_service.set_mode("ultra")
                await event.edit("⚡⚡ **Miya 4 rejimi: ULTRA (Har 1 daqiqada 1 sikl) ga o'tkazildi!**")
                return
            elif clean_arg in ("tezkor", "2.5", "2.5m", "2.5daq", "fast"):
                autonomous_brain_service.set_mode("tezkor")
                await event.edit("⚡ **Miya 4 rejimi: TEZKOR (Har 2.5 daqiqada 1 sikl) ga o'tkazildi!**")
                return
            elif clean_arg in ("optimal", "5", "5m", "5daq", "standart"):
                autonomous_brain_service.set_mode("optimal")
                await event.edit("🌟 **Miya 4 rejimi: OPTIMAL (Har 5 daqiqada 1 sikl) ga o'tkazildi!**")
                return
            elif clean_arg in ("sokin", "10", "10m", "10daq", "slow"):
                autonomous_brain_service.set_mode("sokin")
                await event.edit("🐢 **Miya 4 rejimi: SOKIN (Har 10 daqiqada 1 sikl) ga o'tkazildi!**")
                return
            else:
                st = autonomous_brain_service.get_status()
                en_str = "🟢 Yoqilgan" if st.get("enabled") else "🔴 To'xtatilgan"
                mode_str = st.get("mode", "tezkor").upper()
                interval_str = f"{st.get('interval_seconds', 150) / 60:.1f}".rstrip('0').rstrip('.')
                next_est = st.get("next_run_estimated", "Noma'lum")
                cur_act = st.get("current_activity", "Kutilmoqda")
                await event.edit(
                    f"🧬 **Miya 4: Avtonom Fikrlash Dvigateli (24/7)**\n\n"
                    f"• **Holat:** {en_str}\n"
                    f"• **Tezlik rejimi:** `{mode_str}` ({interval_str} daqiqalik davr)\n"
                    f"• **Keyingi sikl:** `{next_est}`\n"
                    f"• **Joriy amal:** _{cur_act}_\n"
                    f"• **Baza:** {st.get('insights_generated', 0)} saboq, {st.get('answers_precomputed', 0)} kesh, {st.get('lexicon_learned', 0)} leksikon\n\n"
                    f"**Tezlikni o'zgartirish:**\n"
                    f"• `{prefix}miya4 1m` — Ultra tezkor (1 daqiqa)\n"
                    f"• `{prefix}miya4 2.5m` — Tezkor (2.5 daqiqa)\n"
                    f"• `{prefix}miya4 5m` — Optimal (5 daqiqa)\n"
                    f"• `{prefix}miya4 10m` — Sokin (10 daqiqa)\n"
                    f"• `{prefix}miya4 on / off` — Yoqish / To'xtatish"
                )
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
                "**JARVIS Ovoz va Brifing:**\n"
                f"- `{prefix}speak <matn>` — Mac karnayidan ovoz chiqarib gapirish\n"
                f"- `{prefix}briefing` — Kunlik reja va darslar ovozli brifingi\n"
                f"- `{prefix}voice` — Ovozli javoblarni yoqish/o'chirish\n\n"
                "**JARVIS Mac OS Boshqaruv Qo'llari:**\n"
                f"- `{prefix}open <dastur/sayt>` — Dastur yoki saytni Mac'da ochish\n"
                f"- `{prefix}vol <0-100|mute|max>` — Mac ovozini sozlash\n"
                f"- `{prefix}lock` — Mac ekranini qulflash\n"
                f"- `{prefix}sysinfo` — Mac batareyasi, CPU va holatini ko'rish\n"
                f"- `{prefix}shortcut <nom>` — Mac Shortcuts ssenariysini bajarish\n\n"
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
        # JARVIS: Mahalliy Mac Karnayidan Gapirish (.speak <matn>)
        # -----------------------------------------------------------
        is_speak_cmd = False
        speak_text = ""
        for kw in [f"{prefix}speak", "ai speak", "jarvis speak", f"{prefix}gapir"]:
            if lower_text.startswith(kw):
                is_speak_cmd = True
                speak_text = raw_text[len(kw):].strip()
                break

        if is_speak_cmd:
            if not speak_text:
                await event.edit(f"ℹ️ **Foydalanish:** `{prefix}speak <matn>`\nMasalan: `{prefix}speak Salom Ustoz, barcha tizimlar faol!`")
                return
            await event.edit(f"🎙 **JARVIS gapirmoqda...**\n`{speak_text[:120]}`")
            try:
                from services.speaker_service import speaker_service
                ok = await speaker_service.speak_text(speak_text, is_mentor=True)
                if ok:
                    await event.edit(f"🔊 **JARVIS muvaffaqiyatli gapirdi:**\n`{speak_text}`")
                else:
                    await event.edit("⚠️ **Audio ijrosida ogohlantirish (audio pleyer mavjud emas yoki xatolik).**")
            except Exception as spk_e:
                await event.edit(f"❌ **Xatolik:** {spk_e}")
            return

        # -----------------------------------------------------------
        # JARVIS: Tonggi / Kunlik Brifing (.briefing)
        # -----------------------------------------------------------
        is_briefing_cmd = False
        for kw in [f"{prefix}briefing", "ai briefing", "brifing", f"{prefix}brifing"]:
            if lower_text == kw or lower_text.startswith(kw + " "):
                is_briefing_cmd = True
                break

        if is_briefing_cmd:
            await event.edit("🌅 **JARVIS bugungi kunlik brifingni tayyorlamoqda...**")
            try:
                from services.briefing_service import briefing_service
                full_text, spoken_text = await briefing_service.generate_briefing()
                await event.edit(full_text)
                from services.speaker_service import speaker_service
                if speaker_service.is_available():
                    asyncio.create_task(speaker_service.speak_text(spoken_text, is_mentor=True))
                voice_reply_enabled = memory_service.get_setting("voice_reply_enabled", "true").lower() == "true"
                if voice_reply_enabled:
                    from services.tts_service import generate_voice_message
                    v_path = await generate_voice_message(spoken_text, is_mentor=True)
                    if v_path and v_path.exists():
                        await event.reply(file=str(v_path), voice_note=True, caption="🎙 **Jarvis Ovozli Brifingi**")
                        v_path.unlink(missing_ok=True)
            except Exception as br_e:
                logger.error("Briefing xatolik: %s", br_e)
            return

        # -----------------------------------------------------------
        # JARVIS: Ovozli javoblarni yoqish/o'chirish (.voice)
        # -----------------------------------------------------------
        if lower_text in [f"{prefix}voice", f"{prefix}ovoz", "ai voice", "voice toggle"]:
            curr = memory_service.get_setting("voice_reply_enabled", "true").lower() == "true"
            new_val = not curr
            memory_service.set_setting("voice_reply_enabled", "true" if new_val else "false")
            st_text = "🟢 **YOQILDI** (Ovozli xabarlarga audio javob beriladi)" if new_val else "🔴 **O'CHIRILDI** (Faqat matnli javob beriladi)"
            await event.edit(f"🎙 **JARVIS Ovozli Javoblar (Voice-to-Voice):** {st_text}")
            return

        # -----------------------------------------------------------
        # JARVIS: Mac OS Boshqaruv Qo'llari (2-Pog'ona)
        # -----------------------------------------------------------
        # .sysinfo / .mac - Tizim holati hisoboti
        if lower_text in [f"{prefix}sysinfo", f"{prefix}mac", "ai mac", "jarvis status", f"{prefix}pc"]:
            await event.edit("🔄 **Mac OS tizim holati tekshirilmoqda...**")
            from services.mac_control_service import mac_control_service
            s = await mac_control_service.get_system_status()
            batt_str = f"{s['battery_pct']}%" if s['battery_pct'] is not None else "Aniqlanmadi"
            batt_state = "⚡ Quvvatlanmoqda" if s['battery_state'] == "charging" else ("✅ To'liq" if s['battery_state'] == "full" else "🔋 Batareyada")
            vol_str = f"0% (Muted)" if s['muted'] else f"{s['volume']}%"
            msg = (
                "💻 **JARVIS — Mac OS Tizim Holati**\n\n"
                f"🔋 **Batareya:** `{batt_str}` ({batt_state})\n"
                f"⚙️ **CPU Yuklamasi:** `{s['cpu_pct']}%` ({s['cpu_cores']} yadroli)\n"
                f"💾 **Xotira (RAM):** `{s['ram_total_gb']} GB`\n"
                f"🔊 **Karnay Ovozi:** `{vol_str}`\n"
                f"🖥 **OS Platformasi:** `{s['platform']}`"
            )
            await event.edit(msg)
            return

        # .vol <0-100|mute|max> - Ovozni sozlash
        if lower_text.startswith(f"{prefix}vol ") or lower_text.startswith("ai vol "):
            parts = text.split(maxsplit=1)
            val = parts[1].strip() if len(parts) > 1 else "50"
            from services.mac_control_service import mac_control_service
            ok, msg = await mac_control_service.set_volume(val)
            await event.edit(f"🔊 **Mac Ovoz Boshqaruvi:**\n{msg}")
            return

        # .lock - Mac ekranini qulflash
        if lower_text in [f"{prefix}lock", "ai lock", "mac lock", f"{prefix}qulf"]:
            await event.edit("🔒 **Mac ekrani qulflanmoqda...**")
            from services.mac_control_service import mac_control_service
            ok, msg = await mac_control_service.lock_screen()
            await event.edit(msg)
            return

        # .open <dastur/sayt> - Dastur yoki havola ochish
        if lower_text.startswith(f"{prefix}open ") or lower_text.startswith("ai open "):
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            if not target:
                await event.edit("⚠️ **Ochish uchun dastur nomi yoki havolani kiriting:** `.open Chrome`")
                return
            from services.mac_control_service import mac_control_service
            ok, msg = await mac_control_service.open_app_or_url(target)
            await event.edit(msg)
            return

        # .shortcut <nomi> - Apple Shortcuts buyrug'ini bajarish
        if lower_text.startswith(f"{prefix}shortcut ") or lower_text.startswith("ai shortcut "):
            parts = text.split(maxsplit=1)
            sc_name = parts[1].strip() if len(parts) > 1 else ""
            if not sc_name:
                await event.edit("⚠️ **Shortcut nomini kiriting:** `.shortcut <nomi>`")
                return
            await event.edit(f"⚡ **Mac Shortcuts:** `{sc_name}` bajarilmoqda...")
            from services.mac_control_service import mac_control_service
            ok, msg = await mac_control_service.run_shortcut(sc_name)
            await event.edit(msg)
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

