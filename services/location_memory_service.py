"""
Aqlli Lokatsiya Xotirasi Xizmati (Smart Location Memory Service).
- Vazifalar guruhiga joylashuv yuborilganda nomini so'rab oladi.
- 'prosta saqla' yoki maxsus nom (masalan: 'Ishxona', 'Sport zal') bilan bazaga saqlaydi.
- Keyinchalik 'Ishxonam qayerda edi?' yoki 'Sport zal lokatsiyasini tashla' deganda
  rasmiy Telegram Location Pin va xarita havolalari bilan chiqarib beradi.
"""

import logging
import re
from telethon import TelegramClient
from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint
from services.memory_service import memory_service

logger = logging.getLogger("coddyHelper.location_memory_service")

# Nomlanishi kutilayotgan lokatsiyalar: chat_id -> (lat, long, address)
PENDING_LOCATION_NAMING: dict[int, tuple[float, float, str]] = {}


def has_pending_location_naming(chat_id: int) -> bool:
    """Ushbu chatda nomini kutayotgan lokatsiya bormi?"""
    return chat_id in PENDING_LOCATION_NAMING


def register_pending_location(chat_id: int, lat: float, long: float, address: str = "") -> str:
    """Yangi geolokatsiyani qabul qiladi va nomini so'rash xabarini qaytaradi."""
    PENDING_LOCATION_NAMING[chat_id] = (lat, long, address)
    return (
        "📍 **Nuriddin ustoz, joylashuvingiz qabul qilindi!**\n\n"
        "Ushbu manzilni qanday nom bilan xotiraga saqlay?\n"
        "Masalan: *«Ishxona»*, *«Sport zal»*, *«Do'stim uyi»* yoki shunchaki *«prosta saqla»* deb yozing. 👇"
    )


async def save_pending_location(chat_id: int, name_reply: str, client: TelegramClient = None) -> str:
    """Foydalanuvchi bergan nom bilan geolokatsiyani saqlaydi."""
    data = PENDING_LOCATION_NAMING.pop(chat_id, None)
    if not data:
        return "⚠️ Saqlash uchun faol lokatsiya topilmadi."

    lat, long, address = data
    clean_name = name_reply.strip()

    if clean_name.lower() in ("prosta saqla", "shunchaki saqla", "saqla", "prosta", "shunchaki"):
        clean_name = f"Joylashuv ({lat:.4f}, {long:.4f})"

    # Keraksiz qo'shimchalarni tozalash (masalan: "nomi ishxona" -> "Ishxona")
    clean_name = re.sub(r"^(?:nomi|deb\s+saqla|nomi\s+esa|nomini\s+)\s*", "", clean_name, flags=re.I).strip()

    loc_id = memory_service.add_saved_location(
        name=clean_name,
        lat=lat,
        long=long,
        address=address,
    )

    gmaps_link = f"https://www.google.com/maps?q={lat},{long}"
    yandex_link = f"https://yandex.com/maps/?pt={long},{lat}&z=16&l=map"

    # Shuningdek umumiy qoidalar xotirasiga ham kiritish
    memory_service.add_learned_fact(
        topic=f"lokatsiya_{clean_name.lower()}",
        content=f"📍 {clean_name} lokatsiyasi: lat={lat:.6f}, long={long:.6f}. Havola: {gmaps_link}",
        category="mentor_location",
    )

    return (
        f"✅ **«{clean_name}» joylashuvi xotiraga muvaffaqiyatli saqlandi!** (ID: #{loc_id})\n\n"
        f"• 🌐 **GPS:** `{lat:.6f}, {long:.6f}`\n"
        f"• 🗺 [Google Maps]({gmaps_link}) | [Yandex Maps]({yandex_link})\n\n"
        f"Keyinchalik istalgan payt *«{clean_name} lokatsiyasini tashla»* yoki *«{clean_name} qayerda edi»* "
        "desangiz, uni to'liq Telegram xaritasi bilan chiqarib beraman! 🚀"
    )


