"""
services/telegram_agent_service.py
Telegram Action Agent xizmati:
Telethon mijozi orqali xabarlarni qidirish, o'quvchi va ota-onalar kontaktlarini topish,
hamda to'g'ridan-to'g'ri xabar yuborish amallarini bajaradi.
"""

import logging
import re
from datetime import datetime
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


async def search_telegram_messages(client, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Telegram barcha dialoglari bo'ylab xabarlarni global qidiradi.
    Qayerda (qaysi guruh/chatda), kim tomonidan, qachon yozilganini qaytaradi.
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

            results.append({
                "chat_name": chat_title,
                "chat_username": f"@{chat_username}" if chat_username else None,
                "chat_id": chat_id,
                "sender_name": sender_name,
                "date": date_str,
                "snippet": text_snippet,
                "link": link,
                "msg_id": msg.id,
            })
    except Exception as e:
        logger.error("Telegram xabarlarini qidirishda xatolik: %s", e)
        results.append({"error": str(e)})

    return results


async def find_student_or_contact(client, name_or_query: str) -> dict[str, Any]:
    """
    O'quvchini, uning guruhini, uydagilarini yoki shaxsiy lichkasini
    ham Student CRM bazasidan, ham Telegram dialoglaridan qidiradi.
    """
    q = (name_or_query or "").strip().lower()
    if not q:
        return {"crm_students": [], "telegram_chats": []}

    # 1. CRM bazasidan o'quvchilarni qidirish
    crm_matches = memory_service.get_students(limit=10, search=q)

    # 2. Telegram dialoglaridan qidirish
    tg_matches = []
    if client:
        try:
            dialogs = await client.get_dialogs(limit=100)
            for d in dialogs:
                d_name = (d.name or "").strip()
                d_name_lower = d_name.lower()
                entity = d.entity

                username = getattr(entity, "username", None)
                username_lower = (username or "").lower()
                phone = getattr(entity, "phone", None)

                # Qidiruv so'zi ismda, username'da yoki telefon raqamida bormi?
                matched = False
                if q in d_name_lower or (username and q in username_lower):
                    matched = True

                # Ota-ona yoki qarindosh kalit so'zlari (masalan: "Ali dada", "Akmal ota", "onasi")
                family_keywords = ["dada", "ota", "ona", "oyi", "aka", "uka", "amaki", "tog'a"]
                for kw in family_keywords:
                    if kw in q and kw in d_name_lower:
                        matched = True

                if matched:
                    is_group = d.is_group or d.is_channel
                    tg_matches.append({
                        "id": d.id,
                        "name": d_name,
                        "type": "group" if is_group else "user",
                        "username": f"@{username}" if username else None,
                        "phone": f"+{phone}" if phone else None,
                        "link": f"https://t.me/{username}" if username else f"tg://user?id={d.id}",
                    })
                    if len(tg_matches) >= 8:
                        break
        except Exception as e:
            logger.error("Telegram dialoglarini qidirishda xatolik: %s", e)

    return {
        "crm_students": crm_matches,
        "telegram_chats": tg_matches,
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
        # 1. Agar @username yoki telefon yoki to'g'ridan-to'g'ri chat ID bo'lsa
        if target.startswith("@") or target.startswith("+") or re.match(r"^-?\d+$", target):
            parse_target = int(target) if re.match(r"^-?\d+$", target) else target
            try:
                resolved_entity = await client.get_entity(parse_target)
            except Exception:
                pass

        # 2. Agar topilmasa, mavjud dialoglar orasidan nom bo'yicha qidiramiz
        if not resolved_entity:
            dialogs = await client.get_dialogs(limit=100)
            target_lower = target.lower()

            # Exact match first
            for d in dialogs:
                if (d.name or "").lower() == target_lower:
                    resolved_entity = d.entity
                    target_name = d.name
                    break

            # Partial match if not exact
            if not resolved_entity:
                for d in dialogs:
                    if target_lower in (d.name or "").lower():
                        resolved_entity = d.entity
                        target_name = d.name
                        break

        # 3. CRM dan tekshirish
        if not resolved_entity:
            students = memory_service.get_students(limit=5, search=target)
            for s in students:
                u = s.get("username", "")
                if u:
                    try:
                        resolved_entity = await client.get_entity(u)
                        target_name = s.get("full_name") or u
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
