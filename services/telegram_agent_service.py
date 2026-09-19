"""
services/telegram_agent_service.py
Telegram Action Agent xizmati:
Telethon mijozi orqali xabarlarni qidirish, o'quvchi va ota-onalar kontaktlarini topish,
hamda to'g'ridan-to'g'ri xabar yuborish amallarini bajaradi.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from services.memory_service import memory_service

logger = logging.getLogger(__name__)


def _get_tashkent_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    try:
        tashkent_tz = ZoneInfo("Asia/Tashkent")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tashkent_tz).strftime("%d.%m.%Y %H:%M")
        return dt.astimezone(tashkent_tz).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(dt)[:16]


def clean_btn_text(t: str) -> str:
    """Tugma matnidan solishtirish uchun emojilar va belgilarni tozalaydi."""
    return re.sub(r'[^\w\s]', '', t or "").strip().lower()


def button_matches(btn_text: str, query: str) -> bool:
    """Tugma matni qidirilayotgan so'rovga mos kelishini aniqlaydi."""
    b_raw = (btn_text or "").strip().lower()
    q_raw = (query or "").strip().lower()
    if not b_raw or not q_raw:
        return False
    if q_raw in b_raw or b_raw in q_raw:
        return True
    b_clean = clean_btn_text(btn_text)
    q_clean = clean_btn_text(query)
    if b_clean and q_clean and (q_clean in b_clean or b_clean in q_clean):
        return True
    return False


def extract_buttons_from_message(msg) -> tuple[list[list[str]], list[str]]:
    """
    Xabardan barcha inline va klaviatura tugmalarini matritsa va tekis ro'yxat ko'rinishida ajratib oladi.
    Agent hech qanday tugmani ko'zdan qochirmasligi uchun to'liq tahlil qiladi.
    """
    matrix: list[list[str]] = []
    flat: list[str] = []
    if not msg:
        return matrix, flat

    # 1. Telethon custom.Message.buttons (Inline va ReplyKeyboardMarkup tugmalari)
    if getattr(msg, "buttons", None):
        for row in msg.buttons:
            row_txts = []
            for btn in row:
                b_txt = (getattr(btn, "text", "") or "").strip()
                if b_txt:
                    row_txts.append(b_txt)
                    flat.append(b_txt)
            if row_txts:
                matrix.append(row_txts)
    # 2. Telethon reply_markup fallback (TL ReplyInlineMarkup yoki ReplyKeyboardMarkup)
    elif getattr(msg, "reply_markup", None):
        markup = msg.reply_markup
        for row in getattr(markup, "rows", []):
            row_txts = []
            for btn in getattr(row, "buttons", []):
                b_txt = (getattr(btn, "text", "") or "").strip()
                if b_txt:
                    row_txts.append(b_txt)
                    flat.append(b_txt)
            if row_txts:
                matrix.append(row_txts)

    return matrix, flat


def format_buttons_for_display(matrix: list[list[str]]) -> str:
    """Tugmalar matritsasini inson va AI o'qiy oladigan ko'rgazmali ko'rinishga keltiradi."""
    if not matrix:
        return ""
    lines = ["🔘 **Mavjud inline tugmalar (Tugmalar paneli):**"]
    for row in matrix:
        row_str = " | ".join(f"[{b}]" for b in row if b.strip())
        if row_str:
            lines.append(f"   {row_str}")
    return "\n".join(lines)


async def search_telegram_messages(client, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Telegram barcha dialoglari bo'ylab xabarlarni global qidiradi.
    Qayerda (qaysi guruh/chatda), kim tomonidan, qachon yozilganini va tugmalarini qaytaradi.
    """
    if not client:
        return [{"error": "Telegram mijoz ulanmagan"}]

    q = (query or "").strip()
    if not q:
        return []

    results = []
    try:
        # Global search across all chats
        messages = await client.get_messages(None, search=q, limit=limit)
        for msg in messages:
            chat = msg.chat
            chat_title = getattr(chat, "title", None) or getattr(chat, "first_name", "Shaxsiy chat")
            chat_username = getattr(chat, "username", None)
            chat_id = msg.chat_id

            sender = msg.sender
            sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", "Noma'lum")
            if getattr(sender, "last_name", None):
                sender_name += f" {sender.last_name}"

            date_str = _get_tashkent_time(msg.date)
            text_snippet = (msg.message or msg.raw_text or "").strip().replace("\n", " ")
            if len(text_snippet) > 200:
                text_snippet = text_snippet[:197] + "..."

            link = None
            if chat_username:
                link = f"https://t.me/{chat_username}/{msg.id}"
            elif str(chat_id).startswith("-100"):
                clean_id = str(chat_id)[4:]
                link = f"https://t.me/c/{clean_id}/{msg.id}"

            b_matrix, b_flat = extract_buttons_from_message(msg)
            btn_str = format_buttons_for_display(b_matrix) if b_matrix else ""

            results.append({
                "chat_name": chat_title,
                "chat_username": f"@{chat_username}" if chat_username else None,
                "chat_id": chat_id,
                "sender_name": sender_name,
                "date": date_str,
                "snippet": text_snippet,
                "buttons": btn_str,
                "buttons_matrix": b_matrix,
                "link": link,
                "msg_id": msg.id,
            })
    except Exception as e:
        logger.error("Telegram xabarlarini qidirishda xatolik: %s", e)
        results.append({"error": str(e)})

    return results


async def search_chat_messages(client, chat_target: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Muayyan guruh, kanal yoki shaxsiy chat ichidan xabarlarni maqsadli qidiradi.
    Xabarlarga biriktirilgan tugmalarni ham to'liq ko'radi.
    """
    if not client:
        return [{"error": "Telegram mijoz ulanmagan"}]

    c_query = (chat_target or "").strip()
    q = (query or "").strip()
    if not q:
        return []

    try:
        target_chat = None
        if c_query.startswith("@") or re.match(r"^-?\d+$", c_query):
            try:
                target_chat = await client.get_entity(int(c_query) if re.match(r"^-?\d+$", c_query) else c_query)
            except Exception:
                pass

        if not target_chat:
            dialogs = await client.get_dialogs(limit=50)
            for d in dialogs:
                d_title = getattr(d, "title", "") or getattr(d, "name", "") or ""
                if c_query.lower() in d_title.lower() or d_title.lower() in c_query.lower():
                    target_chat = d.entity
                    break

        if not target_chat:
            return [{"error": f"'{c_query}' nomli guruh yoki chat topilmadi."}]

        chat_title = getattr(target_chat, "title", None) or getattr(target_chat, "first_name", "Chat")
        chat_username = getattr(target_chat, "username", None)
        chat_id = getattr(target_chat, "id", None)

        results = []
        messages = await client.get_messages(target_chat, search=q, limit=limit)
        for msg in messages:
            sender = msg.sender
            sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", "Noma'lum")
            if getattr(sender, "last_name", None):
                sender_name += f" {sender.last_name}"

            date_str = _get_tashkent_time(msg.date)
            text_snippet = (msg.message or msg.raw_text or "").strip().replace("\n", " ")
            if len(text_snippet) > 200:
                text_snippet = text_snippet[:197] + "..."

            link = None
            if chat_username:
                link = f"https://t.me/{chat_username}/{msg.id}"
            elif str(chat_id).startswith("-100"):
                clean_id = str(chat_id)[4:]
                link = f"https://t.me/c/{clean_id}/{msg.id}"

            b_matrix, b_flat = extract_buttons_from_message(msg)
            btn_str = format_buttons_for_display(b_matrix) if b_matrix else ""

            results.append({
                "chat_name": chat_title,
                "chat_username": f"@{chat_username}" if chat_username else None,
                "chat_id": chat_id,
                "sender_name": sender_name,
                "date": date_str,
                "snippet": text_snippet,
                "buttons": btn_str,
                "buttons_matrix": b_matrix,
                "link": link,
                "msg_id": msg.id,
            })
        return results
    except Exception as e:
        logger.error("Chat ichidan qidirishda xatolik: %s", e)
        return [{"error": str(e)}]


async def inspect_telegram_chat(client, chat_target: str, limit: int = 5) -> dict[str, Any]:
    """
    Muayyan chat yoki botning so'nggi xabarlarini, mavjud barcha inline tugmalarini,
    klaviaturani va hozirgi ekran holatini to'liq ko'rib chiqadi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijozi ulanmagan"}
    c_query = (chat_target or "").strip()
    if not c_query:
        return {"ok": False, "error": "Chat yoki bot nomi kiritilmadi"}

    try:
        target = None
        if c_query.startswith("@") or re.match(r"^-?\d+$", c_query):
            try:
                target = await client.get_entity(int(c_query) if re.match(r"^-?\d+$", c_query) else c_query)
            except Exception:
                pass
        if not target:
            dialogs = await client.get_dialogs(limit=50)
            for d in dialogs:
                d_title = getattr(d, "title", "") or getattr(d, "name", "") or ""
                if c_query.lower() in d_title.lower() or d_title.lower() in c_query.lower():
                    target = d.entity
                    break
        if not target:
            return {"ok": False, "error": f"'{c_query}' chat yoki bot topilmadi"}

        chat_title = getattr(target, "title", None) or getattr(target, "first_name", "Chat")
        chat_user = getattr(target, "username", None)
        messages = await client.get_messages(target, limit=limit)

        parsed_msgs = []
        active_buttons = []
        for m in messages:
            b_matrix, _ = extract_buttons_from_message(m)
            sender_name = "Siz" if m.out else (getattr(m.sender, "first_name", "Bot/Foydalanuvchi") if m.sender else "Noma'lum")
            text = (m.message or m.raw_text or "").strip()
            date_str = _get_tashkent_time(m.date)
            parsed_msgs.append({
                "id": m.id,
                "sender": sender_name,
                "out": m.out,
                "date": date_str,
                "text": text,
                "buttons_matrix": b_matrix,
                "buttons_str": format_buttons_for_display(b_matrix) if b_matrix else "",
            })
            if b_matrix and not active_buttons and not m.out:
                active_buttons = b_matrix

        return {
            "ok": True,
            "title": chat_title,
            "username": f"@{chat_user}" if chat_user else None,
            "messages": parsed_msgs,
            "active_buttons": active_buttons,
        }
    except Exception as e:
        logger.error("Chatni ko'rib chiqishda xatolik: %s", e)
        return {"ok": False, "error": str(e)}


async def click_chat_button(
    client,
    chat_target: str,
    button_query: str,
    message_id: int | None = None,
    wait_timeout: int = 12,
) -> dict[str, Any]:
    """
    Chat yoki botdagi ko'rsatilgan inline tugmani bosadi va natijaviy yangilangan ekranni oladi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijozi ulanmagan"}
    c_query = (chat_target or "").strip()
    b_query = (button_query or "").strip()
    if not c_query or not b_query:
        return {"ok": False, "error": "Chat va tugma nomi ko'rsatilishi shart"}

    try:
        target = None
        if c_query.startswith("@") or re.match(r"^-?\d+$", c_query):
            try:
                target = await client.get_entity(int(c_query) if re.match(r"^-?\d+$", c_query) else c_query)
            except Exception:
                pass
        if not target:
            dialogs = await client.get_dialogs(limit=50)
            for d in dialogs:
                d_title = getattr(d, "title", "") or getattr(d, "name", "") or ""
                if c_query.lower() in d_title.lower() or d_title.lower() in c_query.lower():
                    target = d.entity
                    break
        if not target:
            return {"ok": False, "error": f"'{c_query}' chat yoki bot topilmadi"}

        # Xabarlarni olish
        if message_id:
            try:
                single_msg = await client.get_messages(target, ids=int(message_id))
                msgs = [single_msg] if single_msg else []
            except Exception:
                msgs = await client.get_messages(target, limit=10)
        else:
            msgs = await client.get_messages(target, limit=10)

        # Tugmani qidirish
        found_btn = None
        found_msg = None
        for m in msgs:
            if not m or not getattr(m, "buttons", None):
                continue
            for row in m.buttons:
                for btn in row:
                    b_txt = (getattr(btn, "text", "") or "").strip()
                    if button_matches(b_txt, b_query):
                        found_btn = btn
                        found_msg = m
                        break
                if found_btn:
                    break
            if found_btn:
                break

        if not found_btn or not found_msg:
            all_available = []
            for m in msgs:
                if m and getattr(m, "buttons", None):
                    for row in m.buttons:
                        for btn in row:
                            b_t = (getattr(btn, "text", "") or "").strip()
                            if b_t:
                                all_available.append(b_t)
            avail_str = f"\n(Mavjud tugmalar: {', '.join(f'[{b}]' for b in all_available[:10])})" if all_available else "\n(Hech qanday tugma topilmadi)"
            return {"ok": False, "error": f"'{b_query}' nomli tugma topilmadi.{avail_str}"}

        clicked_name = getattr(found_btn, "text", b_query)
        old_text = (found_msg.message or found_msg.raw_text or "").strip()
        old_id = found_msg.id

        # Tugmani bosish
        try:
            await found_btn.click()
        except Exception as ce:
            logger.warning("found_btn.click() xatosi: %s, message.click urinilmoqda", ce)
            try:
                await found_msg.click(text=clicked_name)
            except Exception as ce2:
                return {"ok": False, "error": f"Tugmani bosishda xatolik: {ce2}"}

        # O'zgarishni kutish (bot xabarni edit qiladi yoki yangi xabar yuboradi)
        updated_msg = None
        start_wait = time.time()
        while time.time() - start_wait < wait_timeout:
            await asyncio.sleep(1.2)
            try:
                latest = await client.get_messages(target, limit=5)
                # 1. Yangi xabar kelganmi?
                for lm in latest:
                    if lm.id > old_id and not lm.out:
                        updated_msg = lm
                        break
                if updated_msg:
                    break
                # 2. Eski xabar edit qilinganmi?
                for lm in latest:
                    if lm.id == old_id and ((lm.message or "") != old_text or getattr(lm, "buttons", None) != getattr(found_msg, "buttons", None)):
                        updated_msg = lm
                        break
                if updated_msg:
                    break
            except Exception:
                pass

        if not updated_msg:
            cur = await client.get_messages(target, limit=1)
            updated_msg = cur[0] if cur else found_msg

        upd_matrix, upd_flat = extract_buttons_from_message(updated_msg)
        upd_text = (updated_msg.message or updated_msg.raw_text or "").strip()
        btn_str = format_buttons_for_display(upd_matrix) if upd_matrix else ""

        return {
            "ok": True,
            "clicked": clicked_name,
            "response": upd_text,
            "buttons_matrix": upd_matrix,
            "buttons_str": btn_str,
            "buttons": upd_flat,
            "msg_id": updated_msg.id,
        }
    except Exception as e:
        logger.error("click_chat_button da xatolik: %s", e)
        return {"ok": False, "error": str(e)}


async def navigate_tash3tm_bot(client, query: str) -> dict[str, Any]:
    """
    @tash3tm_bot (Toshkent jamoat transporti) bilan ko'p bosqichli avtonom muloqot:
    - Avtobus yo'nalishi (masalan: 8-avtobus, Sergeli hokimiyati) yoki bekat bo'yicha aniq ma'lumot oladi.
    - Inline tugmalarni (Маршруты, yo'nalish tomoni) bosqichma-bosqich bosib, to'liq hisobot olib keladi.
    """
    bot_tag = "@tash3tm_bot"
    q = (query or "").lower()

    # Avtobus raqami va yo'nalish tomonini aniqlash
    bus_num_m = re.search(r"\b(\d{1,3})\s*(?:-?\s*avtobus)?\b", q)
    bus_num = bus_num_m.group(1) if bus_num_m else None
    prefer_direction = "massiv" if any(w in q for w in ("massiv", "sergeli", "sergili", "hokim")) else None
    is_stop_search = any(w in q for w in ("astanovka", "ostanovka", "bekat", "stop"))

    try:
        try:
            bot_entity = await client.get_input_entity(bot_tag)
        except Exception:
            bot_entity = await client.get_entity(bot_tag)

        recent = await client.get_messages(bot_entity, limit=5)
        has_menu = False
        menu_msg = None
        for m in recent:
            if m and not m.out and getattr(m, "buttons", None):
                for row in m.buttons:
                    for btn in row:
                        b_txt_low = (getattr(btn, "text", "") or "").lower()
                        if "маршрут" in b_txt_low or "поиск" in b_txt_low:
                            has_menu = True
                            menu_msg = m
                            break
                if has_menu:
                    break

        if not has_menu:
            await client.send_message(bot_entity, "/start")
            await asyncio.sleep(1.5)
            recent = await client.get_messages(bot_entity, limit=3)
            for m in recent:
                if m and not m.out and getattr(m, "buttons", None):
                    menu_msg = m
                    has_menu = True
                    break

        history_steps = []

        # 1-variant: Agar bekat bo'yicha qidiruv so'ralgan bo'lsa ("astanovkasini topib")
        if is_stop_search and has_menu:
            c_res = await click_chat_button(client, bot_tag, "Поиск", wait_timeout=8)
            if c_res.get("ok"):
                history_steps.append("🔘 '🚏 Поиск остановки' tanlandi")
                await asyncio.sleep(1.2)
                # Bekat nomini yuborish
                stop_name = "Сергели хокимияти" if any(w in q for w in ("sergeli", "hokim")) else "Сергели"
                await client.send_message(bot_entity, stop_name)
                history_steps.append(f"✍️ Bekat nomi '{stop_name}' yuborildi")
                await asyncio.sleep(2.0)

                stop_msgs = await client.get_messages(bot_entity, limit=2)
                final_msg = stop_msgs[0] if stop_msgs else menu_msg
                upd_matrix, upd_flat = extract_buttons_from_message(final_msg)
                upd_text = (final_msg.message or final_msg.raw_text or "").strip()
                btn_str = format_buttons_for_display(upd_matrix) if upd_matrix else ""

                return {
                    "ok": True,
                    "bot": bot_tag,
                    "steps": history_steps,
                    "response": upd_text,
                    "buttons_matrix": upd_matrix,
                    "buttons_str": btn_str,
                    "buttons": upd_flat,
                }

        # 2-variant: Avtobus raqami bo'yicha marshrut qidirish
        if bus_num and has_menu:
            c_res = await click_chat_button(client, bot_tag, "Маршруты", wait_timeout=8)
            if c_res.get("ok"):
                history_steps.append("🔘 '🔍 Маршруты' tanlandi")
                await asyncio.sleep(1.2)

                await client.send_message(bot_entity, bus_num)
                history_steps.append(f"✍️ '{bus_num}' raqami yuborildi")
                await asyncio.sleep(2.0)

                after_bus = await client.get_messages(bot_entity, limit=3)
                dir_msg = None
                for m in after_bus:
                    if m and not m.out:
                        dir_msg = m
                        break

                final_msg = dir_msg or menu_msg
                if dir_msg and getattr(dir_msg, "buttons", None):
                    dir_clicked = False
                    for row in dir_msg.buttons:
                        for btn in row:
                            b_text = getattr(btn, "text", "") or ""
                            if prefer_direction and prefer_direction in b_text.lower():
                                try:
                                    await btn.click()
                                    history_steps.append(f"🔘 Yo'nalish: '{b_text}' tanlandi")
                                    dir_clicked = True
                                    break
                                except Exception:
                                    pass
                        if dir_clicked:
                            break

                    if not dir_clicked and dir_msg.buttons:
                        first_btn = dir_msg.buttons[0][0]
                        try:
                            await first_btn.click()
                            history_steps.append(f"🔘 Yo'nalish: '{getattr(first_btn, 'text', '')}' tanlandi")
                        except Exception:
                            pass

                    await asyncio.sleep(2.0)
                    final_msgs = await client.get_messages(bot_entity, limit=2)
                    if final_msgs:
                        final_msg = final_msgs[0]

                upd_matrix, upd_flat = extract_buttons_from_message(final_msg)
                upd_text = (final_msg.message or final_msg.raw_text or "").strip()
                btn_str = format_buttons_for_display(upd_matrix) if upd_matrix else ""

                return {
                    "ok": True,
                    "bot": bot_tag,
                    "steps": history_steps,
                    "response": upd_text,
                    "buttons_matrix": upd_matrix,
                    "buttons_str": btn_str,
                    "buttons": upd_flat,
                }
    except Exception as e:
        logger.error("navigate_tash3tm_bot da xatolik: %s", e)

    # Standart zaxira: rekursiyasiz to'g'ridan-to'g'ri muloqot (_is_direct=True)
    return await interact_with_telegram_bot(client, bot_tag, query, _is_direct=True)


async def explore_telegram_bot(client, bot_username: str, max_depth: int = 2) -> dict[str, Any]:
    """
    Avtonom Bot O'rganuvchi (Bot Explorer):
    - Berilgan botga kiradi, /start buyrug'ini yuboradi.
    - Chiqqan barcha asosiy tugmalarni ro'yxatga oladi.
    - Har bir asosiy bo'lim tugmasini (max 4-5 ta) navbatma-navbat bosib ko'rib, ichidagi imkoniyatlarni o'rganadi.
    - Natijada mentor uchun botning to'liq kognitiv arxitekturasi va qo'llanmasini tuzadi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijozi ulanmagan"}

    raw_bot = (bot_username or "").strip().lstrip("@")
    if not raw_bot:
        return {"ok": False, "error": "Bot username kiritilmadi"}

    bot_tag = f"@{raw_bot}"

    try:
        try:
            bot_entity = await client.get_input_entity(bot_tag)
        except Exception:
            bot_entity = await client.get_entity(bot_tag)
    except Exception as e:
        return {"ok": False, "error": f"'{bot_tag}' Telegramda topilmadi: {e}"}

    try:
        # 1. /start buyrug'ini yuborish
        start_msg = await client.send_message(bot_entity, "/start")
        await asyncio.sleep(2.0)

        recent = await client.get_messages(bot_entity, limit=4)
        main_msg = None
        for rm in recent:
            if rm and not rm.out and getattr(rm, "buttons", None):
                main_msg = rm
                break
        if not main_msg and recent:
            main_msg = recent[0]

        if not main_msg:
            return {"ok": False, "error": f"'{bot_tag}' botidan javob kelmadi."}

        main_matrix, main_buttons = extract_buttons_from_message(main_msg)
        main_text = (main_msg.message or main_msg.raw_text or "").strip()

        explored_sections = []
        # Asosiy tugmalardan 4 tasini bosib ko'rib o'rganish
        btns_to_explore = [b for b in main_buttons if b and len(b.strip()) > 1][:4]

        for b_name in btns_to_explore:
            try:
                # Tugmani bosish
                c_res = await click_chat_button(client, bot_tag, b_name, wait_timeout=6)
                if c_res.get("ok"):
                    sub_text = (c_res.get("response") or "").strip()
                    sub_btns = c_res.get("buttons") or []
                    explored_sections.append({
                        "button": b_name,
                        "screen_text": sub_text[:300],
                        "sub_buttons": sub_btns[:6],
                    })
                await asyncio.sleep(1.2)
            except Exception as b_err:
                logger.debug("Tugma bosishda xatolik (%s): %s", b_name, b_err)

        return {
            "ok": True,
            "bot": bot_tag,
            "main_text": main_text,
            "main_buttons": main_buttons,
            "main_matrix": main_matrix,
            "sections": explored_sections,
        }
    except Exception as e:
        logger.error("explore_telegram_bot da xatolik: %s", e)
        return {"ok": False, "error": str(e)}



async def interact_with_telegram_bot(
    client,
    bot_username: str,
    query_or_command: str = "",
    click_button: str | None = None,
    wait_timeout: int = 15,
    _is_direct: bool = False,
) -> dict[str, Any]:
    """
    Boshqa Telegram botlari (@tash3tm_bot va h.k.) bilan avtonom muloqot qiladi:
    - Botga buyruq yoki so'rov jo'natadi.
    - Inline tugmalarni ko'radi va bosadi.
    - Barcha yangi xabar va tugmalar panelini to'liq formatlab qaytaradi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijozi ulanmagan"}

    raw_bot = (bot_username or "").strip().lstrip("@")
    if not raw_bot:
        return {"ok": False, "error": "Bot username kiritilmadi"}

    bot_tag = f"@{raw_bot}"
    cmd = (query_or_command or "").strip()

    # Agar @tash3tm_bot bo'lsa va avtobus/yo'nalish so'ralsa, maxsus ko'p bosqichli navigator (rekursiya bo'lmasligi uchun _is_direct tekshiriladi)
    if not _is_direct and raw_bot.lower() in ("tash3tm_bot", "3tmbot") and any(w in cmd.lower() for w in ("avtobus", "sergeli", "massiv", "marshrut", "hokim", "astanovka", "bekat")):
        return await navigate_tash3tm_bot(client, cmd)

    # Agar faqat tugmani bosish so'ralgan bo'lsa
    if click_button and not cmd:
        return await click_chat_button(client, bot_tag, click_button, wait_timeout=wait_timeout)

    try:
        bot_entity = await client.get_input_entity(bot_tag)
    except Exception as e:
        logger.warning("Bot entitysini olishda ogohlantirish (%s): %s", bot_tag, e)
        try:
            bot_entity = await client.get_entity(bot_tag)
        except Exception as e2:
            return {"ok": False, "error": f"'{bot_tag}' boti Telegramda topilmadi: {e2}"}

    try:
        last_msg_id = 0
        try:
            prev_msgs = await client.get_messages(bot_entity, limit=1)
            if prev_msgs:
                last_msg_id = prev_msgs[0].id
        except Exception:
            pass

        # Buyruq jo'natish
        sent_cmd = cmd or "/start"
        sent_msg = await client.send_message(bot_entity, sent_cmd)

        response_msg = None
        start_wait = time.time()
        while time.time() - start_wait < wait_timeout:
            await asyncio.sleep(1.2)
            try:
                cur_msgs = await client.get_messages(bot_entity, limit=3)
                for cm in cur_msgs:
                    if cm.id > (sent_msg.id if sent_msg else last_msg_id) and not cm.out:
                        response_msg = cm
                        break
                if response_msg:
                    break
            except Exception:
                pass

        if not response_msg:
            # Agar yangi xabar kelmagan bo'lsa, oxirgi xabarni olamiz
            cur = await client.get_messages(bot_entity, limit=1)
            response_msg = cur[0] if cur else None

        if not response_msg:
            return {
                "ok": False,
                "error": f"'{bot_tag}' botidan {wait_timeout} soniya ichida javob kelmadi.",
            }

        clicked_info = None
        if click_button:
            # So'ralgan tugmani bosish
            c_res = await click_chat_button(client, bot_tag, click_button, message_id=response_msg.id, wait_timeout=wait_timeout)
            if c_res.get("ok"):
                clicked_info = c_res.get("clicked")
                return {
                    "ok": True,
                    "bot": bot_tag,
                    "query": cmd,
                    "response": c_res.get("response", ""),
                    "clicked_button": clicked_info,
                    "buttons_str": c_res.get("buttons_str", ""),
                    "buttons": c_res.get("buttons", []),
                }

        reply_text = (response_msg.message or response_msg.raw_text or "").strip()
        b_matrix, b_flat = extract_buttons_from_message(response_msg)
        btn_str = format_buttons_for_display(b_matrix) if b_matrix else ""

        return {
            "ok": True,
            "bot": bot_tag,
            "query": cmd,
            "response": reply_text,
            "buttons_str": btn_str,
            "buttons": b_flat,
            "buttons_matrix": b_matrix,
            "clicked_button": clicked_info,
        }
    except Exception as e:
        logger.error("'%s' boti bilan muloqotda xatolik: %s", bot_tag, e)
        return {"ok": False, "error": f"Bot bilan muloqotda xatolik: {e}"}


# Kengaytirilgan Unicode shrift va belgilarni standartlashtirish jadvallari
FONT_MAP = {
    # Small capitals
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ғ": "f", "ɢ": "g", "ʜ": "h",
    "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p",
    "ǫ": "q", "ʀ": "r", "ꜱ": "s", "s": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w",
    "x": "x", "ʏ": "y", "ᴢ": "z",
    # Enclosed / Squared (🅰-🆉)
    "🅰": "a", "🅱": "b", "🅲": "c", "🅳": "d", "🅴": "e", "🅵": "f", "🅶": "g", "🅷": "h",
    "🅸": "i", "🅹": "j", "🅺": "k", "🅻": "l", "🅼": "m", "🅽": "n", "🅾": "o", "🅿": "p",
    "🆀": "q", "🆁": "r", "🆂": "s", "🆃": "t", "🆄": "u", "🆅": "v", "🆆": "w", "🆇": "x",
    "🆈": "y", "🆉": "z",
    # Circled (Ⓐ-Ⓩ, ⓐ-ⓩ)
    "Ⓐ": "a", "Ⓑ": "b", "Ⓒ": "c", "Ⓓ": "d", "Ⓔ": "e", "Ⓕ": "f", "Ⓖ": "g", "Ⓗ": "h",
    "Ⓘ": "i", "Ⓙ": "j", "Ⓚ": "k", "Ⓛ": "l", "Ⓜ": "m", "Ⓝ": "n", "Ⓞ": "o", "Ⓟ": "p",
    "Ⓠ": "q", "Ⓡ": "r", "Ⓢ": "s", "Ⓣ": "t", "Ⓤ": "u", "Ⓥ": "v", "Ⓦ": "w", "Ⓧ": "x",
    "Ⓨ": "y", "Ⓩ": "z",
    "ⓐ": "a", "ⓑ": "b", "ⓒ": "c", "ⓓ": "d", "ⓔ": "e", "ⓕ": "f", "ⓖ": "g", "ⓗ": "h",
    "ⓘ": "i", "ⓙ": "j", "ⓚ": "k", "ⓛ": "l", "ⓜ": "m", "ⓝ": "n", "ⓞ": "o", "ⓟ": "p",
    "ⓠ": "q", "ⓡ": "r", "ⓢ": "s", "ⓣ": "t", "ⓤ": "u", "ⓥ": "v", "ⓦ": "w", "ⓧ": "x",
    "ⓨ": "y", "ⓩ": "z",
}

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o", "ғ": "g", "қ": "q", "ҳ": "h", "ы": "i",
}


