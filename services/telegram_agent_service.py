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


def normalize_text(text: str) -> str:
    """
    Har qanday noodatiy shrift (Mathematical Bold, Italic, Script, Fraktur, Double-struck,
    Small-caps, Squared, Circled, Fullwidth) va Kirill yozuvidagi belgilarni
    standart kichik lotin harflariga o'tkazadi.
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

    return filtered.lower().strip()


def match_text(query: str, target: str) -> bool:
    """
    Shrift va bezaklardan qat'iy nazar qidiruv so'zi maqsadli matnga mos kelishini tekshiradi.
    Submatn, apostrofsiz variant va so'z/token darajasida taqqoslaydi.
    """
    q_norm = normalize_text(query)
    t_norm = normalize_text(target)
    if not q_norm or not t_norm:
        return False

    # To'g'ridan-to'g'ri submatn mosligi
    if q_norm in t_norm:
        return True

    # Tutuq belgisisiz yumshoq moslik (masalan: otkir va o'tkir)
    if q_norm.replace("'", "") in t_norm.replace("'", ""):
        return True

    # So'zlar / tokenlar bo'yicha moslik (masalan: "Ali" -> "Ali Vohidov", "Vohidov Ali")
    q_tokens = [w for w in re.split(r"[\s\W_]+", q_norm) if len(w) >= 2]
    t_tokens = [w for w in re.split(r"[\s\W_]+", t_norm) if len(w) >= 2]
    if q_tokens and all(any(qt in tt or tt in qt for tt in t_tokens) for qt in q_tokens):
        return True

    return False


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
            dialogs = await client.get_dialogs(limit=150)
            family_keywords = ["dada", "ota", "ona", "oyi", "aka", "uka", "amaki", "tog'a"]
            q_norm = normalize_text(raw_q)

            for d in dialogs:
                d_name = (d.name or "").strip()
                entity = d.entity
                username = getattr(entity, "username", None) or ""
                phone = getattr(entity, "phone", None) or ""

                matched = False
                if match_text(raw_q, d_name) or match_text(raw_q, username):
                    matched = True
                elif phone and raw_q.replace("+", "") in phone:
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
            for gd in group_dialogs_to_inspect[:12]:
                try:
                    participants = await client.get_participants(gd.entity, limit=80)
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
                            if len(group_members) >= 10:
                                break
                except Exception as pe:
                    logger.debug("Guruh a'zolarini o'qishda e'tiborsiz xatolik (%s): %s", gd.name, pe)

                if len(group_members) >= 10:
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
        # 1. Agar @username yoki telefon yoki to'g'ridan-to'g'ri chat ID bo'lsa
        if target.startswith("@") or target.startswith("+") or re.match(r"^-?\d+$", target):
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


async def get_group_info(client, group_query: str = "") -> dict[str, Any]:
    """
    Guruhdagi o'quvchilar/a'zolar soni, ismlari va ma'lumotlarini Telethon va CRM orqali aniqlaydi.
    """
    if not client:
        return {"error": "Telegram mijoz ulanmagan"}

    q = (group_query or "").strip().lower()
    generic_words = ["", "guruh", "guruhda", "guruhimizda", "guruhlar", "barcha", "hamma", "darsda"]
    is_generic = q in generic_words or any(q.startswith(w) for w in ["hamma", "barcha", "guruhlar"])

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


ACTION_GROUP_INFO = re.compile(r'<<<ACTION:get_group_info\(["\']?(.*?)["\']?\)>>>', re.IGNORECASE)
ACTION_STUDENTS_SUM = re.compile(r'<<<ACTION:get_students_summary\(\)>>>', re.IGNORECASE)
ACTION_SEARCH = re.compile(r'<<<ACTION:search_telegram\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_FIND_CONTACT = re.compile(r'<<<ACTION:find_contact\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_SEND_MSG = re.compile(r'<<<ACTION:send_message\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)


async def execute_agent_action(reply_text: str, client, orig_msg: str) -> str:
    """
    AI javobidagi maxsus harakat buyruqlarini (Action Tools) yoki
    foydalanuvchining to'g'ridan-to'g'ri Telegram amallari talablarini bajaradi.
    """
    # 1. Action: get_group_info (Guruh a'zolari/o'quvchilar soni)
    m_group = ACTION_GROUP_INFO.search(reply_text)
    is_group_query = False
    group_arg = ""
    if m_group:
        is_group_query = True
        group_arg = m_group.group(1).strip()
    else:
        count_match = re.search(r"(?:guruh|dars).*?(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)", orig_msg, re.I) or \
                      re.search(r"(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)\s+bor", orig_msg, re.I) or \
                      re.search(r"guruhdagi\s+(?:barcha\s+)?(?:o'quvchilar|a'zolar)", orig_msg, re.I)
        if count_match:
            is_group_query = True
            nm = re.search(r"([A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)?)\s+guruh", orig_msg, re.I)
            group_arg = nm.group(1).strip() if nm else ""

    if is_group_query:
        data = await get_group_info(client, group_arg)
        groups = data.get("groups", [])
        if not groups:
            return "👥 **Guruh ma'lumotlari:**\nSiz a'zo bo'lgan guruhlar topilmadi."

        lines = ["👥 **Guruhdagi o'quvchilar va a'zolar soni:**\n"]
        for g in groups:
            g_name = g["group_name"]
            tot = g["total_members"]
            stu = g["students_count"]
            bots = g["bots_count"]
            crm_c = g["crm_count"]

            detail = f"Jami **{tot} nafar** a'zo"
            if bots > 0:
                detail += f" ({stu} ta o'quvchi, {bots} ta bot)"
            if crm_c > 0:
                detail += f" | CRM ro'yxatida: **{crm_c} nafar**"

            lines.append(f"• 📍 **{g_name}**:\n  {detail}")

            sample = g.get("sample_participants", [])
            if sample:
                sample_names = [f"{p['name']}" + (f" (@{p['username']})" if p.get('username') else "") for p in sample[:6]]
                lines.append(f"  *A'zolardan namunalar:* {', '.join(sample_names)}" + (f" va yana {len(sample)-6} kishi..." if len(sample) > 6 else ""))
            lines.append("")

        return "\n".join(lines).strip()

    # 2. Action: get_students_summary (Jami o'quvchilar umumiy statistikasi)
    m_sum = ACTION_STUDENTS_SUM.search(reply_text)
    if not m_sum:
        if re.search(r"jami\s+.*?(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi)", orig_msg, re.I) or \
           re.search(r"o'quvchilar(?:im)?\s+soni\s+qancha", orig_msg, re.I):
            m_sum = True

    if m_sum:
        summary = get_students_summary()
        tot = summary["total_students"]
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

    # 3. Action: search_telegram
    m_search = ACTION_SEARCH.search(reply_text)
    if not m_search:
        fb = re.search(r"(?:telegramdan|chatlardan)\s+(?:'|\")?([^'\"]+?)(?:'|\")?\s+(?:ni\s+)?(?:qidir|top)", orig_msg, re.I)
        if fb:
            m_search = fb

    if m_search:
        query = m_search.group(1).strip()
        # Agar qidiruv so'zi guruh a'zolari soniga tegishli bo'lsa, get_group_info ga yo'naltirish
        if re.search(r"(?:necha|nechta|qancha)\s+(?:o'quvchi|oquvchi|odam|bola|a'zo|azo|kishi)", query, re.I) or \
           re.search(r"(?:guruhda|guruhimizda)", query, re.I):
            data = await get_group_info(client, "")
            groups = data.get("groups", [])
            if groups:
                lines = ["👥 **Guruhdagi o'quvchilar va a'zolar soni:**\n"]
                for g in groups:
                    lines.append(f"• 📍 **{g['group_name']}**: Jami **{g['total_members']} nafar** ({g['students_count']} ta o'quvchi)")
                return "\n".join(lines)

        results = await search_telegram_messages(client, query, limit=6)
        if not results or (len(results) == 1 and "error" in results[0]):
            return f"🔍 **Telegram qidiruv natijasi:**\n'{query}' bo'yicha hech qanday xabar topilmadi."
        lines = [f"🔍 **'{query}' bo'yicha topilgan xabarlar:**\n"]
        for i, res in enumerate(results, 1):
            chat_name = res.get("chat_name", "Noma'lum")
            sender = res.get("sender_name", "Noma'lum")
            date = res.get("date", "")
            snippet = res.get("snippet", "")
            link = res.get("link")
            link_md = f" [🔗 Ochish]({link})" if link else ""
            lines.append(f"{i}. 📍 **{chat_name}** | 👤 *{sender}* ({date}):\n   «{snippet}»{link_md}\n")
        return "\n".join(lines)

    # 4. Action: find_contact (O'quvchi, odamlar, chatlar va guruh a'zolarini qidirish)
    m_contact = ACTION_FIND_CONTACT.search(reply_text)
    if not m_contact:
        fb = re.search(r"(.+?)\s+(?:degan\s+)?(?:o'quvchini|oquvchini|odamni|bolani|uydagilarini|lichkasini|kontaktini|chatini)\s+\b(?:top|qidir|aniqla)\b", orig_msg, re.I) or \
             re.search(r"(?:chatlar\s+ismi\s+bilan\s+)?(?:odamlarni|chatlarni|o'quvchilarni|kontaktlarni)\s+(?:ham\s+)?\b(?:top|qidir|aniqla)\b\s*[:\-]?(?:\s+)?(.+)", orig_msg, re.I) or \
             re.search(r"^([A-Za-z0-9_'\`\s]{2,25}?)(?:ning|ni|i)?\s+\b(?:chatini\s+top|lichkasini\s+top|qaysi\s+guruhda|top|qidir)\b", orig_msg, re.I)
        if fb:
            m_contact = fb

    if m_contact:
        query = m_contact.group(1).strip()
        query = re.sub(r"^(?:degan\s+|ismli\s+|chat\s+|guruh\s+)", "", query, flags=re.I).strip()
        data = await find_student_or_contact(client, query)
        crm_students = data.get("crm_students", [])
        tg_chats = data.get("telegram_chats", [])
        group_members = data.get("group_members", [])

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

        return "\n".join(lines)

    # 5. Action: send_message
    m_send = ACTION_SEND_MSG.search(reply_text)
    if not m_send:
        fb = re.search(r"^(.+?)(?:ga|da)\s+['\"](.+?)['\"]\s+(?:deb\s+)?(?:yoz|xabar\s+yubor|tashla)", orig_msg, re.I)
        if fb:
            m_send = fb

    if m_send:
        target = m_send.group(1).strip()
        text = m_send.group(2).strip()
        res = await send_telegram_message(client, target, text)
        if res.get("ok"):
            return (
                f"✅ **Xabar muvaffaqiyatli yuborildi!**\n\n"
                f"• **Qabul qiluvchi:** {res.get('target_name')}\n"
                f"• **Yuborilgan xabar:** «{text}»"
            )
        else:
            return f"❌ **Xabarni yuborib bo'lmadi:** {res.get('error')}"

    return reply_text


