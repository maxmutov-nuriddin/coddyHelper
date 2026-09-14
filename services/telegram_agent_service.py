"""
services/telegram_agent_service.py
Telegram Action Agent xizmati:
Telethon mijozi orqali xabarlarni qidirish, o'quvchi va ota-onalar kontaktlarini topish,
hamda to'g'ridan-to'g'ri xabar yuborish amallarini bajaradi.
"""

import asyncio
import logging
import re
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
    maksimal kuchli qidiruv taqqoslashini amalga oshiradi:
    - Submatn va teskari submatn mosligi
    - Tutuq belgisisiz (otkir/o'tkir) moslik
    - 'x' va 'h' tovushlari mutanosibligi (shoxrux/shohruh)
    - So'zma-so'z token va 80%+ noaniq (fuzzy) o'xshashlik
    - O'zbekcha va ruscha qo'shimchalarni (-ni, -ga, -dan, -bek, -а, -у, -ом, -ов) hisobga olish
    """
    from difflib import SequenceMatcher

    q_norm = normalize_text(query)
    t_norm = normalize_text(target)
    if not q_norm or not t_norm:
        return False

    # 1. To'g'ridan-to'g'ri submatn mosligi
    if q_norm in t_norm or t_norm in q_norm:
        return True

    # 2. Tutuq belgisisiz yumshoq moslik (masalan: otkir va o'tkir, g'ayrat va gayrat)
    q_no_quote = q_norm.replace("'", "")
    t_no_quote = t_norm.replace("'", "")
    if q_no_quote in t_no_quote or t_no_quote in q_no_quote:
        return True

    # 3. 'x' va 'h' tovushlarini birlashtirilgan holda tekshirish (Shohruh <-> Shoxrux, Bahrom <-> Baxrom)
    q_xh = q_no_quote.replace("x", "h")
    t_xh = t_no_quote.replace("x", "h")
    if q_xh in t_xh or t_xh in q_xh:
        return True

    # 4. So'zlar / tokenlar bo'yicha va Fuzzy (xatoliklarga chidamli) taqqoslash
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

    if q_tokens and all(any(tokens_match(qt, tt) for tt in t_tokens) for qt in q_tokens):
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
        # Mentorning o'ziga yo'naltirilgan xabarlar (Nuriddin, ustoz, me, o'zimga)
        if target.lower() in ("nuriddin", "nuriddinga", "ustoz", "teacher", "me", "o'zim", "ozim", "menga", "o'zimga"):
            resolved_entity = "me"
            target_name = "Nuriddin (Saved Messages)"

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
        resolved_entity = "me"
        target_name = "Nuriddin (Saved Messages)"
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
        resolved_entity = "me"
        target_name = f"{target} (eslatma sifatida)"

    # 2. Vaqtni aniqlash
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    delay_sec = None
    remind_at_dt = None

    rel_match = re.search(r"(\d+)\s*(daqiqa|minut|sekund|soniya|soat|kun)", time_str.lower())
    if rel_match:
        val = int(rel_match.group(1))
        unit = rel_match.group(2)
        if "sekund" in unit or "soniya" in unit:
            delay_sec = float(val)
        elif "soat" in unit:
            delay_sec = float(val * 3600)
        elif "kun" in unit:
            delay_sec = float(val * 86400)
        else:
            delay_sec = float(val * 60)
        remind_at_dt = now + timedelta(seconds=delay_sec)
    else:
        from services.ai_service import extract_smart_reminder
        parsed = extract_smart_reminder(time_str, current_tashkent_time=now.strftime("%Y-%m-%d %H:%M:%S"))
        if parsed and parsed.get("remind_at"):
            try:
                remind_at_dt = datetime.strptime(parsed["remind_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tashkent_tz)
                diff = (remind_at_dt - now).total_seconds()
                delay_sec = max(5.0, diff)
            except Exception:
                pass

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



async def execute_agent_action(reply_text: str, client, orig_msg: str, is_admin_mode: bool = True, chat_id: int | None = None) -> str:
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
            link = res.get("link")
            open_txt = "Открыть" if is_ru else "Ochish"
            link_md = f" [🔗 {open_txt}]({link})" if link else ""
            lines.append(f"{i}. 📍 **{chat_name}** | 👤 *{sender}* ({date}):\n   «{snippet}»{link_md}\n")
        return "\n".join(lines)

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
            time_part = remind_pattern_1.group(1) or ""
            subj = remind_pattern_1.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Eslatma: {subj}"
            sched_time = f"{time_part} daqiqa" if time_part.isdigit() else orig_msg
        elif remind_pattern_2:
            time_part = remind_pattern_2.group(1) or ""
            subj = remind_pattern_2.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Eslatma: {subj}"
            sched_time = f"{time_part} daqiqa" if time_part.isdigit() else orig_msg
        elif remind_pattern_ru:
            time_part = remind_pattern_ru.group(1) or ""
            subj = remind_pattern_ru.group(2).strip()
            sched_target = "me"
            sched_text = f"🔔 Напоминание: {subj}"
            sched_time = f"{time_part} минут" if time_part.isdigit() else orig_msg
        elif remind_pattern_other:
            sched_target = remind_pattern_other.group(1).strip()
            sched_text = remind_pattern_other.group(2).strip()
            sched_time = remind_pattern_other.group(3).strip() if len(remind_pattern_other.groups()) >= 3 and remind_pattern_other.group(3) else orig_msg

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
    if not m_contact and not is_reminder_msg:
        fb = (
            re.search(r"^(?:top|qidir|izla|aniqla)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"^(?:найди|найти|поищи|поиск|где|кто\s+такой)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"^(.+?)\s+(?:haqida\s+(?:ma['’`]?lumot|bilmoqchiman|gapir)|kim\b|qayerda\b|где\s+находится|кто\s+такой)", orig_msg, re.I) or
            re.search(r"(.+?)\s+(?:degan\s+)?(?:o'quvchini|oquvchini|odamni|bolani|uydagilarini|lichkasini|kontaktini|chatini)\s+\b(?:top|qidir|aniqla|izla)\b", orig_msg, re.I) or
            re.search(r"(?:найди|поищи|пробей)\s+(?:ученика|контакт|личку|чат)\s*[:\-]?\s*(.+)", orig_msg, re.I) or
            re.search(r"(?:chatlar\s+ismi\s+bilan\s+)?(?:odamlarni|chatlarni|o'quvchilarni|kontaktlarni)\s+(?:ham\s+)?\b(?:top|qidir|aniqla|izla)\b\s*[:\-]?(?:\s+)?(.+)", orig_msg, re.I) or
            re.search(r"^([A-Za-z0-9_'\`\s\u0400-\u04FF]{2,25}?)(?:ning|ni|i)?\s+\b(?:chatini\s+top|lichkasini\s+top|qaysi\s+guruhda|в\s+какой\s+группе|top|qidir|izla)\b", orig_msg, re.I)
        )
        if fb:
            m_contact = fb

    if m_contact:
        query = m_contact.group(1).strip()
        query = re.sub(
            r"^(?:degan\s+|ismli\s+|chat\s+|guruh\s+|ученика\s+|контакт\s+|по\s+имени\s+|чат\s+|группу\s+)",
            "",
            query,
            flags=re.I,
        ).strip()
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

    return reply_text