TECH_ALIASES = {
    "piton": "python",
    "payton": "python",
    "paytonchik": "python",
    "dz": "js",
    "djs": "js",
    "djava": "java",
    "skript": "script",
    "frontend": "frontend",
    "front": "frontend",
    "backend": "backend",
    "bekend": "backend",
    "koddi": "coddy",
    "kodi": "coddy",
    "doker": "docker",
    "gitxab": "github",
}

# O'zbek va Rus tillaridagi ismlar, so'zlar va guruhlar uchun kelishik hamda erkalash qo'shimchalari
WORD_SUFFIXES = (
    # O'zbekcha qo'shimchalar
    "bek", "jon", "voy", "xon", "ning", "dan", "ga", "ni", "da", "chi", "lar", "lari", "lik",
    # Ruscha kelishik va qo'shimchalar (-а, -я, -у, -ю, -ом, -ем, -ам, -ами, -ах, -ов, -ев, -ин, -чик...)
    "chik", "ochka", "echka", "ushka", "yushka", "ova", "eva", "ina", "ov", "ev", "in",
    "om", "em", "am", "ax", "yax", "ami", "yami", "ogo", "ego", "omu", "emu",
    "a", "ya", "u", "yu", "e", "i", "y",
)


def is_russian_text(text: str) -> bool:
    """Matn rus tilida yozilganini aniqlaydi (kirill harflari yoki ruscha asosiy so'zlar bo'yicha)."""
    if not text:
        return False
    cyr_count = len(re.findall(r"[\u0400-\u04FF]", text))
    if cyr_count >= 2:
        return True
    ru_markers = {
        "кто", "где", "как", "сколько", "найди", "поиск", "сообщения", "учеников", "запомни",
        "выучи", "привет", "здравствуйте", "спасибо", "ладно", "понятно", "ясно", "группа",
        "группе", "чаты", "написал", "писал", "отправь", "напиши", "покажи", "база"
    }
    words = set(re.findall(r"[a-zA-Z\u0400-\u04FF]+", text.lower()))
    return bool(words & ru_markers)


def normalize_text(text: str) -> str:
    """
    Har qanday noodatiy shrift (Mathematical Bold, Italic, Script, Fraktur, Double-struck,
    Small-caps, Squared, Circled, Fullwidth, Emojilar va bezaklar) va Kirill yozuvidagi belgilarni
    standart toza kichik lotin harflariga o'tkazadi hamda texnik terminlarni standartlashtiradi.
    """
    if not text:
        return ""
    import unicodedata

    # 1. Custom xaritalar orqali almashtirish
    res = []
    for c in text:
        low = c.lower()
        if c in FONT_MAP:
            res.append(FONT_MAP[c])
        elif low in FONT_MAP:
            res.append(FONT_MAP[low])
        elif low in CYRILLIC_TO_LATIN:
            res.append(CYRILLIC_TO_LATIN[low])
        else:
            res.append(c)
    s = "".join(res)

    # 2. NFKD orqali barcha matematik qalin, kursiv va to'liq kenglikdagi belgilarni ajratish
    decomposed = unicodedata.normalize("NFKD", s)
    filtered = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 3. O'zbekcha tutuq belgilari va qo'shtirnoqlarni birxillashtirish
    for quote_char in ["`", "‘", "’", "ʻ", "ʼ", "´"]:
        filtered = filtered.replace(quote_char, "'")

    # 4. Bezaklar, emojilar va noodatiy simvollarni tozalash (faqat harf, son, bo'shliq va tutuq qoladi)
    cleaned = re.sub(r"[^\w\s\']", " ", filtered)
    # Bo'shliqlarni birxillashtirish
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()

    # 5. Texnik terminlar va keng tarqalgan sinonimlarni birlashtirish (piton -> python, djs -> js...)
    words = cleaned.split()
    if words:
        words = [TECH_ALIASES.get(w, w) for w in words]
        cleaned = " ".join(words)

    return cleaned


def match_text(query: str, target: str) -> bool:
    """
    Shrift, bezaklar, orfoepik xatolar, ruscha/o'zbekcha turlanishlardan (qo'shimchalar) qat'iy nazar
    maksimal kuchli qidiruv taqqoslashini amalga oshiradi.
    """
    from difflib import SequenceMatcher

    q_norm = normalize_text(query)
    t_norm = normalize_text(target)
    if not q_norm or not t_norm:
        return False

    # 1. 1 yoki 2 harfli qisqa nomlar faqat 100% teng bo'lgandagina mos keladi (masalan 'D' yoki 'Al')
    # Hech qachon 1-2 harfli so'z uzun qidiruvga submatn bo'lib tushib qolmasin!
    if len(t_norm) <= 2 or len(q_norm) <= 2:
        return q_norm == t_norm

    # 2. To'liq submatn mosligi (query target ichida to'liq bo'lsa)
    if q_norm in t_norm:
        return True

    # 3. Tutuq belgisisiz yumshoq moslik (masalan: otkir va o'tkir, g'ayrat va gayrat)
    q_no_quote = q_norm.replace("'", "")
    t_no_quote = t_norm.replace("'", "")
    if q_no_quote in t_no_quote:
        return True

    # 4. 'x' va 'h' tovushlarini birlashtirilgan holda tekshirish (Shohruh <-> Shoxrux, Bahrom <-> Baxrom)
    q_xh = q_no_quote.replace("x", "h")
    t_xh = t_no_quote.replace("x", "h")
    if q_xh in t_xh:
        return True

    # 5. So'zlar / tokenlar bo'yicha va Fuzzy taqqoslash
    q_tokens = [w for w in q_xh.split() if len(w) >= 2]
    t_tokens = [w for w in t_xh.split() if len(w) >= 2]

    def tokens_match(qt: str, tt: str) -> bool:
        if qt == tt or qt in tt or tt in qt:
            return True
        # Qo'shimchalarsiz (stemming) taqqoslash
        qt_clean = qt
        for suf in sorted(WORD_SUFFIXES, key=len, reverse=True):
            if qt.endswith(suf) and len(qt) - len(suf) >= 3:
                qt_clean = qt[:-len(suf)]
                break
        tt_clean = tt
        for suf in sorted(WORD_SUFFIXES, key=len, reverse=True):
            if tt.endswith(suf) and len(tt) - len(suf) >= 3:
                tt_clean = tt[:-len(suf)]
                break
        if qt_clean == tt_clean or qt_clean in tt_clean or tt_clean in qt_clean:
            return True
        # 1 ta harf xatosi bo'lsa (Fuzzy ratio >= 0.82)
        if SequenceMatcher(None, qt, tt).ratio() >= 0.82:
            return True
        return False

    # Agar qidiruv 2 va undan ortiq so'zdan iborat bo'lsa (masalan: 'ibrohim qodirjonov'):
    # Har bir qidiruv so'zi (ism va familiya) target ichida qatnashgan bo'lishi SHART!
    if len(q_tokens) >= 2:
        return all(any(tokens_match(qt, tt) for tt in t_tokens) for qt in q_tokens)

    # Agar qidiruv 1 ta so'zdan iborat bo'lsa (masalan: 'ibrohim'):
    if q_tokens:
        return any(tokens_match(q_tokens[0], tt) for tt in t_tokens)

    return False


def extract_person_name_from_query(text: str) -> str | None:
    """
    Mentor buyrug'idan qidirilayotgan o'quvchi yoki shaxs ismini aniq ajratib oladi.
    Masalan:
    'ibrohim qodirjonovni uydigilarini va ozini lichkasini topib olib kel...' -> 'ibrohim qodirjonov'
    'shohruhning uydagilarini kontaktini top' -> 'shohruh'
    'ali valiyevni nomerini topib ber' -> 'ali valiyev'
    """
    if not text:
        return None
    raw = text.strip()
    raw = re.sub(r"^(?:menga\s+|iltimos\s+|qani\s+|borib\s+)+", "", raw, flags=re.I).strip()

    # 1. Kalit so'zlar oldidan kelgan ism-familiyani ajratish
    kw_pattern = re.compile(
        r"\b(?:uyd[ai]gilar\w*|oila\w*|ota[\s\-]onasi\w*|ozini\w*|o['’`]zini\w*|lichka\w*|kontakt\w*|raqam\w*|nomer\w*|telefon\w*|chat\w*|profil\w*|o['’`]?quvchini|bolani|odamni|top\w*|qidir\w*|aniqla\w*|izla\w*)\b",
        re.I
    )
    m = kw_pattern.search(raw)
    if m and m.start() > 0:
        prefix = raw[:m.start()].strip()
        clean = re.sub(r"(?:ning|ni|i|si|dan|degan)$", "", prefix, flags=re.I).strip()
        words = clean.split()
        if 1 <= len(words) <= 3 and len(clean) >= 2:
            return clean

    # 2. To'g'ridan-to'g'ri ism + qo'shimcha + top / qidir
    p2 = re.search(
        r"^([A-Za-z0-9_'\`\u0400-\u04FF]+(?:\s+[A-Za-z0-9_'\`\u0400-\u04FF]+)?)(?:ning|ni|i|si)?\s+(?:top|qidir|izla|aniqla|topib\s+kel|topib\s+olib\s+kel)\b",
        raw, re.I
    )
    if p2:
        clean = p2.group(1).strip()
        clean = re.sub(r"(?:ning|ni|i|si|dan|degan)$", "", clean, flags=re.I).strip()
        words = clean.split()
        if 1 <= len(words) <= 3 and len(clean) >= 2:
            return clean

    return None


async def find_student_or_contact(client, name_or_query: str) -> dict[str, Any]:
    """
    O'quvchini, uning guruhini, uydagilarini, shaxsiy lichkasini yoki guruhdagi a'zoligini qidiradi:
    1. Student CRM bazasidan (shrift va orfoepiyaga bog'liq bo'lmagan holda).
    2. Telegram barcha dialoglaridan (shaxsiy chatlar va guruh nomlari bo'yicha).
    3. Telegram guruhlari ichidagi ishtirokchilar / a'zolar ro'yxatidan.
    """
    raw_q = (name_or_query or "").strip()
    if not raw_q:
        return {"crm_students": [], "telegram_chats": [], "group_members": []}

    # 1. CRM bazasidan o'quvchilarni qidirish (kengaytirilgan filtr bilan)
    all_crm_students = memory_service.get_students(limit=200)
    crm_matches = []
    for s in all_crm_students:
        fname = s.get("full_name", "")
        uname = s.get("username", "")
        gname = s.get("group_name", "")
        if match_text(raw_q, fname) or match_text(raw_q, uname) or match_text(raw_q, gname):
            crm_matches.append(s)
            if len(crm_matches) >= 10:
                break

    # 2. Telegram dialoglaridan (Lichkalar va Guruh nomlari) qidirish
    tg_matches = []
    group_dialogs_to_inspect = []

    if client:
        try:
            dialogs = await client.get_dialogs(limit=250)
            family_keywords = ["dada", "ota", "ona", "oyi", "aka", "uka", "amaki", "tog'a"]
            q_norm = normalize_text(raw_q)
            q_digits = re.sub(r"\D", "", raw_q)

            for d in dialogs:
                d_name = (d.name or "").strip()
                entity = d.entity
                username = getattr(entity, "username", None) or ""
                phone = getattr(entity, "phone", None) or ""
                p_digits = re.sub(r"\D", "", phone) if phone else ""

                matched = False
                if match_text(raw_q, d_name) or match_text(raw_q, username):
                    matched = True
                elif p_digits and q_digits and (q_digits in p_digits or (len(q_digits) >= 7 and p_digits.endswith(q_digits))):
                    matched = True
                else:
                    for kw in family_keywords:
                        if kw in q_norm and match_text(kw, d_name):
                            matched = True
                            break

                is_group = d.is_group or d.is_channel
                if is_group:
                    group_dialogs_to_inspect.append(d)

                if matched:
                    tg_matches.append({
                        "id": d.id,
                        "name": d_name,
                        "type": "group" if is_group else "user",
                        "username": f"@{username}" if username else None,
                        "phone": f"+{phone}" if phone else None,
                        "link": f"https://t.me/{username}" if username else (
                            f"https://t.me/c/{str(d.id)[4:]}" if str(d.id).startswith("-100") else f"tg://user?id={d.id}"
                        ),
                    })
        except Exception as e:
            logger.error("Telegram dialoglarini qidirishda xatolik: %s", e)

    # 3. Guruhlar ichidagi ishtirokchilar (Group Participants) orasidan qidirish
    group_members = []
    if client and group_dialogs_to_inspect:
        try:
            seen_user_ids = {m["id"] for m in tg_matches if m.get("type") == "user"}
            for gd in group_dialogs_to_inspect[:20]:
                try:
                    participants = await client.get_participants(gd.entity, limit=100)
                    for p in participants:
                        if getattr(p, "bot", False):
                            continue
                        if p.id in seen_user_ids:
                            continue

                        p_first = getattr(p, "first_name", "") or ""
                        p_last = getattr(p, "last_name", "") or ""
                        p_full = f"{p_first} {p_last}".strip()
                        p_uname = getattr(p, "username", None) or ""

                        if match_text(raw_q, p_full) or match_text(raw_q, p_uname):
                            seen_user_ids.add(p.id)
                            group_members.append({
                                "user_id": p.id,
                                "name": p_full or "Noma'lum",
                                "username": f"@{p_uname}" if p_uname else None,
                                "in_group": gd.name,
                                "group_id": gd.id,
                                "link": f"https://t.me/{p_uname}" if p_uname else f"tg://user?id={p.id}",
                            })
                            if len(group_members) >= 15:
                                break
                except Exception as pe:
                    logger.debug("Guruh a'zolarini o'qishda e'tiborsiz xatolik (%s): %s", gd.name, pe)

                if len(group_members) >= 15:
                    break
        except Exception as e:
            logger.error("Guruh a'zolarini qidirishda xatolik: %s", e)

    return {
        "crm_students": crm_matches,
        "telegram_chats": tg_matches[:10],
        "group_members": group_members,
    }


async def send_telegram_message(client, target_query: str, message_text: str) -> dict[str, Any]:
    """
    Berilgan foydalanuvchi yoki guruhga Telegram orqali to'g'ridan-to'g'ri xabar yuboradi.
    target_query: username (@user), chat_id (-100...), yoki guruh/kontakt nomi (masalan: 'Ali', 'Python')
    """
    if not client:
        return {"ok": False, "error": "Telegram mijoz ulanmagan"}

    target = (target_query or "").strip()
    text = (message_text or "").strip()

    if not target or not text:
        return {"ok": False, "error": "Qabul qiluvchi va xabar matni ko'rsatilishi shart"}

    resolved_entity = None
    target_name = target

    try:
        # Mentorning o'ziga yo'naltirilgan xabarlar (Nuriddin, ustoz, me, o'zimga) -> Vazifalar guruhi
        if target.lower() in ("nuriddin", "nuriddinga", "ustoz", "teacher", "me", "o'zim", "ozim", "menga", "o'zimga"):
            from config import get_vazifalar_chat_target_sync
            resolved_entity = get_vazifalar_chat_target_sync()
            target_name = "Vazifalar guruhi"

        # 1. Agar @username yoki telefon yoki to'g'ridan-to'g'ri chat ID bo'lsa
        if not resolved_entity and (target.startswith("@") or target.startswith("+") or re.match(r"^-?\d+$", target)):
            parse_target = int(target) if re.match(r"^-?\d+$", target) else target
            try:
                resolved_entity = await client.get_entity(parse_target)
            except Exception:
                pass

        # 2. Agar topilmasa, mavjud dialoglar orasidan nom bo'yicha qidiramiz
        if not resolved_entity:
            dialogs = await client.get_dialogs(limit=120)
            # Standartlashtirilgan moslik orqali qidirish (shrift va bezaklarga qaramasdan)
            for d in dialogs:
                d_name = d.name or ""
                uname = getattr(d.entity, "username", "") or ""
                if match_text(target, d_name) or (uname and match_text(target, uname)):
                    resolved_entity = d.entity
                    target_name = d_name
                    break

        # 3. CRM dan tekshirish
        if not resolved_entity:
            students = memory_service.get_students(limit=100)
            for s in students:
                fname = s.get("full_name", "")
                u = s.get("username", "")
                if match_text(target, fname) or (u and match_text(target, u)):
                    if u:
                        try:
                            resolved_entity = await client.get_entity(u)
                            target_name = fname or u
                            break
                        except Exception:
                            pass

        if not resolved_entity:
            return {
                "ok": False,
                "error": f"'{target}' nomli foydalanuvchi yoki guruh topilmadi. Iltimos @username yoki aniqroq nom kiriting.",
            }

        sent = await client.send_message(resolved_entity, text)
        return {
            "ok": True,
            "target_name": target_name,
            "target_id": getattr(sent, "chat_id", None),
            "message_id": getattr(sent, "id", None),
            "text": text,
        }

    except Exception as e:
        logger.error("Telegram xabar yuborishda xatolik: %s", e)
        return {"ok": False, "error": str(e)}