def extract_location_query(text: str) -> str | None:
    """Matnda lokatsiyani so'rash talabi borligini aniqlaydi va qidirilayotgan joy nomini ajratadi."""
    t = text.lower().strip().rstrip("?!. ")

    # 1. Aloqa, o'quvchi, telefon, oila yoki umumiy topshiriq so'zlari bo'lsa, bu LOKATSIYA EMAS:
    non_loc_pattern = re.compile(
        r"\b(?:raqam\w*|nomer\w*|telefon\w*|kontakt\w*|tel|kod\w*|sms\w*|"
        r"uydagilar\w*|uydigilar\w*|ota-ona\w*|ota\s+ona\w*|onasi\b|otasi\b|dadasi\b|oyisi\b|"
        r"qidir\w*|topib\b|so['’`]?ra\w*|bilchi\b|aniqla\w*|"
        r"ma['’`]?muriyat\w*|mamuryat\w*|admin\w*|"
        r"o['’`]?quvchi\w*|oquvchi\w*|student\w*|talaba\w*|"
        r"dars\w*|vazifa\w*|skrinshot\w*|xato\w*|xatolik\w*|bug\w*)\b",
        re.I
    )
    if non_loc_pattern.search(t):
        return None

    # "qayerda" bilan keladigan iboralar yoki grammatik savollar:
    idiom_phrases = (
        "qayerda bo'lmasin", "qayerda bolmasin", "qayerda bo'lsa", "qayerda bosa",
        "qayerdadir", "qayerdandir", "qayerda xato", "qayerda yozilgan", "qayerida",
    )
    if any(ip in t for ip in idiom_phrases):
        return None

    if not any(k in t for k in ("lokatsiya", "joylashuv", "manzil", "geopozitsiya", "gps", "koordinata", "xarita", "qayerda", "qayer", "qattaligi")):
        return None

    # Qidiruv namunalari - eng aniqlaridan boshlab
    patterns = [
        # 1. "ofis lokatsiyasini tashla", "ishxona manzilini ber", "filial lokatsiyasi"
        r"^(.+?)\s+(?:lokatsiya\w*|joylashuv\w*|manzil\w*|geopozitsiya\w*)\b.*?(?:qayerda|qayer|tashla|yubor|ber|ko['’`]?rsat)?$",
        r"(?:lokatsiya\w*|joylashuv\w*|manzil\w*)\s+(?:nomi\s+)?([a-zA-Z0-9_'\s]{2,30})",
        # 2. "ishxona qayerda edi", "sport zal qayerda?" (jumla oxirida yoki edi/joylashgan bilan)
        r"^(.+?)\s+(?:qayerda\s+edi|qayerda\s+joylashgan|qayerda\s*\?*$)",
        # 3. "qayerda edi ishxona", "qayerda sport zal"
        r"^(?:qayerda\s+edi|qayerda\s+joylashgan|qayerda)\s+([a-zA-Z0-9_'\s]{2,30})\?*$",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            q = m.group(1).strip()
            # Keraksiz so'zlarni tozalash
            q = re.sub(r"\b(?:menga|bizga|o['’`]?sha|shu|joyni|joyning|mening|bizning|iltimos)\b", "", q).strip()
            # O'zbekcha egalik qo'shimchasini tozalash: "ishxonam" -> "ishxona", "ofisim" -> "ofis"
            if q.endswith("m") and len(q) > 4:
                if q[-2] in ("a", "e", "i", "o", "u"):
                    q = q[:-1]
                elif q.endswith("im") or q.endswith("um"):
                    q = q[:-2]
            q = q.strip("?!. ")
            # Agar ajratilgan matn juda uzun (gap yoki ko'rsatma) bo'lsa, bu lokatsiya emas!
            if len(q.split()) > 4 or len(q) > 30:
                continue
            if len(q) >= 2 and q not in ("shu", "joy", "lokatsiya", "edi", "xarita"):
                return q

    return None


async def handle_find_location_request(client: TelegramClient, chat_id: int, query: str, full_text: str = "") -> str | None:
    """Qidirilgan nom bo'yicha lokatsiyani topib, rasmiy xarita pin xabari bilan yuboradi."""
    loc = memory_service.get_saved_location(query)
    if not loc:
        # Agar foydalanuvchi EXPLICIT (aniq) lokatsiya so'zlarini ishlatmagan bo'lsa,
        # va bunday nomli lokatsiya saqlanmagan bo'lsa, boshqa xizmatlar / AI ishlashi uchun None qaytaramiz!
        explicit_location_keywords = ("lokatsiya", "joylashuv", "manzil", "geopozitsiya", "gps", "koordinata", "xarita")
        has_explicit_kw = any(k in (full_text or query).lower() for k in explicit_location_keywords)
        if not has_explicit_kw:
            return None

        # Faqat foydalanuvchi aniq lokatsiya/manzil deb so'ragandagina topilmadi deb ro'yxatni ko'rsatamiz:
        all_locs = memory_service.list_saved_locations(limit=10)
        if all_locs:
            names = [f"• «{l['name']}»" for l in all_locs]
            return (
                f"🔍 **«{query}» nomli joylashuv topilmadi.**\n\n"
                f"Sizda saqlangan lokatsiyalar:\n" + "\n".join(names)
            )
        return f"🔍 **«{query}» bo'yicha saqlangan joylashuv topilmadi.** Hozircha birorta ham manzil saqlanmagan."

    lat = float(loc["lat"])
    long = float(loc["long"])
    name = loc["name"]
    gmaps_link = f"https://www.google.com/maps?q={lat},{long}"
    yandex_link = f"https://yandex.com/maps/?pt={long},{lat}&z=16&l=map"

    # 1. Telegramning rasmiy interaktiv xaritali Location Pin xabarini yuboramiz
    if client:
        try:
            media = InputMediaGeoPoint(InputGeoPoint(lat=lat, long=long))
            await client.send_file(chat_id, media)
        except Exception as pe:
            logger.warning("Location pin jo'natishda ogohlantirish: %s", pe)

    # 2. To'liq tafsilotli matn
    return (
        f"📍 **«{name}» joylashuvi topildi:**\n\n"
        f"• 🌐 **GPS Koordinatalar:** `{lat:.6f}, {long:.6f}`\n"
        f"• 🗺 [Google Maps orqali ochish]({gmaps_link})\n"
        f"• 🗺 [Yandex Maps orqali ochish]({yandex_link})\n\n"
        "Yuqoridagi xaritada manzil ko'rsatildi! 🚀"
    )
