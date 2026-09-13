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


ACTION_GROUP_INFO = re.compile(r'<<<ACTION:get_group_info\(["\']?(.*?)["\']?\)>>>', re.IGNORECASE)
ACTION_STUDENTS_SUM = re.compile(r'<<<ACTION:get_students_summary\(\)>>>', re.IGNORECASE)
ACTION_SEARCH = re.compile(r'<<<ACTION:search_telegram\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_FIND_CONTACT = re.compile(r'<<<ACTION:find_contact\(["\'](.*?)["\']\)>>>', re.IGNORECASE)
ACTION_SEND_MSG = re.compile(r'<<<ACTION:send_message\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)
ACTION_RECENT_SENDERS = re.compile(r'<<<ACTION:get_recent_senders\((.*?)\)>>>', re.IGNORECASE)
ACTION_LEARN_FACT = re.compile(r'<<<ACTION:learn_fact\(["\'](.*?)["\'],\s*["\'](.*?)["\']\)>>>', re.IGNORECASE | re.DOTALL)
ACTION_GET_LEARNED = re.compile(r'<<<ACTION:get_learned_facts\(\)>>>', re.IGNORECASE)
ACTION_FORGET_FACT = re.compile(r'<<<ACTION:forget_fact\(["\'](.*?)["\']\)>>>', re.IGNORECASE)



async def execute_agent_action(reply_text: str, client, orig_msg: str) -> str:
    """
    AI javobidagi maxsus harakat buyruqlarini (Action Tools) yoki
    foydalanuvchining to'g'ridan-to'g'ri Telegram amallari talablarini (o'zbek va rus tillarida) bajaradi.
    """
    is_ru = is_russian_text(orig_msg)

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

    # 4. Action: find_contact (O'quvchi, kontakt yoki guruh a'zolarini qidirish / Поиск контакта)
    m_contact = ACTION_FIND_CONTACT.search(reply_text)
    if not m_contact:
        fb = (
            re.search(r"^(?:top|qidir|izla|aniqla)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"^(?:найди|найти|поищи|поиск|где|кто\s+такой)\s*[:\-]?\s*(.+)$", orig_msg, re.I) or
            re.search(r"^(.+?)\s+(?:haqida|kim\b|qayerda\b|где\s+находится|кто\s+такой)", orig_msg, re.I) or
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

    return reply_text