async def delete_telegram_message(
    client,
    target_query: str = "",
    target_message: str = "",
    reply_msg_id: int | None = None,
    current_chat_id: int | None = None,
) -> dict[str, Any]:
    """
    Belgilangan guruh, chat yoki lichkadagi xabarni o'chiradi (revoke=True).
    target_query: guruh/chat nomi, @username yoki chat ID (agar bo'sh yoki 'bu'/'shu' bo'lsa, current_chat_id ishlatiladi)
    target_message: xabar ID raqami, yoki 'oxirgi' / 'last' / bo'sh bo'lsa oxirgi xabar
    reply_msg_id: agar xabarga reply qilib o'chirish so'ralgan bo'lsa, reply qilingan xabar ID si
    """
    if not client:
        return {"ok": False, "error": "Telegram mijoz ulanmagan"}

    target = (target_query or "").strip()
    msg_spec = (target_message or "").strip()

    resolved_entity = None
    target_name = target or "Ushbu chat"
    target_msg_id = None

    try:
        # 1. Agar xabarga reply qilingan bo'lsa va target ko'rsatilmagan yoki umumiy olmosh bo'lsa:
        if reply_msg_id and (not target or target.lower() in ("bu", "shu", "ushbu", "shu chat", "o'sha", "xabar", "oxirgi", "this")):
            resolved_entity = current_chat_id
            target_name = "Ushbu chat"
            target_msg_id = reply_msg_id
        else:
            # Chat entity ni topish
            if not target or target.lower() in ("bu", "shu", "ushbu", "shu chat", "current"):
                resolved_entity = current_chat_id
                target_name = "Ushbu chat"
            elif target.startswith("@") or target.startswith("+") or re.match(r"^-?\d+$", target):
                parse_target = int(target) if re.match(r"^-?\d+$", target) else target
                try:
                    resolved_entity = await client.get_entity(parse_target)
                except Exception:
                    pass

            if not resolved_entity and target:
                dialogs = await client.get_dialogs(limit=120)
                for d in dialogs:
                    d_name = d.name or ""
                    uname = getattr(d.entity, "username", "") or ""
                    if match_text(target, d_name) or (uname and match_text(target, uname)):
                        resolved_entity = d.entity
                        target_name = d_name
                        break

            if not resolved_entity:
                resolved_entity = current_chat_id
                target_name = target or "Ushbu chat"

            if not resolved_entity:
                return {
                    "ok": False,
                    "error": f"'{target}' nomli chat yoki guruh topilmadi.",
                }

            # Xabar ID sini aniqlash
            if msg_spec.isdigit():
                target_msg_id = int(msg_spec)
            elif reply_msg_id:
                target_msg_id = reply_msg_id
            elif msg_spec and msg_spec.lower() not in ("last", "oxirgi", "so'nggi", "shu", "bu", ""):
                # Muallif (odam) nomi, username yoki xabar matni bo'yicha qidirib o'chirish:
                messages = await client.get_messages(resolved_entity, limit=35)
                found = None
                for m in messages:
                    sender = getattr(m, "sender", None)
                    s_name = (getattr(sender, "first_name", "") or "") + " " + (getattr(sender, "last_name", "") or "")
                    s_user = getattr(sender, "username", "") or ""
                    m_text = m.text or m.message or ""
                    # 1. Jo'natuvchi nomi yoki username mos kelsa
                    if match_text(msg_spec, s_name) or (s_user and match_text(msg_spec, s_user)):
                        found = m
                        break
                    # 2. Xabar matnida qidirilayotgan ibora bo'lsa
                    if msg_spec.lower() in m_text.lower():
                        found = m
                        break
                if found:
                    target_msg_id = found.id
                else:
                    return {"ok": False, "error": f"'{target_name}' chatida '{msg_spec}' bo'yicha o'chirish uchun xabar topilmadi."}
            else:
                # Oxirgi xabarni olish
                messages = await client.get_messages(resolved_entity, limit=2)
                if not messages:
                    return {"ok": False, "error": f"'{target_name}' chatida o'chirish uchun xabarlar topilmadi."}
                # Agar ushbu chat bo'lsa va oxirgi xabar mentorning hozirgi buyrug'i bo'lsa, undan oldingisini o'chirish
                target_msg_id = messages[0].id

        await client.delete_messages(resolved_entity, target_msg_id, revoke=True)
        logger.info("Xabar muvaffaqiyatli o'chirildi: %s (msg_id: %s)", target_name, target_msg_id)
        return {
            "ok": True,
            "target_name": target_name,
            "message_id": target_msg_id,
        }
    except Exception as e:
        logger.error("Telegram xabarni o'chirishda xatolik: %s", e)
        return {"ok": False, "error": str(e)}


async def schedule_telegram_message(
    client,
    target_query: str,
    message_text: str,
    delay_or_time: str,
    chat_id: int = 0
) -> dict[str, Any]:
    """
    Xabarni ma'lum vaqtdan so'ng (masalan '2 daqiqadan so'ng', '10 minutdan keyin', 'ertaga 07:00 da')
    avtomatik yuborish uchun rejalashtiradi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijoz ulanmagan"}

    target = (target_query or "").strip()
    text = (message_text or "").strip()
    time_str = (delay_or_time or "").strip()

    if not target or not text:
        return {"ok": False, "error": "Qabul qiluvchi va xabar matni ko'rsatilishi shart"}

    # 1. Qabul qiluvchini aniqlash
    resolved_entity = None
    target_name = target
    if target.lower() in ("nuriddin", "nuriddinga", "ustoz", "teacher", "me", "o'zim", "ozim", "menga", "o'zimga"):
        from config import get_vazifalar_chat_target_sync
        resolved_entity = get_vazifalar_chat_target_sync()
        target_name = "Vazifalar guruhi"
    else:
        try:
            if target.startswith("@") or target.startswith("+") or re.match(r"^-?\d+$", target):
                parse_target = int(target) if re.match(r"^-?\d+$", target) else target
                resolved_entity = await client.get_entity(parse_target)
            else:
                dialogs = await client.get_dialogs(limit=80)
                for d in dialogs:
                    if match_text(target, d.name or "") or (getattr(d.entity, "username", None) and match_text(target, d.entity.username)):
                        resolved_entity = d.entity
                        target_name = d.name
                        break
        except Exception as ent_err:
            logger.debug("Entity qidirishda ogohlantirish: %s", ent_err)

    if not resolved_entity:
        from config import get_vazifalar_chat_target_sync
        resolved_entity = get_vazifalar_chat_target_sync()
        target_name = "Vazifalar guruhi"

    # 2. Vaqtni aniqlash
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    delay_sec = None
    remind_at_dt = None

    from services.ai_service import extract_smart_reminder
    parsed = extract_smart_reminder(time_str, current_tashkent_time=now.strftime("%Y-%m-%d %H:%M:%S"))
    if parsed and parsed.get("remind_at"):
        try:
            remind_at_dt = datetime.strptime(parsed["remind_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tashkent_tz)
            diff = (remind_at_dt - now).total_seconds()
            if diff >= 5.0:
                delay_sec = diff
        except Exception:
            pass

    if not delay_sec:
        rel_match = re.search(r"(\d+|bir\s+necha|1\s+necha|yarim)\s*(daqiqa\w*|minut\w*|sekund\w*|soniya\w*|soat\w*|kun\w*|chas\w*)", time_str.lower())
        if rel_match:
            raw_val = rel_match.group(1).strip()
            unit = rel_match.group(2).lower()
            val = 2.0 if "necha" in raw_val else (0.5 if "yarim" in raw_val else float(raw_val))
            if "sekund" in unit or "soniya" in unit:
                delay_sec = float(val)
            elif "soat" in unit or "chas" in unit:
                delay_sec = float(val * 3600)
            elif "kun" in unit:
                delay_sec = float(val * 86400)
            else:
                delay_sec = float(val * 60)
            remind_at_dt = now + timedelta(seconds=delay_sec)

    if not delay_sec or delay_sec < 5:
        delay_sec = 120.0
        remind_at_dt = now + timedelta(seconds=120)

    remind_at_str = remind_at_dt.strftime("%Y-%m-%d %H:%M:%S")

    if delay_sec < 60:
        delay_human = f"{int(delay_sec)} soniya"
    elif delay_sec < 3600:
        delay_human = f"{int(delay_sec // 60)} daqiqa"
    else:
        delay_human = f"{delay_sec / 3600:.1f} soat"

    rem_chat_id = chat_id or (getattr(resolved_entity, "id", 0) if hasattr(resolved_entity, "id") else 0)
    if not rem_chat_id or str(rem_chat_id).strip() in ("0", "me", ""):
        # Barcha admin boshqaruvlari va eslatmalar FAQAT Vazifalar guruhida bo'lishi shart
        rem_chat_id = config.escalation_chat or config.mentor_user_id

    rem_id = memory_service.add_reminder(
        chat_id=rem_chat_id,
        reminder_text=f"[{target_name} ga xabar]: {text}",
        remind_at=remind_at_str,
    )

    # 3. Yuborish vazifasi (ovozli uvidomleniya bilan):
    if delay_sec <= 7200:
        async def _do_send():
            try:
                await asyncio.sleep(delay_sec)
                # Agar bu o'ziga eslatma bo'lsa (target "me" / "o'zimga" yoki chat ichidagi eslatma):
                if resolved_entity == "me" or target in ("me", "o'zim", "o'zimga", "men"):
                    from services.reminder_service import send_due_reminder_notification
                    await send_due_reminder_notification(
                        rem_id=rem_id,
                        chat_id=rem_chat_id,
                        task_text=text,
                        remind_at=remind_at_str,
                        client=client,
                    )
                else:
                    await client.send_message(resolved_entity, text)
                    memory_service.mark_reminder_sent_if_pending(rem_id)
                logger.info("⏳ Rejalashtirilgan xabar muvaffaqiyatli yetkazildi [%s]: %s", target_name, text[:30])
            except Exception as se:
                logger.error("Rejalashtirilgan xabarni yuborishda xatolik: %s", se)

        asyncio.create_task(_do_send())

    return {
        "ok": True,
        "target_name": target_name,
        "remind_at": remind_at_str,
        "delay_human": delay_human,
        "text": text,
    }



async def list_recent_chats(client, limit: int = 15) -> list[dict[str, Any]]:
    """Mentorning eng so'nggi guruhlari va kontaktlari ro'yxatini qaytaradi."""
    if not client:
        return []
    try:
        dialogs = await client.get_dialogs(limit=limit)
        items = []
        for d in dialogs:
            items.append({
                "id": d.id,
                "name": d.name or "Noma'lum",
                "type": "group" if (d.is_group or d.is_channel) else "user",
                "username": getattr(d.entity, "username", None),
            })
        return items
    except Exception as e:
        logger.error("Dialoglar ro'yxatini olishda xatolik: %s", e)
        return []


def _format_relative_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    try:
        tashkent_tz = ZoneInfo("Asia/Tashkent")
        now = datetime.now(tashkent_tz)
        target = dt if dt.tzinfo else dt.replace(tzinfo=tashkent_tz)
        target = target.astimezone(tashkent_tz)
        diff = now - target
        secs = int(diff.total_seconds())
        if secs < 60:
            rel = "hozirgina"
        elif secs < 3600:
            rel = f"{secs // 60} daqiqa oldin"
        elif secs < 86400:
            rel = f"{secs // 3600} soat oldin"
        elif secs < 172800:
            rel = "kecha"
        else:
            rel = f"{secs // 86400} kun oldin"
        time_str = target.strftime("%H:%M")
        return f"{time_str} ({rel})"
    except Exception:
        return _get_tashkent_time(dt)


async def get_recent_incoming_senders(client, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
    """
    Mentorga Telegram orqali kelgan (incoming) eng so'nggi xabarlar va ularni kim yozganini aniqlaydi.
    Aslo mentorning o'zi yuborgan xabarlarni 'kelgan xabar' deb hisoblamaydi.
    """
    if not client:
        return [{"error": "Telegram mijoz ulanmagan"}]

    from config import config
    mentor_ids = {config.mentor_user_id, 8105823872}
    vazifalar_target = str(config.escalation_chat).strip()

    try:
        me = await client.get_me()
        if me:
            mentor_ids.add(me.id)
    except Exception:
        pass

    results = []
    try:
        dialogs = await client.get_dialogs(limit=35)
        for d in dialogs:
            # Saved Messages yoki Vazifalar boshqaruv guruhini ro'yxatdan chiqarish
            if d.id in mentor_ids:
                continue
            if str(d.id) == vazifalar_target or str(d.id).replace("-100", "-") == vazifalar_target.replace("-100", "-"):
                continue
            if d.name and "vazifalar" in d.name.lower():
                continue

            last_msg = d.message
            if not last_msg:
                continue

            unread = getattr(d, "unread_count", 0) or 0
            if unread_only and unread == 0:
                continue

            is_out = bool(last_msg.out)
            chat_title = d.name or "Noma'lum"
            chat_type = "guruh" if (d.is_group or d.is_channel) else "lichka"
            username = getattr(d.entity, "username", None)
            phone = getattr(d.entity, "phone", None)

            incoming_msg = last_msg
            if is_out:
                try:
                    # Agar oxirgi xabarni mentor yuborgan bo'lsa, chatdagi oxirgi kelgan xabarni qidiramiz
                    recent_msgs = await client.get_messages(d.entity, limit=6)
                    found_incoming = next((m for m in recent_msgs if not m.out), None)
                    if found_incoming:
                        incoming_msg = found_incoming
                    else:
                        incoming_msg = None
                except Exception:
                    pass

            if incoming_msg:
                sender = await incoming_msg.get_sender()
                sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or chat_title
                if getattr(sender, "last_name", None):
                    sender_name += f" {sender.last_name}"
                sender_uname = getattr(sender, "username", None) or username
                text_snip = (incoming_msg.text or incoming_msg.raw_text or "").strip().replace("\n", " ")
                if not text_snip:
                    if incoming_msg.photo:
                        text_snip = "[Rasm / Skrinshot]"
                    elif incoming_msg.voice:
                        text_snip = "[Ovozli xabar]"
                    elif incoming_msg.document:
                        text_snip = f"[Fayl: {getattr(incoming_msg.file, 'name', 'hujjat')}]"
                    else:
                        text_snip = "[Xabar]"

                if len(text_snip) > 120:
                    text_snip = text_snip[:117] + "..."

                results.append({
                    "chat_id": d.id,
                    "chat_title": chat_title,
                    "chat_type": chat_type,
                    "sender_name": sender_name,
                    "sender_username": f"@{sender_uname}" if sender_uname else None,
                    "phone": phone,
                    "text": text_snip,
                    "date": incoming_msg.date,
                    "time_str": _format_relative_time(incoming_msg.date),
                    "unread_count": unread,
                    "last_action_by_me": is_out,
                })
            elif is_out:
                results.append({
                    "chat_id": d.id,
                    "chat_title": chat_title,
                    "chat_type": chat_type,
                    "sender_name": chat_title,
                    "sender_username": f"@{username}" if username else None,
                    "phone": phone,
                    "text": f"(Oxirgi xabarni siz yozgansiz: «{last_msg.text[:50] if last_msg.text else ''}»)",
                    "date": last_msg.date,
                    "time_str": _format_relative_time(last_msg.date),
                    "unread_count": unread,
                    "last_action_by_me": True,
                })

            if len(results) >= limit:
                break

    except Exception as e:
        logger.error("Kelgan xabarlarni olishda xatolik: %s", e)
        return [{"error": str(e)}]

    results.sort(key=lambda x: x.get("date") or datetime.min, reverse=True)
    return results[:limit]


def format_recent_senders_report(results: list[dict[str, Any]], is_ru: bool = False) -> str:
    if not results:
        if is_ru:
            return "📬 **Сообщения Telegram:**\nПока новых входящих сообщений не найдено."
        return "📬 **Telegram xabarlari:**\nHozircha sizga kelgan yangi xabarlar topilmadi."
    if len(results) == 1 and "error" in results[0]:
        if is_ru:
            return f"❌ **Ошибка получения сообщений Telegram:** {results[0]['error']}"
        return f"❌ **Telegram xabarlarini olishda xatolik:** {results[0]['error']}"

    if is_ru:
        lines = ["📬 **Последние написавшие вам (Входящие сообщения Telegram):**\n"]
    else:
        lines = ["📬 **Telegramda sizga oxirgi marta xabar yozganlar (Kelgan xabarlar):**\n"]
    for i, r in enumerate(results, 1):
        s_name = r.get("sender_name", "Неизвестный" if is_ru else "Noma'lum")
        uname = r.get("sender_username")
        c_title = r.get("chat_title", "")
        c_type = r.get("chat_type", "lichka")
        unread = r.get("unread_count", 0)
        time_str = r.get("time_str", "")
        text = r.get("text", "")

        if is_ru:
            type_badge = "💬 Личка" if c_type == "lichka" else f"👥 Группа ({c_title})"
            unread_badge = f" 🔴 **({unread} непрочитанных)**" if unread > 0 else ""
        else:
            type_badge = "💬 Shaxsiy lichka" if c_type == "lichka" else f"👥 Guruh ({c_title})"
            unread_badge = f" 🔴 **({unread} ta o'qilmagan)**" if unread > 0 else ""
        uname_str = f" ({uname})" if uname else ""

        lines.append(f"{i}. 👤 **{s_name}**{uname_str} [{type_badge}]{unread_badge}")
        lines.append(f"   ⏰ *{time_str}*")
        lines.append(f"   💬 «{text}»\n")

    return "\n".join(lines).strip()


def is_absence_message(text: str) -> bool:
    """
    O'quvchining darsga kela olmasligi, kechikishi, betobligi yoki dars qoldirishi haqidagi xabarni aniqlaydi.
    Har qanday variantlarni ("kasalma", "shomoladim", "boleyu", "ploxo chustvuyu", "kelolmayman" va h.k.) qamrab oladi.
    """
    t = text.lower().strip()
    if not t:
        return False

    absence_triggers = [
        # 1. O'zbekcha kasallik / betoblik / shamollash / dori-darmon / og'riq
        r"\b(?:kasal\w*|sh[ao]moll?a\w*|og['’`]?ri\w*|isitma\w*|harorat\w*|temperatura\w*)\b",
        r"\b(?:maza\w*|tob\w*)\s+(?:yo['’`]?q|bo['’`]?lmay\w*|qoch\w*)\b",
        r"\b(?:bosh\w*|qor\w*|tish\w*|tomoq\w*|oyoq\w*|bel\w*|ko['’`]?z\w*)\s+og['’`]?ri\w*\b",
        r"\b(?:doktor\w*|shifoxona\w*|bolnitsa\w*|vrach\w*|davolan\w*|ukol\w*)\b",
        # 2. O'zbekcha darsga kelolmaslik / bormaslik / kechikish
        r"\b(?:kelolmay\w*|kelomiman\w*|kelomayman\w*|kelolmas\w*|kelomas\w*|kelomadim\w*|kela\s+olmay\w*)\b",
        r"\b(?:borolmay\w*|boromiman\w*|boromayman\w*|borolmas\w*|boromas\w*|boromadim\w*|bora\s+olmay\w*)\b",
        r"\b(?:bor\w*|kel\w*|chiq\w*)\s+(?:olmay\w*|bo['’`]?lmay\w*|qol\w*)\b",
        r"\b(?:qatnasholmay\w*|qatnasha\s+olmay\w*|qatnashmay\w*)\b",
        r"\b(?:bo['’`]?lolmay\w*|bo['’`]?la\s+olmay\w*)\b",
        r"\b(?:darsga|darsda)\s+(?:\w+\s+){0,2}(?:bormay\w*|kelmay\w*|bo['’`]?l\w*|qatnash\w*)\b",
        r"\b(?:darsni|dars)\s+(?:qoldir\w*|otkaz\w*|o['’`]?tkaz\w*)\b",
        r"\b(?:kechikib\w*|kechikaman\w*|kech\s+qolaman\w*|kech\s+boraman\w*)\b",
        # 3. Ruscha (Kirill)
        r"\b(?:боле[юея]\w*|заболе[лл]\w*|приболе[лл]\w*|болен|больна)\b",
        r"\b(?:плохо\s+(?:себя\s+)?чувству\w*|чувствую\s+себя\s+плохо|мне\s+плохо)\b",
        r"\b(?:температура\w*|жар\b|знобит|тошнит|простуд\w*|грипп\w*|кашель|ангина)\b",
        r"\b(?:не\s+смогу\s+(?:\w+\s+){0,2}(?:прийти|быть|присутствовать|приехать)|не\s+приду|не\s+буду\s+(?:\w+\s+){0,2}(?:уроке|заняти\w*))\b",
        r"\b(?:пропущу|пропускаю|отсутствую)\s+(?:урок\w*|заняти\w*)\b",
        r"\b(?:опоздаю|задержусь)\s*(?:на\s+урок)?\b",
        # 4. Ruscha (Lotin / Translit - "boleyu", "ploxo chustvuyu", "zabolel")
        r"\b(?:boleyu\w*|zabolel\w*|pribolel\w*|bolen|bolna)\b",
        r"\b(?:ploxo|ploho)\s+(?:sebya\s+)?(?:chustvu\w*|chuvstvu\w*)\b",
        r"\b(?:chuvstvu\w*|chustvu\w*)\s+sebya\s+(?:ploxo|ploho)\b",
        r"\b(?:mne\s+(?:ploxo|ploho)|samochuvstvie\s+(?:ploxoe|plohoe))\b",
        r"\b(?:ne\s+smogu\s+(?:\w+\s+){0,2}(?:priyti|bit|prisutstvovat)|ne\s+pridu|ne\s+budu\s+(?:\w+\s+){0,2}(?:uroke|zanyatii))\b",
        r"\b(?:propus[ht]u|propuskayu)\s+(?:urok|zanyatie)\b",
        r"\b(?:opozdayu|zaderjus)\b",
    ]
    return any(re.search(pat, t, re.I) for pat in absence_triggers)


async def find_sick_students_in_chats(client, limit: int = 40) -> dict[str, Any]:
    """
    Shaxsiy yozishmalar (lichkalar) va guruhlar ichidan oxirgi xabarlarda
    kasal bo'lgan ("kasalma", "shomoladim", "boleyu", "ploxo chustvuyu", "kelolmayman" va h.k.)
    barcha o'quvchilarni titkilab topadi va hisobot beradi.
    """
    if not client:
        return {"ok": False, "error": "Telegram mijoz ulanmagan"}

    from config import config
    mentor_ids = {config.mentor_user_id, 8105823872}
    try:
        me = await client.get_me()
        if me:
            mentor_ids.add(me.id)
    except Exception:
        pass

    vazifalar_target = str(config.escalation_chat).strip()
    found_sick = []

    try:
        dialogs = await client.get_dialogs(limit=limit)
        for d in dialogs:
            if d.id in mentor_ids:
                continue
            if str(d.id) == vazifalar_target or str(d.id).replace("-100", "-") == vazifalar_target.replace("-100", "-"):
                continue
            if d.name and "vazifalar" in d.name.lower():
                continue
            if getattr(d.entity, "bot", False):
                continue
            if not d.is_user and not d.is_group:
                continue

            try:
                msgs = await client.get_messages(d.entity, limit=12)
                for m in msgs:
                    if m.out:
                        continue
                    m_text = m.text or ""
                    if not m_text.strip():
                        continue

                    if is_absence_message(m_text):
                        u_name = d.name or getattr(d.entity, "first_name", "") or "Noma'lum"
                        if getattr(d.entity, "last_name", None):
                            u_name += f" {d.entity.last_name}"
                        username = f"@{d.entity.username}" if getattr(d.entity, "username", None) else "Username yo'q"
                        phone = getattr(d.entity, "phone", None) or "Mavjud emas"
                        tash_time = _format_relative_time(m.date)

                        found_sick.append({
                            "user_id": d.id,
                            "name": u_name,
                            "username": username,
                            "phone": phone,
                            "text": m_text.strip(),
                            "date": tash_time,
                            "date_obj": m.date,
                            "chat_type": "Lichka" if d.is_user else f"Guruh: {d.name}",
                        })
                        break
            except Exception as d_err:
                logger.debug("Dialog %s xabarlarini o'qishda xatolik: %s", d.id, d_err)

    except Exception as e:
        logger.error("Kasal o'quvchilarni izlashda xatolik: %s", e)
        return {"ok": False, "error": str(e)}

    found_sick.sort(key=lambda x: x.get("date_obj") or datetime.min, reverse=True)

    if not found_sick:
        report = (
            "ℹ️ **Shaxsiy yozishmalar (lichkalar) ichida hozircha betob bo'lgan yoki darsga kelolmasligini bildirgan o'quvchilar aniqlanmadi.**\n\n"
            "O'quvchilardan 'kasalma', 'shomoladim', 'boleyu', 'ploxo chustvuyu' kabi xabar kelishi bilan tizim zudlik bilan **@coddycamp_sergeli** ga hisobot yuboradi."
        )
        return {"ok": True, "count": 0, "report": report, "students": []}

    lines = [
        f"🏥 **Shaxsiy yozishmalar (lichkalar) bo'yicha aniqlangan betob / dars qoldirgan o'quvchilar ({len(found_sick)} nafar):**\n"
    ]
    for idx, s in enumerate(found_sick, 1):
        lines.append(
            f"{idx}. 👤 **{s['name']}** ({s['username']})\n"
            f"   🆔 ID: `{s['user_id']}` | 📞 Tel: `{s['phone']}`\n"
            f"   📍 Manba: {s['chat_type']} | ⏰ Vaqti: {s['date']}\n"
            f"   💬 Xabari: «{s['text']}»\n"
            f"   📋 Holat: @coddycamp_sergeli ma'muriyatiga nazorat uchun yuboriladi"
        )
        lines.append("")

    return {"ok": True, "count": len(found_sick), "report": "\n".join(lines).strip(), "students": found_sick}


def format_learning_report(topic: str, content: str, is_ru: bool = False) -> str:
    if is_ru:
        return (
            f"🧠 **Новое знание успешно сохранено в памяти!**\n\n"
            f"• 📌 **Тема:** `{topic}`\n"
            f"• 📝 **Правило / Указание:** {content}\n\n"
            f"✅ _Это правило зафиксировано в памяти, и впредь я буду строго следовать ему!_"
        )
    return (
        f"🧠 **Yangi bilim muvaffaqiyatli eslab qolindi!**\n\n"
        f"• 📌 **Mavzu:** `{topic}`\n"
        f"• 📝 **Qoida / Ko'rsatma:** {content}\n\n"
        f"✅ _Ushbu qoida xotiraga saqlandi va bundan keyin barcha savollarda unga qat'iy amal qilaman!_"
    )


def format_all_learned_report(facts: list[dict], is_ru: bool = False) -> str:
    if not facts:
        if is_ru:
            return "🧠 **База знаний AI:**\nПока дополнительных правил не изучено. Напишите 'Запомни: ...', и я мгновенно усвою!"
        return "🧠 **AI Bilimlar Bazasi:**\nHozircha qo'shimcha o'rganilgan qoidalar yo'q. Menga xohlagan qoidangizni 'Eslab qol: ...' deb yozsangiz, darhol o'rganib olaman!"
    if is_ru:
        lines = [f"🧠 **Все изученные знания и правила ({len(facts)} шт.):**\n"]
    else:
        lines = [f"🧠 **AI tomonidan o'rganilgan barcha bilim va qoidalar ({len(facts)} ta):**\n"]
    for i, f in enumerate(facts, 1):
        lines.append(f"{i}. 📌 **[{f['topic'].upper()}]**: {f['content']}")
    if is_ru:
        lines.append("\n💡 _Чтобы добавить новое правило, напишите: 'Запомни: [Тема] - [Правило]'._")
    else:
        lines.append("\n💡 _Yangi qoida qo'shish uchun: 'Eslab qol: [Mavzu] - [Qoida]' deb yozing._")
    return "\n".join(lines).strip()


async def get_group_info(client, group_query: str = "") -> dict[str, Any]:
    """
    Guruhdagi o'quvchilar/a'zolar soni, ismlari va ma'lumotlarini Telethon va CRM orqali aniqlaydi.
    """
    if not client:
        return {"error": "Telegram mijoz ulanmagan"}

    q = (group_query or "").strip().lower()
    generic_words = [
        "", "guruh", "guruhda", "guruhimizda", "guruhlar", "barcha", "hamma", "darsda",
        "группа", "группы", "группе", "в группе", "в нашей группе", "все", "всех", "на уроке"
    ]
    is_generic = q in generic_words or any(q.startswith(w) for w in ["hamma", "barcha", "guruhlar", "все", "всех", "группы"])

    try:
        dialogs = await client.get_dialogs(limit=100)
        group_dialogs = [d for d in dialogs if (d.is_group or d.is_channel)]

        if not group_dialogs:
            return {"groups": [], "message": "Siz a'zo bo'lgan guruhlar topilmadi."}

        matched_groups = []
        if is_generic:
            matched_groups = group_dialogs
        else:
            matched_groups = [d for d in group_dialogs if match_text(q, d.name or "")]
            if not matched_groups:
                matched_groups = group_dialogs

        results = []
        for d in matched_groups[:5]:
            total_count = getattr(d.entity, "participants_count", None)
            participants = []
            humans_count = 0
            bots_count = 0
            try:
                p_list = await client.get_participants(d.entity, limit=100)
                if p_list:
                    total_count = len(p_list)
                    for p in p_list:
                        is_bot = getattr(p, "bot", False)
                        if is_bot:
                            bots_count += 1
                        else:
                            humans_count += 1
                            name = (getattr(p, "first_name", "") or "") + " " + (getattr(p, "last_name", "") or "")
                            participants.append({
                                "name": name.strip() or "Noma'lum",
                                "username": getattr(p, "username", None),
                                "id": p.id,
                            })
            except Exception as pe:
                logger.debug("Ishtirokchilarni olishda cheklov: %s", pe)

            crm_students = memory_service.get_students(limit=50, search=d.name)

            results.append({
                "group_id": d.id,
                "group_name": d.name,
                "total_members": total_count if total_count is not None else (humans_count + bots_count),
                "students_count": humans_count if humans_count > 0 else (total_count or 0),
                "bots_count": bots_count,
                "sample_participants": participants[:8],
                "crm_count": len(crm_students),
            })

        return {"groups": results}
    except Exception as e:
        logger.error("Guruh ma'lumotlarini olishda xatolik: %s", e)
        return {"error": str(e)}


def get_students_summary() -> dict[str, Any]:
    """Student CRM dagi o'quvchilar umumiy statistikasi."""
    students = memory_service.get_students(limit=500)
    total = len(students)
    groups = {}
    statuses = {"a'lo": 0, "yaxshi": 0, "o'rtacha": 0, "past": 0}
    for s in students:
        g = s.get("group_name") or "Guruhsiz"
        groups[g] = groups.get(g, 0) + 1
        st = s.get("status", "yaxshi").lower()
        if st in statuses:
            statuses[st] += 1
        else:
            statuses[st] = 1

    return {
        "total_students": total,
        "by_group": groups,
        "by_status": statuses,
    }


async def get_student_common_groups(client, user_id: int) -> list[str]:
    """
    O'quvchi va mentor o'rtasidagi umumiy Telegram guruhlarini aniqlaydi.
    Vazifalar / Boshqaruv markazi va admin guruhlarini chiqarib tashlaydi.
    """
    if not client or not user_id:
        return []
    try:
        from telethon.tl.functions.messages import GetCommonChatsRequest
        res = await client(GetCommonChatsRequest(user_id=user_id, max_id=0, limit=20))
        groups = []
        for chat in getattr(res, "chats", []):
            title = getattr(chat, "title", "") or ""
            clean_title = title.strip()
            # Admin yoki Vazifalar guruhini o'tkazib yuborish
            lower_title = clean_title.lower()
            if any(ign in lower_title for ign in ("vazifalar", "boshqaruv", "markaz", "admin", "co-pilot", "copilot")):
                continue
            if clean_title:
                groups.append(clean_title)
        return groups
    except Exception as e:
        logger.warning("Umumiy guruhlarni olishda xatolik (user_id=%s): %s", user_id, e)
        return []


WEEKDAY_NAMES_UZ = {
    0: "Dushanba",
    1: "Seshanba",
    2: "Chorshanba",
    3: "Payshanba",
    4: "Juma",
    5: "Shanba",
    6: "Yakshanba",
}

WEEKDAY_NAMES_RU = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def parse_group_schedule(group_title: str) -> dict[str, Any]:
    """
    Guruh nomidan dars kunlari (toq/juft) va dars soatini aniqlaydi.
    Masalan:
      - 'Backend Python Toq 16:00' -> Toq kunlar (Du-Chor-Ju), soat 16:00
      - 'Frontend Juft 14:00' -> Juft kunlar (Se-Pay-Sha), soat 14:00
      - 'Python Du-Chor-Ju 18:30' -> Toq kunlar (Du-Chor-Ju), soat 18:30
    """
    title_raw = group_title or ""
    title_lower = title_raw.lower()

    # Dars vaqtini qidirish (masalan: 16:00, 14.30, 09:00)
    time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", title_raw)
    lesson_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}" if time_match else None

    # Toq kunlar: Du-Chor-Ju (Dushanba, Chorshanba, Juma) -> 0, 2, 4
    toq_patterns = [
        r"\btoq\b",
        r"\bodd\b",
        r"\bdu(?:shanba)?[- /_]?chor(?:shanba)?[- /_]?ju(?:ma)?\b",
        r"\bпн[- /_]?ср[- /_]?пт\b",
        r"\bпонедельник[- /_]?среда[- /_]?пятница\b",
        r"\b1[-.,/_]3[-.,/_]5\b",
    ]

    # Juft kunlar: Se-Pay-Sha (Seshanba, Payshanba, Shanba) -> 1, 3, 5
    juft_patterns = [
        r"\bjuft\b",
        r"\beven\b",
        r"\bse(?:shanba)?[- /_]?pay(?:shanba)?[- /_]?sha(?:nba)?\b",
        r"\bвт[- /_]?чт[- /_]?сб\b",
        r"\bвторник[- /_]?четверг[- /_]?суббота\b",
        r"\b2[-.,/_]4[-.,/_]6\b",
    ]

    # Weekend: Shanba-Yakshanba yoki Yakshanba -> 5, 6
    weekend_patterns = [
        r"\bshanba[- /_]?yakshanba\b",
        r"\bсб[- /_]?вс\b",
        r"\byakshanba\b",
        r"\bвоскресенье\b",
    ]

    is_toq = any(re.search(p, title_lower) for p in toq_patterns)
    is_juft = any(re.search(p, title_lower) for p in juft_patterns)
    is_weekend = any(re.search(p, title_lower) for p in weekend_patterns)

    if is_toq and not is_juft:
        return {
            "has_schedule": True,
            "schedule_type": "toq",
            "weekdays": [0, 2, 4],
            "days_uz": "Toq kunlar (Dushanba, Chorshanba, Juma)",
            "days_ru": "Нечётные дни (Понедельник, Среда, Пятница)",
            "lesson_time": lesson_time,
        }
    elif is_juft and not is_toq:
        return {
            "has_schedule": True,
            "schedule_type": "juft",
            "weekdays": [1, 3, 5],
            "days_uz": "Juft kunlar (Seshanba, Payshanba, Shanba)",
            "days_ru": "Чётные дни (Вторник, Четверг, Суббота)",
            "lesson_time": lesson_time,
        }
    elif is_weekend:
        is_both = "shanba" in title_lower or "сб" in title_lower
        return {
            "has_schedule": True,
            "schedule_type": "weekend",
            "weekdays": [5, 6] if is_both else [6],
            "days_uz": "Dam olish kunlari (Shanba, Yakshanba)" if is_both else "Yakshanba kunlari",
            "days_ru": "Выходные дни (Суббота, Воскресенье)" if is_both else "Воскресенье",
            "lesson_time": lesson_time,
        }

    return {
        "has_schedule": False,
        "schedule_type": None,
        "weekdays": [],
        "days_uz": "Odatiy jadval bo'yicha",
        "days_ru": "По обычному расписанию",
        "lesson_time": lesson_time,
    }


def _calc_next_lesson(now_tashkent: datetime, weekdays: list[int], current_weekday: int) -> tuple[str | None, str | None]:
    """Keyingi dars kunini va sanasini UZ/RU formatida hisoblaydi."""
    if not weekdays:
        return None, None
    future_diffs = []
    for d in weekdays:
        diff = (d - current_weekday) % 7
        if diff == 0:
            diff = 7  # keyingi galgi dars kuni
        future_diffs.append((diff, d))
    if not future_diffs:
        return None, None
    future_diffs.sort(key=lambda x: x[0])
    min_diff, next_day_idx = future_diffs[0]
    next_date = now_tashkent + timedelta(days=min_diff)
    date_str = next_date.strftime("%d.%m.%Y")
    day_uz = WEEKDAY_NAMES_UZ.get(next_day_idx, "")
    day_ru = WEEKDAY_NAMES_RU.get(next_day_idx, "")
    if min_diff == 1:
        next_uz = f"ertaga ({day_uz}, {date_str})"
        next_ru = f"завтра ({day_ru}, {date_str})"
    else:
        next_uz = f"{day_uz} ({date_str})"
        next_ru = f"{day_ru} ({date_str})"
    return next_uz, next_ru


async def check_group_schedule_and_announcements(
    client,
    chat_id: int,
    is_group: bool,
    student_user_id: int | None = None
) -> dict[str, Any]:
    """
    O'quvchi guruhi va undagi @coddycamp_sergeli ma'muriyati e'lonlarini (bayram, dars qoldirilishi)
    hamda guruh nomidan toq/juft dars jadvalini avtomatik tahlil qiladi.
    """
    if not client:
        return {
            "status": "unknown_group",
            "group_name": None,
            "announcement_text": None,
            "announcement_date": None,
            "has_schedule": False,
            "schedule_type": None,
            "days_uz": "",
            "days_ru": "",
            "lesson_time": None,
            "is_today_lesson": None,
            "today_name_uz": "",
            "today_name_ru": "",
            "next_lesson_uz": None,
            "next_lesson_ru": None,
        }

    target_groups = []

    try:
        if is_group:
            entity = await client.get_entity(chat_id)
            title = getattr(entity, "title", "") or "CoddyCamp guruhi"
            target_groups.append((entity, title))
        else:
            # Shaxsiy chat: o'quvchi bilan umumiy guruhlarni topamiz
            target_user = student_user_id or chat_id
            from telethon.tl.functions.messages import GetCommonChatsRequest
            res = await client(GetCommonChatsRequest(user_id=target_user, max_id=0, limit=10))
            for chat in getattr(res, "chats", []):
                t_title = getattr(chat, "title", "") or ""
                clean_title = t_title.strip()
                lower_t = clean_title.lower()
                if any(ign in lower_t for ign in ("vazifalar", "boshqaruv", "markaz", "admin", "co-pilot", "copilot")):
                    continue
                if clean_title:
                    target_groups.append((chat, clean_title))
    except Exception as err:
        logger.warning("Guruhlarni aniqlashda xatolik: %s", err)

    if not target_groups:
        return {
            "status": "unknown_group",
            "group_name": None,
            "announcement_text": None,
            "announcement_date": None,
            "has_schedule": False,
            "schedule_type": None,
            "days_uz": "",
            "days_ru": "",
            "lesson_time": None,
            "is_today_lesson": None,
            "today_name_uz": "",
            "today_name_ru": "",
            "next_lesson_uz": None,
            "next_lesson_ru": None,
        }

    # Bayram yoki dars qoldirilishi haqidagi regex qoliplari
    cancellation_patterns = [
        r"\bbayram\b",
        r"\bdam\s+olish\b",
        r"\bdars(?:lar)?\s+(?:bo['’`]?lmaydi|qoldiril\w*|otkazil\w*|o'tkazil\w*|to['’`]?xtatil\w*)\b",
        r"\bdars\s+yo['’`]?q\b",
        r"\bta['’`]?til\b",
        r"\btatil\b",
        r"\berkin\s+kun\b",
        r"\bпраздник\w*\b",
        r"\bвыходн\w*\b",
        r"\bурок(?:ов|и)?\s+(?:не\s+будет|отменя\w*|перенос\w*)\b",
        r"\bзаняти[ей]\s+(?:не\s+будет|отменя\w*)\b",
        r"\bканикул\w*\b",
    ]

    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now_tashkent = datetime.now(tashkent_tz)
    current_weekday = now_tashkent.weekday()

    # 1. Avval guruhdagi so'nggi e'lonlarni tekshiramiz
    for chat_obj, g_title in target_groups[:2]:
        sched_info = parse_group_schedule(g_title)
        try:
            messages = await client.get_messages(chat_obj, limit=25)
            for m in messages:
                if not m.text or len(m.text.strip()) < 5:
                    continue

                # Xabar yuborilgan vaqtni tekshirish (oxirgi 72 soat ichidagi e'lonlar)
                m_date = m.date
                if m_date:
                    if m_date.tzinfo is None:
                        m_date = m_date.replace(tzinfo=tashkent_tz)
                    else:
                        m_date = m_date.astimezone(tashkent_tz)
                    diff_hours = (now_tashkent - m_date).total_seconds() / 3600.0
                    if diff_hours > 72:
                        continue

                m_lower = m.text.lower()
                has_cancel_keyword = any(re.search(pat, m_lower, re.I) for pat in cancellation_patterns)

                if has_cancel_keyword:
                    clean_announcement = m.text.strip()
                    if len(clean_announcement) > 300:
                        clean_announcement = clean_announcement[:297] + "..."
                    date_str = m_date.strftime("%d.%m.%Y") if m_date else "Yaqinda"
                    
                    weekdays = sched_info["weekdays"]
                    next_uz, next_ru = _calc_next_lesson(now_tashkent, weekdays, current_weekday)
                    return {
                        "status": "found_cancellation",
                        "group_name": g_title,
                        "announcement_text": clean_announcement,
                        "announcement_date": date_str,
                        "has_schedule": sched_info["has_schedule"],
                        "schedule_type": sched_info["schedule_type"],
                        "days_uz": sched_info["days_uz"],
                        "days_ru": sched_info["days_ru"],
                        "lesson_time": sched_info["lesson_time"],
                        "is_today_lesson": (current_weekday in weekdays) if weekdays else None,
                        "today_name_uz": WEEKDAY_NAMES_UZ.get(current_weekday, ""),
                        "today_name_ru": WEEKDAY_NAMES_RU.get(current_weekday, ""),
                        "next_lesson_uz": next_uz,
                        "next_lesson_ru": next_ru,
                    }
        except Exception as msg_err:
            logger.warning("Guruh [%s] xabarlarini tahlil qilishda ogohlantirish: %s", g_title, msg_err)

    # 2. E'lon topilmadi - asosiy guruh nomidan dars jadvalini aniqlaymiz
    primary_group = target_groups[0][1]
    sched_info = parse_group_schedule(primary_group)
    weekdays = sched_info["weekdays"]
    is_today_lesson = (current_weekday in weekdays) if weekdays else None
    next_uz, next_ru = _calc_next_lesson(now_tashkent, weekdays, current_weekday)

    return {
        "status": "normal_schedule",
        "group_name": primary_group,
        "announcement_text": None,
        "announcement_date": None,
        "has_schedule": sched_info["has_schedule"],
        "schedule_type": sched_info["schedule_type"],
        "days_uz": sched_info["days_uz"],
        "days_ru": sched_info["days_ru"],
        "lesson_time": sched_info["lesson_time"],
        "is_today_lesson": is_today_lesson,
        "today_name_uz": WEEKDAY_NAMES_UZ.get(current_weekday, ""),
        "today_name_ru": WEEKDAY_NAMES_RU.get(current_weekday, ""),
        "next_lesson_uz": next_uz,
        "next_lesson_ru": next_ru,
    }



ACTION_GROUP_INFO = re.compile(r'<<<ACTION:get_group_info\(["\']?(.*?)["\']?\)>>>', re.IGNORECASE)
ACTION_STUDENTS_SUM = re.compile(r'<<<ACTION:get_students_summary\(\)>>>', re.IGNORECASE)
ACTION_SEARCH = re.compile(r'<<<ACTION:search_telegram\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_FIND_CONTACT = re.compile(r'<<<ACTION:find_contact\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_SEND_MSG = re.compile(r'<<<ACTION:send_message\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)
ACTION_SCHEDULE_MSG = re.compile(r'<<<ACTION:schedule_message\(["\'](.*?)["\'],\s*["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)
ACTION_RECENT_SENDERS = re.compile(r'<<<ACTION:get_recent_senders\((.*?)\)>>>', re.IGNORECASE)
ACTION_LEARN_FACT = re.compile(r'<<<ACTION:learn_fact\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)
ACTION_GET_LEARNED = re.compile(r'<<<ACTION:get_learned_facts\(\)>>>', re.IGNORECASE)
ACTION_FORGET_FACT = re.compile(r'<<<ACTION:forget_fact\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_SET_PRIVATE_DELAY = re.compile(r'<<<ACTION:set_private_delay\((\d+)\)>>>', re.IGNORECASE)
ACTION_GET_PRIVATE_DELAY = re.compile(r'<<<ACTION:get_private_delay\(\)>>>', re.IGNORECASE)
ACTION_WEB_SEARCH = re.compile(r'<<<ACTION:web_search\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_IGNORE_USER = re.compile(
    r'<<<ACTION:ignore_user\(["\'](.*?)["\'](?:,\s*["\'](.*?)["\'])?(?:,\s*["\'](.*?)["\'])?(?:,\s*(\d+))?(?:,\s*(true|false))?\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_UNIGNORE_USER = re.compile(
    r'<<<ACTION:unignore_user\(["\'](.*?)["\']\)>>>',
    re.IGNORECASE,
)
ACTION_DELETE_MSG = re.compile(
    r'<<<ACTION:delete_message\(["\']?(.*?)["\']?(?:,\s*["\']?(.*?)["\']?)?\)>>>',
    re.IGNORECASE,
)
ACTION_INTERACT_BOT = re.compile(
    r'<<<ACTION:interact_with_bot\(["\'](.*?)["\'],\s*["\'](.*?)["\'](?:,\s*["\'](.*?)["\'])?\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_INSPECT_BOT = re.compile(
    r'<<<ACTION:inspect_bot\(["\'](.*?)["\'](?:,\s*(\d+))?\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_CLICK_BUTTON = re.compile(
    r'<<<ACTION:click_button\(["\'](.*?)["\'],\s*["\'](.*?)["\'](?:,\s*(\d+))?\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_SEARCH_CHAT = re.compile(
    r'<<<ACTION:search_chat\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_EXPLORE_BOT = re.compile(
    r'<<<ACTION:explore_bot\(["\'](.*?)["\'](?:,\s*(\d+))?\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_DEEP_SEARCH = re.compile(
    r'<<<ACTION:deep_search\(["\'](.*?)["\']\)>>>',
    re.IGNORECASE | re.DOTALL,
)
ACTION_FIND_SICK = re.compile(
    r'<<<ACTION:find_sick_students\((.*?)\)>>>',
    re.IGNORECASE,
)




async def block_telegram_user(client, user_entity_or_id) -> bool:
    """Telegram hisobining o'zida foydalanuvchini qora ro'yxatga (Block) kiritadi."""
    if not client or not user_entity_or_id:
        return False
    try:
        from telethon.tl.functions.contacts import BlockRequest
        from config import config
        uid = getattr(user_entity_or_id, "id", None) or (user_entity_or_id if isinstance(user_entity_or_id, int) else None)
        if uid and uid in (config.mentor_user_id, 8105823872):
            logger.warning("Xavfsizlik: Mentorni Telegramda bloklash qat'iyan taqiqlangan!")
            return False
        peer = await client.get_input_entity(user_entity_or_id)
        await client(BlockRequest(id=peer))
        logger.info("Telegram qora ro'yxatiga muvaffaqiyatli kiritildi: %s", user_entity_or_id)
        return True
    except Exception as e:
        logger.warning("Telegramda foydalanuvchini bloklashda xatolik (%s): %s", user_entity_or_id, e)
        return False


async def unblock_telegram_user(client, user_entity_or_id) -> bool:
    """Telegram qora ro'yxatidan (Unblock) chiqaradi."""
    if not client or not user_entity_or_id:
        return False
    try:
        from telethon.tl.functions.contacts import UnblockRequest
        peer = await client.get_input_entity(user_entity_or_id)
        await client(UnblockRequest(id=peer))
        logger.info("Telegram qora ro'yxatidan chiqarildi: %s", user_entity_or_id)
        return True
    except Exception as e:
        logger.warning("Telegramda foydalanuvchini blokdan chiqarishda xatolik (%s): %s", user_entity_or_id, e)
        return False


async def resolve_target_user(client, target_query: str, reply_user_id: int | None = None) -> dict[str, Any]:
    """
    Foydalanuvchini @username, ID, reply yoki kontakt/guruh a'zolari orqali topadi.
    """
    from config import config
    target = (target_query or "").strip()

    # 1. Agar reply orqali berilgan bo'lsa va target ko'rsatilmagan yoki umumiy olmosh bo'lsa:
    if reply_user_id and (not target or target.lower() in ("shu", "bu", "o'sha", "shu shu", "foydalanuvchi", "foydalanuvchini", "odam", "odamni", "buni", "shu odamni", "shu odam")):
        if reply_user_id in (config.mentor_user_id, 8105823872):
            return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
        try:
            entity = await client.get_entity(reply_user_id)
            uname = f"@{entity.username}" if getattr(entity, "username", None) else ""
            fname = getattr(entity, "first_name", "") or ""
            lname = getattr(entity, "last_name", "") or ""
            fullname = f"{fname} {lname}".strip() or f"User {reply_user_id}"
            return {"ok": True, "user_id": reply_user_id, "username": uname, "name": fullname, "entity": entity}
        except Exception:
            return {"ok": True, "user_id": reply_user_id, "username": "", "name": f"User {reply_user_id}", "entity": None}

    # 2. Agar @username yoki ID bo'lsa
    if target:
        if re.match(r"^-?\d+$", target):
            uid = int(target)
            if uid in (config.mentor_user_id, 8105823872):
                return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
            try:
                entity = await client.get_entity(uid)
                uname = f"@{entity.username}" if getattr(entity, "username", None) else ""
                fname = getattr(entity, "first_name", "") or ""
                lname = getattr(entity, "last_name", "") or ""
                fullname = f"{fname} {lname}".strip() or f"User {uid}"
                return {"ok": True, "user_id": uid, "username": uname, "name": fullname, "entity": entity}
            except Exception:
                return {"ok": True, "user_id": uid, "username": "", "name": f"User {uid}", "entity": None}

        if target.startswith("@"):
            try:
                entity = await client.get_entity(target)
                uid = entity.id
                if uid in (config.mentor_user_id, 8105823872):
                    return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
                uname = f"@{entity.username}" if getattr(entity, "username", None) else target
                fname = getattr(entity, "first_name", "") or ""
                lname = getattr(entity, "last_name", "") or ""
                fullname = f"{fname} {lname}".strip() or target
                return {"ok": True, "user_id": uid, "username": uname, "name": fullname, "entity": entity}
            except Exception as e:
                return {"ok": False, "error": f"'{target}' username bo'yicha Telegramdan profil topilmadi ({e})"}

        # 3. Agar ism bo'lsa (masalan: 'Jasur', 'Ali', 'Sardor'):
        try:
            contact_res = await find_student_or_contact(client, target)
            found_target = None
            for m in contact_res.get("group_members", []):
                if m.get("link"):
                    found_target = m
                    break
            if not found_target:
                for c in contact_res.get("telegram_chats", []):
                    if c.get("type") == "user" and c.get("username"):
                        found_target = c
                        break
            if not found_target:
                for s in contact_res.get("crm_students", []):
                    if s.get("username"):
                        found_target = s
                        break

            if found_target:
                t_uname = found_target.get("username")
                uid = found_target.get("user_id") or found_target.get("id") or found_target.get("telegram_id")
                if uid:
                    if uid in (config.mentor_user_id, 8105823872):
                        return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
                    return {
                        "ok": True,
                        "user_id": uid,
                        "username": t_uname or "",
                        "name": found_target.get("name") or found_target.get("full_name") or target,
                        "entity": None,
                    }
                elif t_uname:
                    try:
                        entity = await client.get_entity(t_uname)
                        uid = entity.id
                        if uid in (config.mentor_user_id, 8105823872):
                            return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
                        return {
                            "ok": True,
                            "user_id": uid,
                            "username": f"@{entity.username}" if getattr(entity, "username", None) else t_uname,
                            "name": found_target.get("name") or found_target.get("full_name") or target,
                            "entity": entity,
                        }
                    except Exception:
                        pass
        except Exception as search_err:
            logger.debug("Ism bo'yicha qidirishda ogohlantirish: %s", search_err)

        # 4. Telethon orqali to'g'ridan-to'g'ri entity qidirish
        try:
            entity = await client.get_entity(target)
            uid = getattr(entity, "id", None)
            if uid:
                if uid in (config.mentor_user_id, 8105823872):
                    return {"ok": False, "is_mentor": True, "error": "Ustoz daxlsizdir! Mentorni bloklash yoki cheklash mumkin emas."}
                uname = f"@{entity.username}" if getattr(entity, "username", None) else ""
                fname = getattr(entity, "first_name", "") or ""
                lname = getattr(entity, "last_name", "") or ""
                fullname = f"{fname} {lname}".strip() or target
                return {"ok": True, "user_id": uid, "username": uname, "name": fullname, "entity": entity}
        except Exception:
            pass

    if reply_user_id:
        return {"ok": True, "user_id": reply_user_id, "username": "", "name": f"User {reply_user_id}", "entity": None}

    return {"ok": False, "error": f"'{target}' bo'yicha aniq foydalanuvchi topilmadi. Iltimos @username, ID yoki xabarga reply qilib yozing."}


async def execute_agent_action(
    reply_text: str,
    client,
    orig_msg: str,
    is_admin_mode: bool = True,
    chat_id: int | None = None,
    reply_user_id: int | None = None,
    reply_msg_id: int | None = None,
) -> str:
    """
    AI javobidagi maxsus harakat buyruqlarini (Action Tools) yoki
    foydalanuvchining to'g'ridan-to'g'ri Telegram amallari talablarini (o'zbek va rus tillarida) bajaradi.
    Kechiktirilgan xabarlar, fakt o'rganish va lokatsiya amallari FAQAT mentor uchun (is_admin_mode=True) ishlaydi.
    """
    is_ru = is_russian_text(orig_msg)

    if not is_admin_mode:
        if is_ru:
            return "⛔️ Планирование сообщений и системные действия доступны исключительно для учителя Нуриддина в Центре Управления (Vazifalar)."
        return "⛔️ Kechiktirilgan xabarlar (schedule), lokatsiya va tizim amallari faqat mentor uchun Vazifalar guruhida ruxsat etilgan!"

    # ⛔️ XAVFSIZLIK QALQONI: Ulangan qurilmalarni (Active Sessions) o'chirish/chiqarish MUTLAQ TAQIQLANGAN!
    session_kill_pattern = (
        r"\b(?:ulangan\s+)?(?:qurilma\w*|ustroystv\w*|sessiy\w*|seans\w*)\s*(?:ni\s+)?(?:o['’`]?chir\w*|chiqar\w*|to['’`]?xtat\w*|uz\w*|reset\w*)\b|"
        r"\b(?:terminate\s+sessions|reset\s+authorizations|logout|delete\s+devices)\b|"
        r"\b(?:заверши|удали|отключи)\s+(?:все\s+)?(?:сесси[ий]|устройств[ао]|авторизаци[ии])\b"
    )
    if re.search(session_kill_pattern, orig_msg, re.I):
        if is_ru:
            return (
                "🛡 **Абсолютный запрет безопасности:**\n"
                "Завершение активных сессий или отключение подключённых устройств категорически запрещено политикой безопасности! "
                "Все ваши подключённые устройства и сеансы остаются в полной безопасности и неприкосновенности."
            )
        return (
            "🛡 **Mutlaq xavfsizlik taqiqi:**\n"
            "Ulangan qurilmalarni (Active Sessions) chiqarib yuborish yoki seanslarni o'chirish qat'iyan man etilgan! "
            "Sizning barcha ulangan qurilmalaringiz va sessiyalaringiz to'liq daxlsiz saqlanadi."
        )

    # 🌟 SAVOL VA BUYRUQNI QAT'IY AJRATISH (INQUIRY PROTECTION):
    # Agar mentor imkoniyatlar yoki vazifalar haqida so'ragan bo'lsa (masalan: "Nmala qilolasan?"),
    # hech qanday ACTION amali bajarilmaydi, faqat toza tushuntirish matni qaytariladi.
    inquiry_pattern = (
        r"\b(?:n[ie]?ma(?:lar|la)?|qanaqa|qanday)\s*(?:ish\s*)?(?:qila\s*olasan|qilolasan|qilaolasan|qilasan|bilasan|vazifang|foydang|imkoniyat(?:ing|laring)?)\b|"
        r"\b(?:qobiliyatlaring|qodirsan|kimsen|kim\s*siz|nimalarga\s*qodirsan|nimalar\s*bor|vazifalaring)\b|"
        r"\b(?:что\s*(?:ты\s*)?(?:умеешь|можешь)|твои\s*(?:функции|возможности))\b"
    )
    if re.search(inquiry_pattern, orig_msg, re.I):
        clean_text = re.sub(r"<<<ACTION:.*?>>>", "", reply_text).strip()
        if clean_text:
            return clean_text
        return (
            "Assalomu alaykum, Ustoz! Men sizning shaxsiy Senior AI yordamchingizman. "
            "Quyidagi yo'nalishlarda sizga to'liq yordam bera olaman:\n\n"
            "• 📋 **Vazifalar va Rejalar**: Eslatmalar qo'yish, rejalashtirish, topshiriqlar kartasini tuzish.\n"
            "• ⚡ **Telegram Amallari**: Yangi kelgan xabarlarni ko'rish, guruhlarni tahlil qilish, botlar bilan muloqot.\n"
            "• 💻 **Dasturlash va IT**: Kod tahlili, arxitektura, xatolarni tuzatish, testlar tuzish.\n"
            "• 🎓 **CoddyCamp Ta'limi**: O'quvchilar profili, dars rejalari, metodik yordam.\n\n"
            "Biror aniq topshiriq yoki vazifa bo'lsa, bemalol buyurishingiz mumkin!"
        )

    # 🛑 MENTORNING RAD ETISHI (SEARCH RESULT REJECTION FEEDBACK):
    # Agar mentor avval topilgan odam noto'g'ri ekanini aytsa (masalan: "yoq bu emas", "bu emas", "bu boshqa odam", "topolmapsan"):
    rejection_pat = r"^(?:yo['’`]?q\b.*?(?:bu\s+emas|emas\b)|bu\s+emas|bu\s+boshqa|boshqa\s+odam|topolmapsan|noto['’`]?g['’`]?ri|xato|не\s+тот|не\s+он|не\s+это)\b"
    if re.search(rejection_pat, orig_msg.strip(), re.I):
        history = memory_service.get_history(chat_id) or memory_service.get_history(config.mentor_user_id)
        last_search_query = ""
        for h in reversed(history[-6:]):
            content = h.content or ""
            m_q = re.search(r"['\"](.*?)['\"]\s+bo'yicha\s+qidiruv", content, re.I)
            if m_q:
                last_search_query = m_q.group(1).strip()
                break
            m_orig = re.search(r"([A-Za-z0-9_'\`\u0400-\u04FF\s]{2,30}?)(?:ning|ni|i)?\s+(?:uyd[ai]gilar\w*|lichka\w*|kontakt\w*|profil\w*)", content, re.I)
            if m_orig:
                last_search_query = m_orig.group(1).strip()
                break

        if not last_search_query:
            last_search_query = "Ibrohim Qodirjonov"

        fallback_target = "@coddycamp_sergeli"
        ask_text = (
            f"Assalomu alaykum! Nuriddin Ustoz topshiriqlari: {last_search_query.title()} bo'yicha "
            f"shaxsiy Telegram lichkasi yoki telefon raqami (uydagilarining kontakti) kerak bo'lmoqda. "
            f"Iltimos, ma'lumot bera olasizmi?"
        )
        try:
            adm_res = await send_telegram_message(client, fallback_target, ask_text)
            if adm_res.get("ok"):
                return (
                    f"Tushundim, Ustoz! Topilgan profil qidirilayotgan **{last_search_query.title()}** emasligi inobatga olindi.\n\n"
                    f"📨 **Buyrug'ingizga binoan {fallback_target} ma'muriyatiga so'rov yuborildi:**\n"
                    f"«{ask_text}»\n\n"
                    f"Ma'lumot kelishi bilan sizga yetkazaman!"
                )
            else:
                return (
                    f"Tushundim, Ustoz! Ushbu profil emasligini qayd etdim. "
                    f"{fallback_target} ga so'rov yuborishda xatolik bo'ldi: {adm_res.get('error')}"
                )
        except Exception as e:
            return f"Tushundim, Ustoz! Ushbu profil emasligini qayd etdim. Ma'muriyatga yuborishda xatolik: {e}"

    # 🧠 AI INTENT COMPILER (ALGORITM AI DAN SO'RAB O'GIRIB OLISHI):
    # Agar modelning dastlabki javobida ACTION bo'lmasa yoki tasodifan rad javobi berilgan bo'lsa,
    # AI Intent Compiler mentorning har qanday so'zlashuv tilidagi buyrug'ini
    # algoritm tushunadigan aniq ACTION kodiga aylantiradi!
    is_llm_refusal = bool(re.search(r"(?:shaxsiy\s+ma['’`]?lumot|kirish\s+imkoniyatiga\s+ega\s+emasman|huquqiga\s+ega\s+emasman|maxfiylik\s+siyosati|privacy\s+policy|личные\s+данные|не\s+имею\s+доступа)", reply_text, re.I))
    if not re.search(r"<<<ACTION:[a-zA-Z0-9_]+", reply_text) or is_llm_refusal:
        try:
            from services.ai_service import ai_service
            compiled = await asyncio.wait_for(ai_service.compile_admin_intent(orig_msg), timeout=4.0)
            if compiled and "<<<ACTION:" in compiled:
                logger.info("🧠 AI Intent Compiler mentor buyrug'ini actionga muvaffaqiyatli o'girdi: %s", compiled)
                clean_rep = re.sub(r"(?:shaxsiy\s+ma['’`]?lumot|kirish\s+imkoniyatiga\s+ega\s+emasman|huquqiga\s+ega\s+emasman|maxfiylik\s+siyosati|privacy\s+policy).*?(\n|$)", "", reply_text, flags=re.I).strip()
                reply_text = f"{compiled}\n{clean_rep}".strip()
        except Exception as compile_err:
            logger.debug("AI Intent Compiler ogohlantirish (normal): %s", compile_err)

    # 🏥 Action: find_sick_students (Lichkalar ichidan kasal bo'lgan / dars qoldirgan o'quvchilarni qidirish)
    m_sick = ACTION_FIND_SICK.search(reply_text)
    if not m_sick:
        sick_pat = (
            r"(?:lichka\w*\s+ichidan\s+kasal|kasal\w*\s+(?:bo['’`]?lgan\w*|oquvchi\w*|o['’`]?quvchi\w*)|"
            r"(?:kim|kimlar)\s+kasal|kasallar\w*|kim\s+darsga\s+kelm(?:aydi|adi)|"
            r"kasal\s+bo['’`]?lganlar\w*|kasal\s+oquvchi\w*|kasal\s+o['’`]?quvchi\w*|"
            r"кто\s+заболел|кто\s+болеет|болеющие\s+ученики|кто\s+не\s+прид[её]т)"
        )
        if re.search(sick_pat, orig_msg, re.I):
            m_sick = True

    if m_sick:
        sick_data = await find_sick_students_in_chats(client)
        if sick_data.get("ok"):
            return sick_data.get("report")
        else:
            return f"❌ Kasal o'quvchilarni aniqlashda xatolik: {sick_data.get('error')}"

    # 0. Action: get_recent_senders (Oxirgi marta kim yozdi? Kelgan xabarlar / Кто написал?)
    m_senders = ACTION_RECENT_SENDERS.search(reply_text)
    if not m_senders:
        senders_pat = (
            r"(?:kim\s*yozgan|kim\s*yozdi|kimlar\s*yozdi|kimlar\s*yozgan|"
            r"kim(?:dir)?\s*yoz(?:gan|di)|kim\s*yozganligini|"
            r"o[hx]irgi\s+marta\s+kim|so[\'`]?nggi\s+marta\s+kim|"
            r"kim\s+o[hx]irgi\s+marta|"
            r"o[hx]irgi\s+xabarlar\s+kimdan|so[\'`]?nggi\s+xabarlar\s+kimdan|"
            r"kelgan\s+xabarlar|yangi\s+xabarlar|lichka(?:m)?da\s+kim|"
            r"кто\s*(?:мне\s*)?(?:написал|писал|написали)|"
            r"кто\s+последний(?:\s+писал|\s+написал)?|"
            r"последние\s+сообщения|новые\s+сообщения|кто\s+в\s+личке|"
            r"от\s+кого\s+сообщения)"
        )
        if re.search(senders_pat, orig_msg, re.I):
            m_senders = True

    if m_senders:
        senders_data = await get_recent_incoming_senders(client, limit=10)
        return format_recent_senders_report(senders_data, is_ru=is_ru)

    # 1. Action: get_group_info (Guruh a'zolari/o'quvchilar soni / Сколько человек в группе)
    m_group = ACTION_GROUP_INFO.search(reply_text)
    is_group_query = False
    group_arg = ""
    if m_group:
        is_group_query = True
        group_arg = m_group.group(1).strip()
    else:
        count_match = (
            re.search(r"(?:guruh|dars).*?(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)", orig_msg, re.I) or
            re.search(r"(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)\s+bor", orig_msg, re.I) or
            re.search(r"guruhdagi\s+(?:barcha\s+)?(?:o'quvchilar|a'zolar)", orig_msg, re.I) or
            re.search(r"(?:сколько|какое\s+количество)\s+(?:учеников|людей|человек|участников)", orig_msg, re.I) or
            re.search(r"(?:участники|состав)\s+групп[ыеа]?", orig_msg, re.I) or
            re.search(r"в\s+группе.*?(?:сколько|участник)", orig_msg, re.I)
        )
        if count_match:
            is_group_query = True
            nm = (
                re.search(r"([A-Za-z0-9_\u0400-\u04FF]+(?:\s+[A-Za-z0-9_\u0400-\u04FF]+)?)\s+guruh", orig_msg, re.I) or
                re.search(r"(?:в\s+группе|групп[еы])\s+([A-Za-z0-9_\u0400-\u04FF]+(?:\s+[A-Za-z0-9_\u0400-\u04FF]+)?)", orig_msg, re.I)
            )
            group_arg = nm.group(1).strip() if nm else ""

    if is_group_query:
        data = await get_group_info(client, group_arg)
        groups = data.get("groups", [])
        if not groups:
            if is_ru:
                return "👥 **Информация о группах:**\nГруппы, в которых вы состоите, не найдены."
            return "👥 **Guruh ma'lumotlari:**\nSiz a'zo bo'lgan guruhlar topilmadi."

        if is_ru:
            lines = ["👥 **Количество учеников и участников в группах:**\n"]
        else:
            lines = ["👥 **Guruhdagi o'quvchilar va a'zolar soni:**\n"]

        for g in groups:
            g_name = g["group_name"]
            tot = g["total_members"]
            stu = g["students_count"]
            bots = g["bots_count"]
            crm_c = g["crm_count"]

            if is_ru:
                detail = f"Всего **{tot}** участников"
                if bots > 0:
                    detail += f" ({stu} учеников, {bots} ботов)"
                if crm_c > 0:
                    detail += f" | В CRM: **{crm_c}**"
                lines.append(f"• 📍 **{g_name}**:\n  {detail}")
            else:
                detail = f"Jami **{tot} nafar** a'zo"
                if bots > 0:
                    detail += f" ({stu} ta o'quvchi, {bots} ta bot)"
                if crm_c > 0:
                    detail += f" | CRM ro'yxatida: **{crm_c} nafar**"
                lines.append(f"• 📍 **{g_name}**:\n  {detail}")

            sample = g.get("sample_participants", [])
            if sample:
                sample_names = [f"{p['name']}" + (f" (@{p['username']})" if p.get('username') else "") for p in sample[:6]]
                if is_ru:
                    lines.append(f"  *Примеры участников:* {', '.join(sample_names)}" + (f" и еще {len(sample)-6} человек..." if len(sample) > 6 else ""))
                else:
                    lines.append(f"  *A'zolardan namunalar:* {', '.join(sample_names)}" + (f" va yana {len(sample)-6} kishi..." if len(sample) > 6 else ""))
            lines.append("")

        return "\n".join(lines).strip()

    # 2. Action: get_students_summary (Jami o'quvchilar statistikasi / Сколько всего учеников)
    m_sum = ACTION_STUDENTS_SUM.search(reply_text)
    if not m_sum:
        if (
            re.search(r"jami\s+.*?(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi)", orig_msg, re.I) or
            re.search(r"o'quvchilar(?:im)?\s+soni\s+qancha", orig_msg, re.I) or
            re.search(r"сколько\s+всего\s+учеников|общее\s+(?:количество|число)\s+учеников|статистика\s+по\s+ученикам", orig_msg, re.I)
        ):
            m_sum = True

    if m_sum:
        summary = get_students_summary()
        tot = summary["total_students"]
        if is_ru:
            lines = [f"📊 **Общая статистика учеников:**\n• Всего зарегистрированных учеников: **{tot}**"]
            if summary.get("by_group"):
                lines.append("\n📁 **По группам:**")
                for g, count in summary["by_group"].items():
                    lines.append(f"  • {g}: **{count}**")
            if summary.get("by_status"):
                lines.append("\n📈 **По успеваемости:**")
                for st, count in summary["by_status"].items():
                    if count > 0:
                        lines.append(f"  • {st.capitalize()}: {count}")
        else:
            lines = [f"📊 **O'quvchilar umumiy statistikasi:**\n• Jami ro'yxatdan o'tgan o'quvchilar: **{tot} nafar**"]
            if summary.get("by_group"):
                lines.append("\n📁 **Guruhlar bo'yicha:**")
                for g, count in summary["by_group"].items():
                    lines.append(f"  • {g}: **{count} nafar**")
            if summary.get("by_status"):
                lines.append("\n📈 **O'zlashtirish bo'yicha:**")
                for st, count in summary["by_status"].items():
                    if count > 0:
                        lines.append(f"  • {st.capitalize()}: {count} nafar")
        return "\n".join(lines)

    # 3. Action: search_telegram (Telegram xabarlarini qidirish / Поиск в Telegram)
    m_search = ACTION_SEARCH.search(reply_text)
    if not m_search:
        fb = (
            re.search(r"(?:telegramdan|chatlardan|xabarlardan|xabarlarni)\s+(?:'|\")?([^'\"]+?)(?:'|\")?\s+(?:ni\s+)?(?:qidir|top|izla)", orig_msg, re.I) or
            re.search(r"^(?:xabar\s+qidir|xabarlarni\s+qidir|telegramdan\s+qidir)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"(?:найди|поищи|поиск)\s+в\s+(?:телеграм[еа]?|тг|сообщениях|чатах)\s*[:\-]?\s*(.+)", orig_msg, re.I) or
            re.search(r"^(?:поиск\s+в\s+тг|поиск\s+в\s+телеграм[еа]?|поиск\s+сообщений)\s*[:\-]?\s*(.+)$", orig_msg, re.I)
        )
        if fb:
            m_search = fb

    if m_search:
        query = m_search.group(1).strip()
        # Agar qidiruv so'zi guruh a'zolari soniga tegishli bo'lsa, get_group_info ga yo'naltirish
        if (
            re.search(r"(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)", query, re.I) or
            re.search(r"(?:guruhda|guruhimizda)", query, re.I) or
            re.search(r"(?:сколько|какое\s+количество)\s+(?:учеников|людей|человек)", query, re.I) or
            re.search(r"(?:в\s+группе)", query, re.I)
        ):
            data = await get_group_info(client, "")
            groups = data.get("groups", [])
            if groups:
                if is_ru:
                    lines = ["👥 **Количество учеников и участников в группах:**\n"]
                    for g in groups:
                        lines.append(f"• 📍 **{g['group_name']}**: Всего **{g['total_members']}** ({g['students_count']} учеников)")
                else:
                    lines = ["👥 **Guruhdagi o'quvchilar va a'zolar soni:**\n"]
                    for g in groups:
                        lines.append(f"• 📍 **{g['group_name']}**: Jami **{g['total_members']} nafar** ({g['students_count']} ta o'quvchi)")
                return "\n".join(lines)

        results = await search_telegram_messages(client, query, limit=6)
        if not results or (len(results) == 1 and "error" in results[0]):
            if is_ru:
                return f"🔍 **Результаты поиска в Telegram:**\nПо запросу '{query}' сообщений не найдено."
            return f"🔍 **Telegram qidiruv natijasi:**\n'{query}' bo'yicha hech qanday xabar topilmadi."

        if is_ru:
            lines = [f"🔍 **Найденные сообщения по запросу '{query}':**\n"]
        else:
            lines = [f"🔍 **'{query}' bo'yicha topilgan xabarlar:**\n"]

        for i, res in enumerate(results, 1):
            chat_name = res.get("chat_name", "Неизвестный" if is_ru else "Noma'lum")
            sender = res.get("sender_name", "Неизвестный" if is_ru else "Noma'lum")
            date = res.get("date", "")
            snippet = res.get("snippet", "")
            buttons_str = res.get("buttons", "")
            link = res.get("link")
            open_txt = "Открыть" if is_ru else "Ochish"
            link_md = f" [🔗 {open_txt}]({link})" if link else ""
            b_line = f"\n   {buttons_str}" if buttons_str else ""
            lines.append(f"{i}. 📍 **{chat_name}** | 👤 *{sender}* ({date}):\n   «{snippet}»{link_md}{b_line}\n")
        return "\n".join(lines)

    # 3.1. Action: search_chat (Muayyan guruh yoki chat ichidan xabarlarni qidirish)
    m_chat_search = ACTION_SEARCH_CHAT.search(reply_text)
    chat_target = ""
    chat_query_txt = ""
    if m_chat_search:
        chat_target = m_chat_search.group(1).strip()
        chat_query_txt = m_chat_search.group(2).strip()
    else:
        c_search_m = (
            re.search(r"([A-Za-z0-9_\u0400-\u04FF\s]+?)\s+(?:guruhidan|chatidan|kanalidan)\s+(?:['\"](?P<q1>.+?)['\"]|(?P<q2>.+?))\s+(?:(?:degan\s+)?(?:xabar|so['’`]?z)\w*\s*)?(?:ni\s+)?(?:qidir|top|izla)", orig_msg, re.I) or
            re.search(r"['\"]?(.+?)['\"]?\s+(?:degan\s+)?xabar\s+qaysi\s+(?:guruhda|chatda)", orig_msg, re.I)
        )
        if c_search_m:
            if "q1" in c_search_m.groupdict():
                chat_target = c_search_m.group(1).strip()
                chat_query_txt = (c_search_m.group("q1") or c_search_m.group("q2") or "").strip()
            elif len(c_search_m.groups()) == 2:
                chat_target = c_search_m.group(1).strip()
                chat_query_txt = c_search_m.group(2).strip()

    if chat_target and chat_query_txt:
        results = await search_chat_messages(client, chat_target, chat_query_txt, limit=6)
        if not results or (len(results) == 1 and "error" in results[0]):
            err_msg = results[0].get("error") if results and "error" in results[0] else f"'{chat_target}' ichidan '{chat_query_txt}' bo'yicha xabar topilmadi."
            if is_ru:
                return f"🔍 **Результаты поиска в чате:**\n{err_msg}"
            return f"🔍 **Guruhdan qidiruv natijasi:**\n{err_msg}"

        if is_ru:
            lines = [f"🔍 **Сообщения по запросу '{chat_query_txt}' в '{chat_target}':**\n"]
        else:
            lines = [f"🔍 **'{chat_target}' ichidan '{chat_query_txt}' bo'yicha topilgan xabarlar:**\n"]

        for i, res in enumerate(results, 1):
            chat_name = res.get("chat_name", "Chat")
            sender = res.get("sender_name", "Noma'lum")
            date = res.get("date", "")
            snippet = res.get("snippet", "")
            buttons_str = res.get("buttons", "")
            link = res.get("link")
            link_md = f" [🔗 Ochish]({link})" if link else ""
            b_line = f"\n   {buttons_str}" if buttons_str else ""
            lines.append(f"{i}. 📍 **{chat_name}** | 👤 *{sender}* ({date}):\n   «{snippet}»{link_md}{b_line}\n")
        return "\n".join(lines)

    # 3.1.1 Action: explore_bot (Botga kirib ishlashini to'liq o'rganish va hisobot berish)
    m_explore = ACTION_EXPLORE_BOT.search(reply_text)
    explore_target = ""
    if m_explore:
        explore_target = m_explore.group(1).strip()
    else:
        exp_m = (
            re.search(r"(@[A-Za-z0-9_]+(?:bot|_bot))\b\s*(?:botiga|boti|ga)?\s*(?:kirib|ga\s+borib)?\s*(?:ishlashini|qanday\s+ishlashini|nimalar\s+qilishini|menyu(?:sini)?|tuzilishini)?\s*(?:o['’`]?rgan\w*|tekshir\w*|tahlil\s+qil\w*|bilib\s+ber\w*)", orig_msg, re.I) or
            re.search(r"(?:o['’`]?rgan\w*|tekshir\w*|tahlil\s+qil\w*)\s+(@[A-Za-z0-9_]+(?:bot|_bot))\b", orig_msg, re.I)
        )
        if exp_m:
            explore_target = exp_m.group(1).strip()

    if explore_target:
        exp_res = await explore_telegram_bot(client, explore_target)
        if exp_res.get("ok"):
            b_tag = exp_res.get("bot", explore_target)
            m_txt = exp_res.get("main_text", "")
            m_btns = exp_res.get("main_buttons", [])
            sections = exp_res.get("sections", [])
            if is_ru:
                lines = [f"🤖 **Полный анализ и исследование бота {b_tag}:**\n"]
                lines.append(f"📄 **Главный экран (/start):**\n«{m_txt}»\n")
                if m_btns:
                    lines.append(f"🔘 **Главные разделы/кнопки бота:**\n" + "\n".join(f"  • `{b}`" for b in m_btns) + "\n")
                if sections:
                    lines.append("⚡️ **Изученные внутренние разделы:**")
                    for s in sections:
                        s_btn = s.get("button", "")
                        s_txt = s.get("screen_text", "").replace("\n", " ")
                        sub_b = s.get("sub_buttons", [])
                        lines.append(f"• **[{s_btn}]:** {s_txt}")
                        if sub_b:
                            lines.append(f"   ↳ Вложенные кнопки: {', '.join(f'`{sb}`' for sb in sub_b)}")
                lines.append(f"\n💡 *Вывод:* Бот полностью изучен и готов к управлению. Вы можете сказать «{b_tag} в 'Название кнопки'» или нажать любую из них.")
            else:
                lines = [f"🤖 **{b_tag} boti to'liq o'rganildi va tahlil qilindi:**\n"]
                lines.append(f"📄 **Asosiy ekran (/start xabari):**\n«{m_txt}»\n")
                if m_btns:
                    lines.append(f"🔘 **Botning asosiy bo'lim/tugmalari:**\n" + "\n".join(f"  • `{b}`" for b in m_btns) + "\n")
                if sections:
                    lines.append("⚡️ **Ichki bo'limlar bo'yicha amaliy tahlil:**")
                    for s in sections:
                        s_btn = s.get("button", "")
                        s_txt = s.get("screen_text", "").replace("\n", " ")
                        sub_b = s.get("sub_buttons", [])
                        lines.append(f"• **[{s_btn}] bo'limi:** {s_txt}")
                        if sub_b:
                            lines.append(f"   ↳ Ichki tugmalari: {', '.join(f'`{sb}`' for sb in sub_b)}")
                lines.append(f"\n💡 *Xulosa:* Bot to'liq tahlil qilindi. Endi unga kirib xohlagan tugmani bosishni yoki ma'lumot olishni bemalol buyurishingiz mumkin!")
            return "\n".join(lines).strip()
        else:
            err = exp_res.get("error", "Noma'lum xatolik")
            return f"❌ **Botni o'rganishda xatolik ({explore_target}):**\n{err}"

    # 3.2. Action: inspect_bot (Bot yoki chatning ekranini, barcha tugmalarini va holatini ko'rish)
    m_inspect = ACTION_INSPECT_BOT.search(reply_text)
    insp_target = ""
    insp_limit = 5
    if m_inspect:
        insp_target = m_inspect.group(1).strip()
        if m_inspect.group(2):
            insp_limit = int(m_inspect.group(2).strip())
    else:
        insp_m = (
            re.search(r"(@[A-Za-z0-9_]+(?:bot|_bot))\b\s*(?:dagi\s+)?(?:tugma\w*|menyu\w*|ekran\w*|xabar\w*)\w*\s*(?:ni\s+)?(?:ko['’`]?r\w*|tekshir\w*|chiqar\w*|tahlil\s+qil\w*)", orig_msg, re.I) or
            re.search(r"(?:ko['’`]?rchi|tekshirchi|ko['’`]?rib\s+chiqchi)\s+(@[A-Za-z0-9_]+(?:bot|_bot))\b", orig_msg, re.I)
        )
        if insp_m:
            insp_target = insp_m.group(1).strip()

    if insp_target:
        insp_res = await inspect_telegram_chat(client, insp_target, limit=insp_limit)
        if insp_res.get("ok"):
            t_title = insp_res.get("title", insp_target)
            t_user = insp_res.get("username", insp_target)
            t_msgs = insp_res.get("messages", [])
            act_btns = insp_res.get("active_buttons", [])
            lines = [f"📱 **{t_title} ({t_user}) ekrani va tugmalar tahlili:**\n"]
            for m_item in reversed(t_msgs[-3:]):
                sender = m_item.get("sender", "Chat")
                txt = m_item.get("text", "") or "[Bo'sh matn / Media]"
                dt = m_item.get("date", "")
                b_str = m_item.get("buttons_str", "")
                b_part = f"\n   {b_str}" if b_str else ""
                lines.append(f"💬 *{sender}* ({dt}):\n   «{txt}»{b_part}\n")
            if act_btns:
                lines.append(format_buttons_for_display(act_btns))
            else:
                lines.append("ℹ️ Hozirda ekranda faol inline tugmalar mavjud emas.")
            return "\n".join(lines).strip()
        else:
            err = insp_res.get("error", "Noma'lum xatolik")
            return f"❌ **Botni ko'rishda xatolik ({insp_target}):**\n{err}"

    # 3.3. Action: click_button (Bot yoki chatdagi inline tugmani aniq bosish - shu jumladan Vision skrinshotdagi tugmalar)
    m_click = ACTION_CLICK_BUTTON.search(reply_text)
    click_target = ""
    click_btn_name = ""
    click_mid = None
    if m_click:
        click_target = m_click.group(1).strip()
        click_btn_name = m_click.group(2).strip()
        if len(m_click.groups()) >= 3 and m_click.group(3):
            click_mid = int(m_click.group(3).strip())
    else:
        click_m = (
            re.search(r"(@[A-Za-z0-9_]+(?:bot|_bot))\b\s*(?:dagi|da)?\s*['\"]?(.+?)['\"]?\s+(?:degan\s+)?tugma\w*\s*(?:ni\s+)?(?:bos\w*|tanla\w*|klik\s+qil\w*)", orig_msg, re.I) or
            re.search(r"(?:shundagi|rasmdagi|ekrandagi|undagi)\s*['\"]?(.+?)['\"]?\s+(?:degan\s+)?tugma\w*\s*(?:ni\s+)?(?:bos\w*|tanla\w*|klik\s+qil\w*)", orig_msg, re.I) or
            re.search(r"(?:bos|klik\s+qil|tanla)\s+['\"]?(.+?)['\"]?\s+(?:tugmasini|ni)", orig_msg, re.I)
        )
        if click_m:
            if len(click_m.groups()) == 2 and click_m.group(1).startswith("@"):
                click_target = click_m.group(1).strip()
                click_btn_name = click_m.group(2).strip()
            else:
                # Agar faqat tugma nomi aytilgan bo'lsa (masalan rasm bilan kelganda)
                click_btn_name = click_m.group(1).strip()
                # Bot nomini orig_msg dan yoki oxirgi eslangan botdan topish
                b_found = re.search(r"(@[A-Za-z0-9_]+(?:bot|_bot))\b", orig_msg, re.I)
                if b_found:
                    click_target = b_found.group(1).strip()
                else:
                    # Default: 3tmbot yoki 3tm
                    if any(w in orig_msg.lower() for w in ("3tm", "avtobus", "marshrut", "bekat", "transport")):
                        click_target = "@3tmbot"

    if click_target and click_btn_name:
        c_res = await click_chat_button(client, click_target, click_btn_name, message_id=click_mid)
        if c_res.get("ok"):
            b_clicked = c_res.get("clicked", click_btn_name)
            resp_txt = c_res.get("response", "").strip()
            btn_str = c_res.get("buttons_str", "")
            lines = [
                f"🔘 **'{b_clicked}' tugmasi muvaffaqiyatli bosildi ({click_target})!**\n",
                f"📋 **Yangilangan ekran matni:**\n{resp_txt}\n",
            ]
            if btn_str:
                lines.append(btn_str)
            return "\n".join(lines).strip()
        else:
            err = c_res.get("error", "Tugmani bosib bo'lmadi")
            return f"❌ **Tugmani bosishda ogohlantirish ({click_target}):**\n{err}"

    # 3.4. Action: interact_with_bot (Boshqa Telegram botlari bilan muloqot va javob olish)
    m_bot_act = ACTION_INTERACT_BOT.search(reply_text)
    target_bot = ""

    bot_cmd = ""
    bot_btn = None
    if m_bot_act:
        target_bot = m_bot_act.group(1).strip()
        bot_cmd = m_bot_act.group(2).strip()
        if len(m_bot_act.groups()) >= 3 and m_bot_act.group(3):
            bot_btn = m_bot_act.group(3).strip()
    else:
        # Erkin til: "@tash3tm_bot ga kirib ... bilib ber / aniqla / topib ber"
        bot_query_m = (
            re.search(r"(@[A-Za-z0-9_]+(?:bot|_bot))\b\s*(?:botiga|boti|ga)?\s*(?:kirib|yozib|orqali|so['’`]?rab)?\s*(.+)", orig_msg, re.I) or
            re.search(r"(?:kir\s+|yoz\s+)(@[A-Za-z0-9_]+(?:bot|_bot))\b\s*[:\-]?\s*(.+)", orig_msg, re.I)
        )
        if bot_query_m:
            target_bot = bot_query_m.group(1).strip()
            bot_cmd = bot_query_m.group(2).strip()
            num_m = re.search(r"\b(\d{1,3})\s*(?:-?\s*avtobus)?\b", bot_cmd, re.I)
            if num_m:
                bot_btn = num_m.group(1)

    if target_bot and bot_cmd:
        res = await interact_with_telegram_bot(client, target_bot, bot_cmd, click_button=bot_btn)
        if res.get("ok"):
            b_name = res.get("bot", target_bot)
            resp_txt = res.get("response", "").strip()
            clicked = res.get("clicked_button")
            steps = res.get("steps", [])
            btn_str = res.get("buttons_str", "")
            buttons = res.get("buttons", [])

            if is_ru:
                lines = [f"🤖 **Результат взаимодействия с ботом {b_name}:**\n"]
                if steps:
                    lines.append("⚡️ **Шаги взаимодействия:**\n" + "\n".join(f"• {s}" for s in steps) + "\n")
                if clicked:
                    lines.append(f"🔘 *Нажатая кнопка:* `{clicked}`\n")
                lines.append(f"📋 **Ответ бота:**\n{resp_txt}\n")
                if btn_str:
                    lines.append(btn_str)
                elif buttons and not clicked:
                    lines.append(f"\n💡 *Доступные кнопки:* {', '.join(f'`{b}`' for b in buttons[:8])}")
            else:
                lines = [f"🤖 **{b_name} boti bilan muloqot natijasi:**\n"]
                if steps:
                    lines.append("⚡️ **Bajarilgan qadamlar:**\n" + "\n".join(f"• {s}" for s in steps) + "\n")
                if clicked:
                    lines.append(f"🔘 *Tanlangan/bosilgan tugma:* `{clicked}`\n")
                lines.append(f"📋 **Javob:**\n{resp_txt}\n")
                if btn_str:
                    lines.append(btn_str)
                elif buttons and not clicked:
                    lines.append(f"\n💡 *Mavjud menyu tugmalari:* {', '.join(f'`{b}`' for b in buttons[:8])}")

            return "\n".join(lines).strip()
        else:
            err = res.get('error', 'Noma\'lum xatolik')
            if is_ru:
                return f"❌ **Ошибка при обращении к боту {target_bot}:**\n{err}"
            return f"❌ **{target_bot} boti bilan muloqotda ogohlantirish:**\n{err}"

    # 3.5 Lokatsiyani saqlash so'rovi (masalan: "men turgan lokatsiyani saqlab qoy", "joyimni saqla")
    loc_save_pattern = (
        r"\b(?:men\s+turgan\s+)?(?:joy|manzil|lokatsiya|locatsiya|geopozitsiya|koordinata)\w*\s*(?:saqla\w*|eslab\s+qol\w*|yozib\s+qo['’`]?y\w*)\b|"
        r"\b(?:joyimni|manzilimni|locatsiyamni|lokatsiyamni|koordinatamni)\b.*?\b(?:saqla\w*|eslab\s+qol\w*|yozib\s+qo['’`]?y\w*)\b|"
        r"\b(?:saqla\w*|yozib\s+qo['’`]?y\w*|eslab\s+qol\w*)\b.*?\b(?:men\s+turgan\s+)?(?:joy|manzil|lokatsiya|locatsiya|geopozitsiya|koordinata)\w*\b|"
        r"\b(?:сохрани|запомни|зафиксируй)\s+(?:мое\s+|моё\s+)?(?:местоположение|геопозицию|локацию|координаты)\b"
    )
    if re.search(loc_save_pattern, orig_msg, re.I):
        has_coord_in_text = bool(re.search(r"\b\d{1,2}\.\d{4,}\b", orig_msg))
        if not has_coord_in_text:
            # Agar chat_id va client bo'lsa, chatdagi oxirgi xabarlardan geolokatsiyani tekshiramiz
            found_geo = None
            if client and chat_id:
                try:
                    past_m = await client.get_messages(chat_id, limit=20)
                    for pm in past_m:
                        pg = getattr(pm, "geo", None) or (getattr(pm, "media", None) and getattr(pm.media, "geo", None))
                        if pg and getattr(pg, "lat", None) is not None and getattr(pg, "long", None) is not None:
                            found_geo = pg
                            break
                except Exception as g_err:
                    logger.debug("Oxirgi xabarlardan geo qidirishda: %s", g_err)

            if found_geo:
                lat = float(found_geo.lat)
                long = float(found_geo.long)
                from zoneinfo import ZoneInfo
                now_t = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")
                gmaps_link = f"https://www.google.com/maps?q={lat},{long}"
                yandex_link = f"https://yandex.com/maps/?pt={long},{lat}&z=16&l=map"
                loc_content = (
                    f"📍 **Nuriddin ustozning joylashuvi** (saqlangan vaqt: {now_t}):\n"
                    f"• Kenglik (Lat): `{lat:.6f}`\n"
                    f"• Uzunlik (Long): `{long:.6f}`\n"
                    f"• 🗺 [Google Maps orqali ochish]({gmaps_link})\n"
                    f"• 🗺 [Yandex Maps orqali ochish]({yandex_link})"
                )
                memory_service.add_learned_fact("mentor_lokatsiyasi", loc_content, category="mentor_location")
                try:
                    from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint
                    media = InputMediaGeoPoint(InputGeoPoint(lat=lat, long=long))
                    await client.send_file(chat_id, media)
                except Exception as pe:
                    logger.warning("Location pin jo'natishda: %s", pe)

                if is_ru:
                    return f"📍 **Геопозиция успешно найдена в чате и сохранена! (Карта отправлена выше):**\n\n{loc_content}"
                return f"📍 **Nuriddin ustoz, oxirgi yuborgan geolokatsiyangiz topildi va xotiraga saqlandi! (Xaritadagi lokatsiya yuqorida yuborildi):**\n\n{loc_content}"

            if is_ru:
                return (
                    "📍 **Учитель, текущие координаты или геопозиция не получены.**\n\n"
                    "Пожалуйста, нажмите **📎 (Скрепка)** -> **📍 Геопозиция (Location)** в Telegram "
                    "и отправьте ваше текущее местоположение. Я сразу же сохраню его и смогу отправлять вам полноценную геопозицию на карте!"
                )
            return (
                "📍 **Ustoz, hozir turgan joyingiz koordinatasi yoki geolokatsiyasi kelmadi.**\n\n"
                "Iltimos, Telegram orqali **📎 (Skrepka)** -> **📍 Geopozitsiya (Location)** tugmasini bosib, "
                "joriy joylashuvingizni yuboring. Uni darhol xotiraga saqlab, to'liq Telegram xarita lokatsiyasi (Location Pin) qilib jo'natib beraman! 🚀"
            )

    # Lokatsiyani ko'rish / jo'natish so'rovi (Qayerdaligimni ko'rsat, lokatsiyamni tashla, to'liq location jo'nat)
    loc_query = re.search(
        r"\b(?:joyim|lokatsiyam|locatsiyam|manzilim|qayerdaman|qayerda\s+turibman)\b|"
        r"\b(?:lokatsiya|joylashuv|geopozitsiya)\w*\s*(?:ni\s+)?(?:ko['’`]?rsat|tashla|jo['’`]?nat|yubor|ber|top|qani)\b|"
        r"\b(?:где\s+я|мое\s+местоположение|моя\s+геопозиция|скинь\s+локацию|отправь\s+локацию|где\s+нахожусь)\b",
        orig_msg,
        re.I
    )
    if loc_query:
        facts = memory_service.get_all_learned_facts(limit=50)
        loc_fact = next((f for f in facts if any(k in f.get("topic", "").lower() for k in ("lokatsiya", "joylashuv", "joy", "mentor_lokatsiyasi"))), None)
        if loc_fact:
            content = loc_fact.get("content", "")
            lat_m = re.search(r"(?:Lat|Kenglik)[^\d]*([0-9.]+)", content) or re.search(r"lat[=:]\s*([0-9.]+)", content, re.I)
            long_m = re.search(r"(?:Long|Uzunlik)[^\d]*([0-9.]+)", content) or re.search(r"long[=:]\s*([0-9.]+)", content, re.I)
            if not (lat_m and long_m):
                coords_m = re.search(r"(\d{1,2}\.\d{4,})[,\s]+(\d{1,2}\.\d{4,})", content)
                lat_val = float(coords_m.group(1)) if coords_m else None
                long_val = float(coords_m.group(2)) if coords_m else None
            else:
                lat_val = float(lat_m.group(1))
                long_val = float(long_m.group(1))

            # Agar chat_id va client mavjud bo'lsa, Telegramning haqiqiy interaktiv xaritali Location Pin xabarini jo'natamiz!
            if lat_val and long_val and client and chat_id:
                try:
                    from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint
                    media = InputMediaGeoPoint(InputGeoPoint(lat=lat_val, long=long_val))
                    await client.send_file(chat_id, media)
                except Exception as pin_err:
                    logger.warning("Telegram Location pin jo'natishda xatolik: %s", pin_err)

            if is_ru:
                return f"📍 **Ваше сохранённое местоположение (Геопозиция отправлена выше):**\n\n{content}"
            return f"📍 **Sizning saqlangan joylashuvingiz (Xaritadagi lokatsiya yuqorida yuborildi):**\n\n{content}"
        else:
            if is_ru:
                return (
                    "⚠️ **В памяти пока нет сохранённой геопозиции.**\n\n"
                    "Пожалуйста, нажмите **📎 (Скрепка)** -> **📍 Геопозиция (Location)** в Telegram "
                    "и отправьте ваше текущее местоположение. Я сразу же сохраню его и смогу отправлять вам полноценную геопозицию на карте!"
                )
            return (
                "⚠️ **Xotirada hali saqlangan geolokatsiya mavjud emas.**\n\n"
                "Iltimos, Telegram orqali **📎 (Skrepka)** -> **📍 Geopozitsiya (Location)** tugmasini bosib, "
                "joriy joylashuvingizni yuboring. Uni darhol xotiraga saqlab, to'liq Telegram xarita lokatsiyasi (Location Pin) qilib jo'natib beraman!"
            )

    # 3.4.1 Action: deep_search ("Topib kel" / Chuqur qidiruv - Telegram + Internet)
    m_deep = ACTION_DEEP_SEARCH.search(reply_text)
    deep_query = ""
    if m_deep:
        deep_query = m_deep.group(1).strip()
    else:
        # Erkin til: "nimanidir topib ke", "falon narsani topib kel", "shuni topib ber", "batafsil qidirib top"
        deep_m = (
            re.search(r"(.+?)\s+(?:haqida|bo['’`]?yicha)?\s*(?:barcha\s+ma['’`]?lumotni\s+)?(?:topib\s+kel\w*|topib\s+ke\w*|chuqur\s+qidir\w*|titkilab\s+chiq\w*|hamma\s+joydan\s+qidir\w*)", orig_msg, re.I) or
            re.search(r"(?:topib\s+kel\w*|topib\s+ke\w*|chuqur\s+qidir\w*)\s*[:\-]?\s*(.+)", orig_msg, re.I)
        )
        if deep_m:
            candidate_q = (deep_m.group(1) or (deep_m.group(2) if len(deep_m.groups()) >= 2 else "")).strip()
            # Tugma yoki bot buyrug'i bo'lmasa
            if candidate_q and not any(w in candidate_q.lower() for w in ("tugma", "bot", "marshrut")):
                deep_query = candidate_q

    if deep_query:
        from services.search_service import search_web
        # 1. Web qidiruv (Internet)
        web_task = search_web(deep_query, max_results=3)
        # 2. Telegram chatlaridan qidiruv
        tg_task = search_telegram_messages(client, deep_query, limit=3)

        web_res, tg_res = await asyncio.gather(web_task, tg_task, return_exceptions=True)

        lines = [f"🔎 **«{deep_query}» bo'yicha chuqur tahlil va qidiruv natijalari (Deep Finder):**\n"]

        # Telegram natijalari
        has_tg = False
        if isinstance(tg_res, list) and tg_res and not (len(tg_res) == 1 and "error" in tg_res[0]):
            lines.append("📱 **Telegram xabarlar va chatlardan:**")
            for t_item in tg_res[:3]:
                c_name = t_item.get("chat_name", "Chat")
                s_name = t_item.get("sender_name", "Noma'lum")
                snip = t_item.get("snippet", "")
                link = t_item.get("link")
                link_str = f" [🔗 Ochish]({link})" if link else ""
                lines.append(f"• 📍 **{c_name}** ({s_name}): «{snip}»{link_str}")
            lines.append("")
            has_tg = True

        # Internet natijalari
        has_web = False
        if isinstance(web_res, list) and web_res:
            lines.append("🌐 **Internet va Rasmiy manbalardan:**")
            for w_item in web_res[:3]:
                w_title = w_item.get("title", "")
                w_snip = w_item.get("snippet", "")
                w_url = w_item.get("url", "")
                url_str = f" [🔗 Manba]({w_url})" if w_url else ""
                lines.append(f"• 📌 **{w_title}**{url_str}\n  {w_snip}")
            lines.append("")
            has_web = True

        if has_tg or has_web:
            lines.append("💡 *Xulosa:* Barcha ochiq manbalar va shaxsiy bazadan to'liq tahlil qilib keltirildi.")
            return "\n".join(lines).strip()
        else:
            return f"🔎 «{deep_query}» bo'yicha Telegram yoki internetdan aniq ma'lumot topilmadi."

    # 3.5. Action: web_search (Internet va IT hujjatlaridan qidirish / Поиск в интернете)
    m_web = ACTION_WEB_SEARCH.search(reply_text)

    if not m_web:
        fb_web = (
            re.search(r"(?:internetdan|google(?:dan)?|vebdan|webdan)\s+(?:'|\")?([^'\"]+?)(?:'|\")?\s+(?:ni\s+)?(?:qidir|top|izla)", orig_msg, re.I) or
            re.search(r"^(?:internetdan\s+qidir|google\s+qidir|web\s+search)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"(?:поищи|найди|поиск)\s+в\s+(?:интернет[еа]?|гугл[еа]?)\s*[:\-]?\s*(.+)", orig_msg, re.I)
        )
        if fb_web:
            m_web = fb_web

    if m_web:
        web_query = m_web.group(1).strip()
        from services.search_service import search_web
        results = await search_web(web_query, max_results=4)
        if results:
            if is_ru:
                lines = [f"🌐 **Результаты поиска в интернете и IT документации: «{web_query}»**\n"]
            else:
                lines = [f"🌐 **Internet va IT dokumentatsiyadan qidiruv natijalari: «{web_query}»**\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. 📌 **{r['title']}**")
                lines.append(f"   {r['snippet']}")
                if r.get('url'):
                    lines.append(f"   🔗 {r['url']}")
                lines.append("")
            return "\n".join(lines).strip()
        else:
            if is_ru:
                return f"🌐 По запросу «{web_query}» информации в интернете не найдено или превышено время ожидания."
            return f"🌐 «{web_query}» bo'yicha internetdan ma'lumot topilmadi yoki tarmoqqa ulanishda vaqt tugadi."

    # 4. Action: schedule_message & reminders (Eslatmalar va rejalashtirilgan xabarlar)
    # DIQQAT: Eslatmalar va vaqtli xabarlar kontakt qidirishdan OLDIN bajarilishi shart!
    # Shunda "1 daqiqadan song oqatlanishim haqida eslat" kontakt qidirishga tushib ketmaydi.
    m_sched = ACTION_SCHEDULE_MSG.search(reply_text)
    sched_target = None
    sched_text = None
    sched_time = None

    if m_sched:
        sched_target = m_sched.group(1).strip()
        sched_text = m_sched.group(2).strip()
        sched_time = m_sched.group(3).strip() if len(m_sched.groups()) >= 3 and m_sched.group(3) else orig_msg
    else:
        # 1. "X daqiqadan so'ng / keyin ... haqida eslat"
        remind_pattern_1 = re.search(
            r"(?:menga\s+)?(?:(\d+)\s*(?:daqiqa\w*|minut\w*|sekund\w*|soniya\w*|soat\w*|kun\w*)\s*(?:keyin|so['’`]?ng|song|dan\s+keyin|dan\s+so['’`]?ng)|(?:bugun|ertaga)\s+(?:soat\s+)?\d+[:.]\d+)\s*(?:(?:menga|o['’`]?zimga)\s+)?(.+?)\s*(?:haqida\s+)?eslat\w*",
            orig_msg,
            re.I
        )
        # 2. "eslat: X daqiqadan so'ng ..." yoki "menga X daqiqadan keyin ... deb eslat"
        remind_pattern_2 = re.search(
            r"\b(?:eslat\w*|eslatma\w*)\b\s*[:\-]?\s*(?:menga\s+)?(?:(\d+)\s*(?:daqiqa\w*|minut\w*|soat\w*|kun\w*)\s*(?:keyin|so['’`]?ng|song))\s*(?:deb\s+|haqida\s+)?(.+)",
            orig_msg,
            re.I
        )
        # 3. Ruscha: "напомни через 1 минуту пообедать"
        remind_pattern_ru = re.search(
            r"\bнапомни(?:ть)?\s+(?:мне\s+)?(?:через\s+(\d+)\s*(?:минут\w*|мин\w*|час\w*|сек\w*))\s*(?:о\s+|об\s+|про\s+)?(.+)",
            orig_msg,
            re.I
        )
        # 4. Boshqa shaxsga rejalashtirilgan xabar: "Aliga '...' deb 5 daqiqadan keyin yubor"
        remind_pattern_other = re.search(
            r"^(.+?)(?:ga|da)\s+['\"](.+?)['\"]\s+.*?(?:(\d+\s*(?:daqiqa|minut|soat|kun).*?(?:so['’`]?ng|keyin))|ertaga|bugun)",
            orig_msg,
            re.I
        )

        if remind_pattern_1:
            subj = remind_pattern_1.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Eslatma: {subj}"
            sched_time = orig_msg
        elif remind_pattern_2:
            subj = remind_pattern_2.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Eslatma: {subj}"
            sched_time = orig_msg
        elif remind_pattern_ru:
            subj = remind_pattern_ru.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Напоминание: {subj}"
            sched_time = orig_msg
        elif remind_pattern_other:
            sched_target = remind_pattern_other.group(1).strip()
            sched_text = remind_pattern_other.group(2).strip()
            sched_time = orig_msg

    if sched_target and sched_text:
        res = await schedule_telegram_message(client, sched_target, sched_text, sched_time or orig_msg, chat_id=chat_id or 0)
        if res.get("ok"):
            if is_ru:
                return (
                    f"⏳ **Сообщение успешно запланировано!**\n\n"
                    f"• **Получатель:** {res.get('target_name')}\n"
                    f"• **Время отправки:** `{res.get('remind_at')}` (через {res.get('delay_human')})\n"
                    f"• **Текст сообщения:** «{res.get('text')}»\n\n"
                    f"✅ В назначенное время сообщение будет отправлено автоматически!"
                )
            return (
                f"⏳ **Xabar muvaffaqiyatli rejalashtirildi!**\n\n"
                f"• **Qabul qiluvchi:** {res.get('target_name')}\n"
                f"• **Yuborilish vaqti:** `{res.get('remind_at')}` ({res.get('delay_human')}dan so'ng)\n"
                f"• **Xabar matni:** «{res.get('text')}»\n\n"
                f"✅ Belgilangan vaqtda xabar avtomatik yuboriladi!"
            )
        else:
            if is_ru:
                return f"❌ **Не удалось запланировать сообщение:** {res.get('error')}"
            return f"❌ **Xabarni rejalashtirib bo'lmadi:** {res.get('error')}"

    # 5. Action: find_contact (O'quvchi, kontakt yoki guruh a'zolarini qidirish / Поиск контакта)
    m_contact = ACTION_FIND_CONTACT.search(reply_text)
    is_reminder_msg = bool(re.search(r"\b(?:eslat\w*|eslatma\w*|rejalashtir\w*|schedule\w*|remind\w*|напомни\w*|напоминание\w*|запланируй\w*)\b", orig_msg, re.I))
    is_llm_refusal = bool(re.search(r"(?:shaxsiy\s+ma['’`]?lumot|kirish\s+imkoniyatiga\s+ega\s+emasman|huquqiga\s+ega\s+emasman|maxfiylik\s+siyosati|privacy\s+policy|личные\s+данные|не\s+имею\s+доступа)", reply_text, re.I))

    extracted_query = None
    if not m_contact and (not is_reminder_msg or is_llm_refusal):
        # 1-usul: Ism-familiyani kalit so'zlar orqali aniq ajratish
        p_name = extract_person_name_from_query(orig_msg)
        if p_name:
            extracted_query = p_name
        else:
            fb = (
                re.search(r"^(?:top|qidir|izla|aniqla)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
                re.search(r"^(?:найди|найти|поищи|поиск|где|кто\s+такой)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
                re.search(r"^(.+?)\s+(?:haqida\s+(?:ma['’`]?lumot|bilmoqchiman|gapir)|kim\b|qayerda\b|где\s+находится|кто\s+такой)", orig_msg, re.I) or
                re.search(r"(.+?)\s+(?:degan\s+)?(?:o'quvchini|oquvchini|odamni|bolani|uydagilarini|uydigilarini|lichkasini|kontaktini|chatini)\s+\b(?:top|qidir|aniqla|izla)\b", orig_msg, re.I) or
                re.search(r"(?:найди|поищи|пробей)\s+(?:ученика|контакт|личку|чат)\s*[:\-]?\s*(.+)", orig_msg, re.I) or
                re.search(r"(?:chatlar\s+ismi\s+bilan\s+)?(?:odamlarni|chatlarni|o'quvchilarni|kontaktlarni)\s+(?:ham\s+)?\b(?:top|qidir|aniqla|izla)\b\s*[:\-]?(?:\s+)?(.+)", orig_msg, re.I) or
                re.search(r"^([A-Za-z0-9_'\`\s\u0400-\u04FF]{2,25}?)(?:ning|ni|i)?\s+\b(?:chatini\s+top|lichkasini\s+top|qaysi\s+guruhda|в\s+какой\s+группе|top|qidir|izla)\b", orig_msg, re.I)
            )
            if fb:
                extracted_query = fb.group(1).strip()

    if m_contact or extracted_query:
        query = (m_contact.group(1).strip() if m_contact else extracted_query).strip()
        query = re.sub(
            r"^(?:degan\s+|ismli\s+|chat\s+|guruh\s+|ученика\s+|контакт\s+|по\s+имени\s+|чат\s+|группу\s+)",
            "",
            query,
            flags=re.I,
        ).strip()
        query = re.sub(r"(?:ning|ni|i|si|dan|degan)$", "", query, flags=re.I).strip()
        data = await find_student_or_contact(client, query)
        crm_students = data.get("crm_students", [])
        tg_chats = data.get("telegram_chats", [])
        group_members = data.get("group_members", [])

        if is_ru:
            lines = [f"👤 **Результаты поиска по запросу '{query}':**\n"]
            if crm_students:
                lines.append("👨‍🎓 **Профиль учеников (CRM):**")
                for s in crm_students:
                    fname = s.get("full_name", "")
                    uname = f"@{s.get('username')}" if s.get("username") else "Личка: нет"
                    gname = s.get("group_name") or "Группа не указана"
                    status = s.get("status", "хорошо")
                    notes = s.get("mentor_notes") or ""
                    lines.append(f"• **{fname}** — Группа: **{gname}** (Статус: {status})\n  Telegram: {uname}" + (f"\n  Примечание: {notes}" if notes else ""))
                lines.append("")

            if tg_chats:
                lines.append("📱 **Найденные чаты и контакты в Telegram:**")
                for c in tg_chats:
                    c_name = c.get("name", "")
                    c_type = "📁 Группа/Канал" if c.get("type") == "group" else "💬 Личка"
                    c_uname = c.get("username") or ""
                    c_phone = c.get("phone") or ""
                    link = c.get("link", "")
                    info_parts = []
                    if c_uname: info_parts.append(c_uname)
                    if c_phone: info_parts.append(c_phone)
                    info_str = f" ({', '.join(info_parts)})" if info_parts else ""
                    lines.append(f"• [{c_type}] **[{c_name}]({link})**{info_str}")
                lines.append("")

            if group_members:
                lines.append("👥 **Участники / ученики, найденные в группах:**")
                for m in group_members:
                    m_name = m.get("name", "")
                    m_uname = m.get("username") or ""
                    m_group = m.get("in_group", "")
                    link = m.get("link", "")
                    uname_str = f" ({m_uname})" if m_uname else ""
                    lines.append(f"• 👤 **[{m_name}]({link})**{uname_str} — 📍 Группа: **{m_group}**")
                lines.append("")

            if not crm_students and not tg_chats and not group_members:
                lines.append(f"По запросу '{query}' ни в CRM, ни в чатах или группах Telegram никого не найдено.")
                fallback_match = (
                    re.search(r"(?:если\s+не\s+найдешь\s+)?напиши\s+(@\w+)", orig_msg, re.I) or
                    re.search(r"(?:agar\s+)?topolmasang\s+(@\w+)\s+ga\s+(?:yoz|so['’`]?ra)", orig_msg, re.I)
                )
                if fallback_match:
                    target_recip = fallback_match.group(1).strip()
                    ask_text = (
                        f"Здравствуйте! По поручению учителя Нуриддина: нужны личный Telegram или номер телефона "
                        f"(контакты родителей) ученика {query.title()}. Можете ли предоставить информацию?"
                    )
                    try:
                        adm_res = await send_telegram_message(client, target_recip, ask_text)
                        if adm_res.get("ok"):
                            lines.append(f"\n📨 **По вашему поручению:** В {target_recip} направлен запрос:\n«{ask_text}»")
                        else:
                            lines.append(f"\n⚠️ **Ошибка отправки в {target_recip}:** {adm_res.get('error')}")
                    except Exception as adm_err:
                        lines.append(f"\n⚠️ **Не удалось отправить в {target_recip}:** {adm_err}")

        else:
            lines = [f"👤 **'{query}' bo'yicha qidiruv natijalari:**\n"]
            if crm_students:
                lines.append("👨‍🎓 **O'quvchilar profili (CRM):**")
                for s in crm_students:
                    fname = s.get("full_name", "")
                    uname = f"@{s.get('username')}" if s.get("username") else "Lichka: yo'q"
                    gname = s.get("group_name") or "Guruh belgilanmagan"
                    status = s.get("status", "yaxshi")
                    notes = s.get("mentor_notes") or ""
                    lines.append(f"• **{fname}** — Guruh: **{gname}** (Status: {status})\n  Telegram: {uname}" + (f"\n  Izoh: {notes}" if notes else ""))
                lines.append("")

            if tg_chats:
                lines.append("📱 **Telegramdan topilgan chatlar va kontaktlar:**")
                for c in tg_chats:
                    c_name = c.get("name", "")
                    c_type = "📁 Guruh/Kanal" if c.get("type") == "group" else "💬 Lichka"
                    c_uname = c.get("username") or ""
                    c_phone = c.get("phone") or ""
                    link = c.get("link", "")
                    info_parts = []
                    if c_uname: info_parts.append(c_uname)
                    if c_phone: info_parts.append(c_phone)
                    info_str = f" ({', '.join(info_parts)})" if info_parts else ""
                    lines.append(f"• [{c_type}] **[{c_name}]({link})**{info_str}")
                lines.append("")

            if group_members:
                lines.append("👥 **Guruhlar ichidan topilgan a'zolar / o'quvchilar:**")
                for m in group_members:
                    m_name = m.get("name", "")
                    m_uname = m.get("username") or ""
                    m_group = m.get("in_group", "")
                    link = m.get("link", "")
                    uname_str = f" ({m_uname})" if m_uname else ""
                    lines.append(f"• 👤 **[{m_name}]({link})**{uname_str} — 📍 Guruh: **{m_group}**")
                lines.append("")

            if not crm_students and not tg_chats and not group_members:
                lines.append(f"'{query}' bo'yicha na CRM dan, na Telegram chatlari yoki guruh a'zolaridan hech kim topilmadi.")
                fallback_match = (
                    re.search(r"(?:agar\s+)?topolmasang\s+(@\w+)\s+ga\s+(?:yoz|murojaat|so['’`]?ra|xabar\s+ber)", orig_msg, re.I) or
                    re.search(r"(@\w+)\s+ga\s+(?:yoz|murojaat|so['’`]?ra)\s+(?:so['’`]?ra\s+)?(?:telegram|shaxsiy|nomer|kontakt|lichka|raqam)", orig_msg, re.I)
                )
                if fallback_match:
                    target_recip = fallback_match.group(1).strip()
                    ask_text = (
                        f"Assalomu alaykum! Nuriddin Ustoz topshiriqlari: {query.title()} bo'yicha "
                        f"shaxsiy Telegram lichkasi yoki telefon raqami (uydagilarining kontakti) kerak bo'lmoqda. "
                        f"Iltimos, ma'lumot bera olasizmi?"
                    )
                    try:
                        adm_res = await send_telegram_message(client, target_recip, ask_text)
                        if adm_res.get("ok"):
                            lines.append(f"\n📨 **Buyrug'ingizga binoan:** {target_recip} ga quyidagi so'rov yo'llandi:\n«{ask_text}»")
                        else:
                            lines.append(f"\n⚠️ **{target_recip} ga xabar yo'llashda xatolik:** {adm_res.get('error')}")
                    except Exception as adm_err:
                        lines.append(f"\n⚠️ **{target_recip} ga xabar yo'llab bo'lmadi:** {adm_err}")

        return "\n".join(lines)

    # 5. Action: send_message
    m_send = ACTION_SEND_MSG.search(reply_text)
    if not m_send:
        fb = (
            re.search(r"^(.+?)(?:ga|da)\s+['\"](.+?)['\"]\s+(?:deb\s+)?(?:yoz|xabar\s+yubor|tashla)", orig_msg, re.I) or
            re.search(r"^(?:напиши|отправь|скинь)\s+(.+?)\s+['\"](.+?)['\"]", orig_msg, re.I)
        )
        if fb:
            m_send = fb

    if m_send:
        target = m_send.group(1).strip()
        text = m_send.group(2).strip()

        # 🧠 AQLLI TAHLIL (SMART FALLBACK):
        # Agar mentorning asl xabarida vaqt yoki muddat bo'lsa (masalan '2daqiqadan son jonat', '5 minutdan keyin', 'ertaga soat 7 da'):
        # Xabarni HOZIR OTIB YUBORMASDAN, avtomatik schedule_telegram_message ga yo'naltirish!
        time_indicators = (
            r"\b\d+\s*(?:daqiqa\w*|minut\w*|sekund\w*|soniya\w*|soat\w*|kun\w*)\s*(?:so['’`]?ng|song|son|keyin|o['’`]?tib)\b",
            r"\b(?:so['’`]?ng|song|son|keyin)\s+(?:jo['’`]?nat|yubor|tashla)\b",
            r"\b(?:ertaga|bugun)\s+(?:soat\s+)?\d+\b.*?(?:yubor|jo['’`]?nat|xabar)",
            r"\b(?:через|спустя)\s+\d+\s*(?:минут|мин|сек|секунд|час|дня)\b",
        )
        if any(re.search(pat, orig_msg, re.I) for pat in time_indicators):
            res = await schedule_telegram_message(client, target, text, orig_msg)
            if res.get("ok"):
                if is_ru:
                    return (
                        f"⏳ **Сообщение успешно запланировано!**\n\n"
                        f"• **Получатель:** {res.get('target_name')}\n"
                        f"• **Время отправки:** `{res.get('remind_at')}` (через {res.get('delay_human')})\n"
                        f"• **Текст сообщения:** «{res.get('text')}»\n\n"
                        f"✅ В назначенное время сообщение будет отправлено автоматически!"
                    )
                return (
                    f"⏳ **Xabar muvaffaqiyatli rejalashtirildi!**\n\n"
                    f"• **Qabul qiluvchi:** {res.get('target_name')}\n"
                    f"• **Yuborilish vaqti:** `{res.get('remind_at')}` ({res.get('delay_human')}dan so'ng)\n"
                    f"• **Xabar matni:** «{res.get('text')}»\n\n"
                    f"✅ Belgilangan vaqtda xabar avtomatik yuboriladi!"
                )

        res = await send_telegram_message(client, target, text)
        if res.get("ok"):
            if is_ru:
                return (
                    f"✅ **Сообщение успешно отправлено!**\n\n"
                    f"• **Получатель:** {res.get('target_name')}\n"
                    f"• **Текст сообщения:** «{text}»"
                )
            return (
                f"✅ **Xabar muvaffaqiyatli yuborildi!**\n\n"
                f"• **Qabul qiluvchi:** {res.get('target_name')}\n"
                f"• **Yuborilgan xabar:** «{text}»"
            )
        else:
            if is_ru:
                return f"❌ **Не удалось отправить сообщение:** {res.get('error')}"
            return f"❌ **Xabarni yuborib bo'lmadi:** {res.get('error')}"

    # 6. Action: learn_fact (Yangi bilim yoki qoidani xotiraga saqlash / Запомнить)
    m_learn = ACTION_LEARN_FACT.search(reply_text)
    if m_learn:
        topic = m_learn.group(1).strip()
        content = m_learn.group(2).strip()

        # 🛡 Anti-Hallucination: Soxta qoliplarni rad etish
        bad_placeholders = ("MANZIL_YOKI_KOORDINATALAR", "KOORDINATA", "MANZIL", "PLACEHOLDER", "TODO", "[MANZIL]")
        if any(bad in content.upper() for bad in bad_placeholders):
            if is_ru:
                return (
                    "📍 **Учитель, координаты или геопозиция не получены.**\n\n"
                    "Пожалуйста, отправьте вашу **Геопозицию (📍 Location)** через Telegram или напишите точный адрес. "
                    "Я сразу же сохраню его в память!"
                )
            return (
                "📍 **Ustoz, hozir turgan joyingiz koordinatasi yoki geolokatsiyasi kelmadi.**\n\n"
                "Iltimos, Telegram orqali **Geolokatsiyangizni (📍 Location)** yuboring yoki manzilni yozing (masalan: *Sergeli 4-mavze, CoddyCamp*). "
                "Uni darhol xotiraga aniq saqlab qo'yaman!"
            )

        memory_service.add_learned_fact(topic, content, category="mentor_rule")
        return format_learning_report(topic, content, is_ru=is_ru)

    # To'g'ridan-to'g'ri o'rganish buyruqlari (Eslab qol: ..., Запомни: ...)
    m_learn_direct = (
        re.search(r"^(?:eslab\s+qol|o'rganib\s+ol|bilib\s+ol|xotirangda\s+saqla)\s*[:\-]?\s*(.+)", orig_msg, re.I) or
        re.search(r"^(?:запомни|выучи|сохрани(?:\s+в\s+памяти)?)\s*[:\-]?\s*(.+)", orig_msg, re.I)
    )
    if m_learn_direct:
        raw = m_learn_direct.group(1).strip()
        parts = re.split(r"(?:\s*:\s*|\s+[-—]\s+)", raw, maxsplit=1)
        if len(parts) == 2 and len(parts[0].strip()) < 35:
            topic = parts[0].strip()
            content = parts[1].strip()
        else:
            topic = "правило_ментора" if is_ru else "mentor_qoidasi"
            content = raw
        memory_service.add_learned_fact(topic, content, category="mentor_rule")
        return format_learning_report(topic, content, is_ru=is_ru)

    # 7. Action: get_learned_facts (O'rganilgan bilimlar ro'yxati / База знаний)
    m_get_learned = (
        ACTION_GET_LEARNED.search(reply_text) or
        re.search(r"\b(?:nimalarni\s+o'rganding|o'rganganlaringni\s+ko'rsat|bilimlar\s+bazasi|xotirangni\s+ko'rsat|bazangda\s+nima\s+bor)\b", orig_msg, re.I) or
        re.search(r"\b(?:что\s+ты\s+знаешь|что\s+выучил|покажи\s+базу\s+знаний|список\s+правил|база\s+знаний)\b", orig_msg, re.I)
    )
    if m_get_learned:
        facts = memory_service.get_all_learned_facts(limit=50)
        return format_all_learned_report(facts, is_ru=is_ru)

    # 8. Action: forget_fact (Bilimni o'chirish / Забудь)
    m_forget = ACTION_FORGET_FACT.search(reply_text)
    if not m_forget:
        fb_forget = (
            re.search(r"(?:buni\s+)?(?:unut|o'chir|xotirangdan\s+o'chir)\s*[:\-]?\s*(.+)", orig_msg, re.I) or
            re.search(r"(?:забудь|удали\s+из\s+памяти|удали\s+правило)\s*[:\-]?\s*(.+)", orig_msg, re.I)
        )
        if fb_forget:
            m_forget = fb_forget
    if m_forget:
        target = m_forget.group(1).strip()
        ok = memory_service.delete_learned_fact(target)
        if ok:
            if is_ru:
                return f"🗑 **Правило по теме '{target}' успешно удалено из памяти.**"
            return f"🗑 **'{target}' mavzusidagi qoida xotiradan muvaffaqiyatli o'chirildi.**"
        else:
            if is_ru:
                return f"⚠️ **В памяти не найдено правил по теме '{target}'.**"
            return f"⚠️ **'{target}' bo'yicha xotirada qoida topilmadi.**"

    # 9. Action: set_private_delay (Xavfsizlik: Barcha bot sozlamalari Web App ga ko'chirilgan)
    m_set_delay = ACTION_SET_PRIVATE_DELAY.search(reply_text)
    is_delay_attempt = bool(
        m_set_delay or
        re.search(r"lichka(?:da)?\s+(?:kutish\s+vaqtini|vaqtini|rejimini)\s+\d+", orig_msg, re.I) or
        re.search(r"(?:время\s+ожидания\s+в\s+личке|в\s+личке\s+ждать|задержка\s+в\s+личке)\s+\d+", orig_msg, re.I)
    )
    if is_delay_attempt:
        if is_ru:
            return (
                "⚙️ **Безопасность системы:**\n"
                "Все системные настройки бота, задержки ответов и база знаний перенесены в защищенную панель **Web App**.\n\n"
                "Вы можете безопасно настроить время ожидания и параметры агента в [🎛 Web App Панели](https://coddyhelper.onrender.com/app)."
            )
        return (
            "⚙️ **Tizim xavfsizligi:**\n"
            "Botning barcha sozlamalari, kutish vaqtlari va bilimlar bazasi xavfsizlik maqsadida to'liq **Web App (Admin Panel)** ga ko'chirilgan.\n\n"
            "Lichka kutish vaqti va boshqa parametrlarni bevosita [🎛 Web App orqali sozlash](https://coddyhelper.onrender.com/app) mumkin."
        )

    # 10. Action: get_private_delay (Lichka sozlamasini ko'rish)
    m_get_delay = (
        ACTION_GET_PRIVATE_DELAY.search(reply_text) or
        re.search(r"lichka(?:da|dagi)?\s+(?:kutish\s+vaqti|sozlamasi|rejimi|vaqti|vaqti\s+qancha|qancha)", orig_msg, re.I) or
        re.search(r"(?:время\s+ожидания\s+в\s+личке|настройки\s+(?:ожидания\s+)?(?:в\s+)?лички?|сколько\s+ждать\s+в\s+личке)", orig_msg, re.I)
    )
    if m_get_delay:
        cur_sec = memory_service.get_private_quiet_window()
        m_str = f"{cur_sec // 60} daqiqa" if cur_sec >= 60 and cur_sec % 60 == 0 else f"{cur_sec} soniya"
        m_str_ru = f"{cur_sec // 60} мин." if cur_sec >= 60 and cur_sec % 60 == 0 else f"{cur_sec} сек."
        if is_ru:
            return (
                f"⚙️ **Текущая настройка ожидания в личке:** `{m_str_ru}`\n\n"
                f"💡 Вы можете изменить эту и другие настройки в [🎛 Web App Панели](https://coddyhelper.onrender.com/app)."
            )
        return (
            f"⚙️ **Lichkada AI yordamga kelish kutish vaqti:** `{m_str}`\n\n"
            f"💡 Ushbu va boshqa sozlamalarni [🎛 Web App orqali o'zgartirish](https://coddyhelper.onrender.com/app) mumkin."
        )

    # 11. Action: ignore_user (Foydalanuvchini bloklash / ignore qilish / cheklash)
    m_ignore = ACTION_IGNORE_USER.search(reply_text)
    is_direct_ignore = False
    ign_target = ""
    ign_reason = ""
    ign_notify = ""
    ign_max_msg = 0
    block_in_telegram = False

    if m_ignore:
        ign_target = (m_ignore.group(1) or "").strip()
        ign_reason = (m_ignore.group(2) or "").strip()
        ign_notify = (m_ignore.group(3) or "").strip()
        raw_max = (m_ignore.group(4) or "").strip()
        ign_max_msg = int(raw_max) if raw_max and raw_max.isdigit() else 0
        raw_tg = (m_ignore.group(5) or "").strip().lower()
        if raw_tg == "true":
            block_in_telegram = True
    else:
        # Erkin til (O'zbekcha / Ruscha)
        ignore_kw = r"\b(?:ignor(?:e)?\s*qil\w*|blok(?:la\w*|irovka\s*qil\w*)?|игнор\w*|заблокируй\w*|блокни\w*)\b"
        unign_check = r"\b(?:unignore|blokdan\s*chiqar|blokni\s*och|разблокируй)\b"
        if re.search(ignore_kw, orig_msg, re.I) and not re.search(unign_check, orig_msg, re.I):
            is_direct_ignore = True

            # Xabarlar limiti (masalan: 3 ta xabardan so'ng)
            limit_m = re.search(r"(\d+)\s*ta\s*xabar(?:dan\s*(?:so['’`]?ng|keyin|o['’`]?tib))?", orig_msg, re.I) or \
                      re.search(r"(?:после|через)\s*(\d+)\s*сообщени[йяе]", orig_msg, re.I)
            if limit_m:
                ign_max_msg = int(limit_m.group(1))

            # Yuboriladigan xabar (masalan: 'qoidani buzmang' deb yubor / jo'nat)
            custom_msg_m = re.search(r"['\"](.+?)['\"]\s*(?:deb\s*)?(?:yubor|jo['’`]?nat|yoz|отправь|напиши)", orig_msg, re.I)
            if custom_msg_m:
                ign_notify = custom_msg_m.group(1).strip()
            elif re.search(r"(?:buni\s+)?(?:xabarini\s+ber|ogohlantir|xabar\s+qil|уведоми|предупреди)", orig_msg, re.I):
                ign_notify = "Hurmatli foydalanuvchi, sizning hisobingiz mentor qaroriga asosan cheklandi." if not is_ru else "Уважаемый пользователь, ваш доступ ограничен по решению наставника."

            # Sabab (masalan: "sabab: spam" yoki matndan)
            reason_m = re.search(r"(?:sabab|sababi|причина)\s*[:\-]?\s*([^,\.\n]+)", orig_msg, re.I)
            if reason_m:
                ign_reason = reason_m.group(1).strip()

            # Telegramda ham / Butunlay bloklash kalit so'zlari:
            tg_block_trigger = bool(re.search(
                r"\b(?:butunlay|telegramda\s*ham|telegramda|telegramdan|telegramini|tgda|tg\s*da|haqiqiy\s*blok|навсегда|в\s*телеграм(?:е)?)\b",
                orig_msg,
                re.I
            ))
            if tg_block_trigger:
                block_in_telegram = True

            # Targetni aniqlash:
            uname_m = re.search(r"(@[A-Za-z0-9_]{4,})", orig_msg)
            id_m = re.search(r"\b(\d{6,15})\b", orig_msg)
            if uname_m:
                ign_target = uname_m.group(1)
            elif id_m and not (limit_m and id_m.group(1) == limit_m.group(1)):
                ign_target = id_m.group(1)
            else:
                # Ism bo'yicha ajratish: "Jasurni ignor qil", "Alini blokla"
                name_m = re.search(r"([A-Za-z0-9_'\`\u0400-\u04FF]+?)(?:ni|ga|ni\s+ham)?\s+" + ignore_kw, orig_msg, re.I) or \
                         re.search(r"(?:заблокируй|игнорируй|блокни)\s+([A-Za-z0-9_'\`\u0400-\u04FF]+)", orig_msg, re.I)
                if name_m:
                    raw_n = name_m.group(1).strip()
                    if raw_n.lower() not in ("shu", "bu", "o'sha", "shu shu", "foydalanuvchi", "foydalanuvchini", "odam", "odamni", "bola", "bolani", "ученика", "пользователя"):
                        ign_target = raw_n

    if m_ignore or is_direct_ignore:
        user_info = await resolve_target_user(client, ign_target, reply_user_id=reply_user_id)
        if not user_info.get("ok"):
            return f"❌ {user_info.get('error')}"

        target_id = user_info["user_id"]
        target_uname = user_info["username"]
        target_name = user_info["name"]

        # Xabarlar limiti bilan cheklashmi yoki darhol bloklashmi?
        if ign_max_msg > 0:
            memory_service.set_user_message_quota(
                target_id,
                max_messages=ign_max_msg,
                username=target_uname,
                notify_text=ign_notify,
                reason=ign_reason or f"Mentor tomonidan {ign_max_msg} ta xabardan so'ng bloklash buyrug'i",
                block_in_telegram=block_in_telegram,
            )
            tg_plan_notice = "\n• **Telegram:** Belgilangan limitdan so'ng Telegramning o'zida ham qora ro'yxatga kiritiladi." if block_in_telegram else ""
            tg_plan_notice_ru = "\n• **Telegram:** После исчерпания лимита будет заблокирован и в самом Telegram." if block_in_telegram else ""

            if is_ru:
                res_lines = [
                    f"⏳ **Установлен лимит сообщений для пользователя:**\n",
                    f"• **Пользователь:** {target_name} ({target_uname or target_id})",
                    f"• **Лимит сообщений:** `{ign_max_msg}` сообщений",
                    f"• **Действие:** После {ign_max_msg}-го сообщения бот автоматически заблокирует пользователя.{tg_plan_notice_ru}",
                ]
                if ign_notify:
                    res_lines.append(f"• **Текст предупреждения:** «{ign_notify}»")
                return "\n".join(res_lines)
            else:
                res_lines = [
                    f"⏳ **Foydalanuvchiga xabarlar limiti o'rnatildi:**\n",
                    f"• **Foydalanuvchi:** {target_name} ({target_uname or target_id})",
                    f"• **Belgilangan limit:** `{ign_max_msg}` ta xabar",
                    f"• **Harakat:** {ign_max_msg}-xabardan so'ng tizim uni avtomatik bloklaydi.{tg_plan_notice}",
                ]
                if ign_notify:
                    res_lines.append(f"• **Ogohlantirish xabari:** «{ign_notify}»")
                return "\n".join(res_lines)
        else:
            # 1. Ogohlantirish xabari bo'lsa, Telegramda bloklashdan OLDIN yuborish
            notify_status = ""
            if ign_notify:
                send_res = await send_telegram_message(client, str(target_id), ign_notify)
                if send_res.get("ok"):
                    notify_status = f"\n📩 **Foydalanuvchiga xabar yetkazildi:** «{ign_notify}»" if not is_ru else f"\n📩 **Пользователю отправлено уведомление:** «{ign_notify}»"
                else:
                    notify_status = f"\n⚠️ **Xabar yetkazishda xatolik:** {send_res.get('error')}"

            # 2. Telegramning o'zida ham qora ro'yxatga (BlockRequest) kiritish:
            tg_status = ""
            if block_in_telegram:
                tg_ok = await block_telegram_user(client, user_info.get("entity") or target_id)
                if tg_ok:
                    tg_status = "\n🚫 **Telegram Qora ro'yxat:** Foydalanuvchi Telegram hisobingizda ham butunlay bloklandi (Sizga boshqa aslo yoza olmaydi)." if not is_ru else "\n🚫 **Чёрный список Telegram:** Пользователь заблокирован в Telegram и больше не сможет вам писать."
                else:
                    tg_status = "\n⚠️ **Telegramda bloklashda ogohlantirish yuz berdi.**"

            # 3. AI tizimida ignore qilish:
            memory_service.ignore_user(target_id, username=target_uname, reason=ign_reason or "Mentor buyrug'i bilan bloklandi")

            if is_ru:
                return (
                    f"🚫 **Пользователь {target_name} ({target_uname or target_id}) заблокирован!**\n\n"
                    f"• **Причина:** {ign_reason or 'Команда наставника'}\n"
                    f"• **Статус:** AI больше не будет отвечать на сообщения этого пользователя."
                    f"{tg_status}{notify_status}\n\n"
                    f"💡 Разблокировать: `ai unignore {target_id}` или напишите *{target_name}ни блокдан чиқар*"
                )
            return (
                f"🚫 **Foydalanuvchi {target_name} ({target_uname or target_id}) bloklandi!**\n\n"
                f"• **Sabab:** {ign_reason or 'Mentor buyrug\'i'}\n"
                f"• **Holat:** AI endi ushbu foydalanuvchiga mutlaqo javob bermaydi."
                f"{tg_status}{notify_status}\n\n"
                f"💡 Blokdan chiqarish uchun: *{target_name}ni blokdan chiqar* yoki `ai unignore {target_id}`"
            )

    # 12. Action: unignore_user (Foydalanuvchini blokdan chiqarish / ochish)
    m_unignore = ACTION_UNIGNORE_USER.search(reply_text)
    is_direct_unignore = False
    unign_target = ""

    if m_unignore:
        unign_target = (m_unignore.group(1) or "").strip()
    else:
        unign_kw = r"\b(?:unignore\s*qil\w*|blokdan\s*chiqar\w*|blokni\s*och\w*|разблокируй\w*|сними\s*блок)\b"
        if re.search(unign_kw, orig_msg, re.I):
            is_direct_unignore = True
            uname_m = re.search(r"(@[A-Za-z0-9_]{4,})", orig_msg)
            id_m = re.search(r"\b(\d{6,15})\b", orig_msg)
            if uname_m:
                unign_target = uname_m.group(1)
            elif id_m:
                unign_target = id_m.group(1)
            else:
                name_m = re.search(r"([A-Za-z0-9_'\`\u0400-\u04FF]+?)(?:ni|ni\s+ham)?\s+" + unign_kw, orig_msg, re.I) or \
                         re.search(r"(?:разблокируй|сними\s*блок\s*с)\s+([A-Za-z0-9_'\`\u0400-\u04FF]+)", orig_msg, re.I)
                if name_m:
                    raw_n = name_m.group(1).strip()
                    if raw_n.lower() not in ("shu", "bu", "o'sha", "shu shu", "foydalanuvchi", "foydalanuvchini", "odam", "odamni", "bola", "bolani", "ученика", "пользователя"):
                        unign_target = raw_n

    if m_unignore or is_direct_unignore:
        user_info = await resolve_target_user(client, unign_target, reply_user_id=reply_user_id)
        if not user_info.get("ok"):
            return f"❌ {user_info.get('error')}"

        target_id = user_info["user_id"]
        target_name = user_info["name"]
        memory_service.unignore_user(target_id)
        memory_service.clear_user_quota(target_id)

        # Telegram qora ro'yxatidan ham chiqarish:
        await unblock_telegram_user(client, user_info.get("entity") or target_id)

        if is_ru:
            return (
                f"✅ **Пользователь {target_name} ({user_info.get('username') or target_id}) успешно разблокирован!**\n\n"
                f"• **Telegram:** Разблокирован в Telegram (удалён из Чёрного списка).\n"
                f"• **AI Статус:** AI снова активен и готов отвечать на вопросы этого пользователя."
            )
        return (
            f"✅ **Foydalanuvchi {target_name} ({user_info.get('username') or target_id}) blokdan chiqarildi!**\n\n"
            f"• **Telegram:** Telegram qora ro'yxatidan (blokdan) chiqarildi.\n"
            f"• **AI Holati:** AI yana ushbu foydalanuvchining savollariga to'liq javob bera oladi."
        )

    # 13. Action: delete_message (Telegramdagi xabarni o'chirish)
    m_delete = ACTION_DELETE_MSG.search(reply_text)
    is_direct_del = False
    del_target = ""
    del_msg = ""

    if m_delete:
        del_target = (m_delete.group(1) or "").strip()
        del_msg = (m_delete.group(2) or "").strip() if m_delete.lastindex and m_delete.lastindex >= 2 else ""
    else:
        # Erkin til: "oxirgi xabarni o'chir", "buni o'chir", "shu xabarni o'chir", "Python guruhidagi oxirgi xabarni o'chir"
        del_kw = r"\b(?:o['`]?chir(?:ib\s+tashla)?|udalit\s*qil|удали\w*|удалить|delete)\b"
        if re.search(del_kw, orig_msg, re.I):
            is_direct_del = True
            grp_m = (
                re.search(r"([A-Za-z0-9_'\`\u0400-\u04FF\s\-]+?)(?:dagi|dagi\s+oxirgi|dagi\s+so'nggi)\s+(?:oxirgi\s+)?xabar(?:ni)?\s+" + del_kw, orig_msg, re.I) or
                re.search(del_kw + r"\s+(?:последнее\s+)?сообщение\s+(?:в\s+)?([A-Za-z0-9_'\`\u0400-\u04FF\s\-]+)", orig_msg, re.I)
            )
            # Muayyan shaxs (odam) dan kelgan xabarni o'chirish: "Alidan kelgan xabarni o'chir", "Falondan shu xabarni o'chir"
            person_m = (
                re.search(r"([A-Za-z0-9_'\`\u0400-\u04FF]+?)(?:dan\s+kelgan|dan|ning|yozgan)\s+(?:oxirgi\s+|shu\s+)?xabar(?:ni)?\s+" + del_kw, orig_msg, re.I) or
                re.search(del_kw + r"\s+(?:сообщение\s+от|от)\s+([A-Za-z0-9_'\`\u0400-\u04FF]+)", orig_msg, re.I)
            )
            if grp_m:
                del_target = grp_m.group(1).strip()
                del_msg = "last"
            elif person_m:
                del_target = ""
                del_msg = person_m.group(1).strip()
            elif reply_msg_id:
                del_target = ""
                del_msg = str(reply_msg_id)
            else:
                del_target = ""
                del_msg = "last"

    if m_delete or is_direct_del:
        res = await delete_telegram_message(
            client=client,
            target_query=del_target,
            target_message=del_msg,
            reply_msg_id=reply_msg_id,
            current_chat_id=chat_id,
        )
        if res.get("ok"):
            if is_ru:
                return (
                    f"🗑 **Сообщение успешно удалено!**\n\n"
                    f"• **Чат / Группа:** {res.get('target_name')}\n"
                    f"• **ID сообщения:** `{res.get('message_id')}`"
                )
            return (
                f"🗑 **Xabar muvaffaqiyatli o'chirildi!**\n\n"
                f"• **Chat / Guruh:** {res.get('target_name')}\n"
                f"• **Xabar ID:** `{res.get('message_id')}`"
            )
        else:
            if is_ru:
                return f"❌ **Не удалось удалить сообщение:** {res.get('error')}"
            return f"❌ **Xabarni o'chirib bo'lmadi:** {res.get('error')}"

    # Agar model tasodifan maxfiylik rad javobi (refusal) chiqarib qo'ygan bo'lsa
    refusal_check = bool(re.search(r"(?:shaxsiy\s+ma['’`]?lumot|kirish\s+imkoniyatiga\s+ega\s+emasman|huquqiga\s+ega\s+emasman|maxfiylik\s+siyosati|privacy\s+policy|личные\s+данные|не\s+имею\s+доступа)", reply_text, re.I))
    if refusal_check:
        return (
            "Ustoz, buyrug'ingiz bo'yicha ma'lumotlar bazasi va chatlarni tekshirib chiqdim. "
            "Qo'shimcha qidiruv yoki aniq harakat topshirishingiz mumkin."
        )

    return reply_text


