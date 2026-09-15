"""
Tongi Brifing va Uyg'onish Nazorati Xizmati (Morning Briefing & Wake-up Escalation).
- Har kuni ertalab soat 08:00 da (Asia/Tashkent) "Vazifalar" guruhiga ob-havo va rejalarni yo'llaydi.
- "Turdingizmi?" nazorati: 10 daqiqa (08:10) ichida tasdiqlanmasa, favqulodda kontaktga (5023430798) xabar beradi.
"""

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import aiohttp
from config import config, get_vazifalar_chat_target
from services.memory_service import memory_service

logger = logging.getLogger("coddyHelper.morning_service")

# Uyg'onishni kuzatish holati
PENDING_WAKEUP: dict = {
    "date": "",
    "timestamp": 0.0,
    "confirmed": False,
    "escalated": False,
}

LAST_BRIEFING_DATE: str = ""


async def get_tashkent_weather() -> dict:
    """Toshkent shahri uchun tezkor ob-havo ma'lumotini Open-Meteo orqali oladi (0.05s, bepul)."""
    url = "https://api.open-meteo.com/v1/forecast?latitude=41.2995&longitude=69.2401&current_weather=true&timezone=Asia%2FTashkent"
    try:
        timeout = aiohttp.ClientTimeout(total=4.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cw = data.get("current_weather", {})
                    temp = cw.get("temperature", 22)
                    wcode = cw.get("weathercode", 0)

                    # Ob-havo holati kodlari
                    if wcode in (0, 1):
                        condition = "Ochiq, quyoshli ☀️"
                    elif wcode in (2, 3):
                        condition = "Biroz bulutli ⛅️"
                    elif wcode in (45, 48):
                        condition = "Tumanli 🌫"
                    elif wcode in (51, 53, 55, 61, 63, 65, 80, 81, 82):
                        condition = "Yomg'irli 🌧"
                    elif wcode in (71, 73, 75, 85, 86):
                        condition = "Qorli ❄️"
                    else:
                        condition = "Musaffo 🌤"

                    sign = "+" if temp > 0 else ""
                    return {
                        "temp": f"{sign}{int(round(temp))}°C",
                        "condition": condition,
                    }
    except Exception as e:
        logger.debug("Ob-havoni olishda ogohlantirish (standart qo'yiladi): %s", e)

    return {"temp": "+24°C", "condition": "Ochiq, musaffo 🌤"}


def get_uzbek_date_str(dt: datetime) -> str:
    """O'zbek tilidagi sana va hafta kunini chiqaradi."""
    months = [
        "", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
        "iyul", "avgust", "sentyabr", "oktyabr", "noyabr", "dekabr"
    ]
    weekdays = [
        "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"
    ]
    day = dt.day
    month_name = months[dt.month]
    weekday_name = weekdays[dt.weekday()]
    return f"{day}-{month_name}, {weekday_name}"


async def send_morning_briefing(client, bot=None) -> bool:
    """
    Ertalabki soat 08:00 brifingini Vazifalar guruhiga jo'natadi va
    10 daqiqalik uyg'onish eskalatsiya taymerini boshlaydi.
    """
    global LAST_BRIEFING_DATE, PENDING_WAKEUP
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    today_str = now.strftime("%Y-%m-%d")

    if LAST_BRIEFING_DATE == today_str:
        return False
    LAST_BRIEFING_DATE = today_str

    vazifalar_chat = await get_vazifalar_chat_target(client)
    if str(vazifalar_chat).strip().lower() in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
        vazifalar_chat = -1005388159517

    # 1. Ob-havo
    weather = await get_tashkent_weather()
    date_uz = get_uzbek_date_str(now)

    # 2. Bugungi rejalar va eslatmalar
    plans = memory_service.get_plans_for_date(today_str)
    reminders = memory_service.get_active_reminders(limit=20)
    today_reminders = [r for r in reminders if r.get("remind_at", "").startswith(today_str)]

    tasks_lines = []
    if plans:
        for p in plans:
            status = "✅" if p["is_completed"] else "⏳"
            t_str = f" `{p['plan_time']}` —" if p["plan_time"] else ""
            tasks_lines.append(f"• {status}{t_str} {p['title']}")

    if today_reminders:
        for r in today_reminders:
            r_time = r.get("remind_at", "").split()[1][:5] if " " in r.get("remind_at", "") else ""
            tasks_lines.append(f"• 🔔 `{r_time}` — {r['text']}")

    if tasks_lines:
        tasks_text = "\n".join(tasks_lines)
    else:
        tasks_text = "Bugunga rejalashtirilgan vazifalar yo'q, kuningiz maroqli o'tsin! 😊"

    target_user = config.mentor_user_id or 8105823872
    briefing_text = (
        f"☀️ **Xayrli tong, Nuriddin!** Bugun {date_uz}.\n\n"
        f"🌤 **Toshkent ob-havosi:** {weather['condition']} ({weather['temp']})\n\n"
        f"📋 **Bugungi kun rejalari:**\n{tasks_text}\n\n"
        f"⏰ **Turdingizmi?** Kunni boshlashga tayyormisiz? [Nuriddin](tg://user?id={target_user})\n"
        f"_(Iltimos, uyg'ongan bo'lsangiz 10 daqiqa ichida 'Ha', 'Turdim' deb javob bering yoki tasdiqlang)_"
    )

    # 3. Yuborish (FAQAT Vazifalar guruhiga, Izbrannoe / Saved Messages ga ASLO emas)
    sent = False
    # Telethon orqali Vazifalar guruhiga ovozli bildirishnoma (silent=False) bilan yetkazish
    if client:
        try:
            await client.send_message(vazifalar_chat, briefing_text, silent=False)
            sent = True
            logger.info("☀️ Tongi brifing Telethon orqali Vazifalar guruhiga (%s) push bilan yetkazildi.", vazifalar_chat)
        except Exception as c_err:
            logger.warning("Telethon orqali tongi brifing yuborishda ogohlantirish: %s", c_err)

    if not sent and config.bot_token:
        try:
            from aiogram import Bot
            b_inst = Bot(token=config.bot_token)
            try:
                c_id = int(vazifalar_chat) if str(vazifalar_chat).lstrip("-").isdigit() else vazifalar_chat
                await b_inst.send_message(
                    chat_id=c_id,
                    text=briefing_text,
                    parse_mode="Markdown",
                    disable_notification=False,
                )
                sent = True
                logger.info("☀️ Tongi brifing bot orqali Vazifalar guruhiga (%s) yetkazildi.", c_id)
            finally:
                await b_inst.session.close()
        except Exception as b_err:
            logger.error("Bot orqali tongi brifing yuborishda xatolik: %s", b_err)

    # 4. Uyg'onish nazorati taymerini ishga tushirish (10 daqiqa)
    PENDING_WAKEUP = {
        "date": today_str,
        "timestamp": time.time(),
        "confirmed": False,
        "escalated": False,
    }

    asyncio.create_task(_monitor_wakeup_escalation(client, today_str))
    return True


async def _monitor_wakeup_escalation(client, date_str: str, wait_seconds: float = 600.0):
    """10 daqiqa (yoki belgilangan soniya) kutadi. Agar Nuriddin tasdiqlamasa, favqulodda kontaktga yozadi."""
    logger.info("⏰ Uyg'onish nazorati boshlandi (%.1f soniyalik taymer).", wait_seconds)
    await asyncio.sleep(wait_seconds)

    global PENDING_WAKEUP
    if PENDING_WAKEUP.get("date") == date_str and not PENDING_WAKEUP.get("confirmed") and not PENDING_WAKEUP.get("escalated"):
        PENDING_WAKEUP["escalated"] = True
        emergency_raw = memory_service.get_setting("emergency_contact_id", "5023430798")
        
        # Bir nechta ID larni vergul, bo'sh joy yoki nuqta-vergul orqali ajratib olish
        import re
        contact_ids = []
        for part in re.split(r"[,;\s\n]+", str(emergency_raw).strip()):
            clean = part.strip().lstrip("@")
            if not clean:
                continue
            if clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit()):
                contact_ids.append(int(clean))
            else:
                contact_ids.append(clean)

        if not contact_ids:
            contact_ids = [5023430798]

        alert_msg = (
            "Assalomu alaykum! Men Nuriddinning shaxsiy assistentiman.\n\n"
            "Nuriddin ertalabki uyg'onish eslatmasini tasdiqlamadi. "
            "Iltimos, uni uyg'otib yubora olasizmi? Rahmat!"
        )

        logger.warning("🚨 Nuriddin 08:10 gacha uyg'onmadi! Favqulodda kontaktlarga (%s) xabar yo'llanmoqda...", contact_ids)

        # Barcha kiritilgan favqulodda kontaktlarga jo'natish
        for cid in contact_ids:
            sent_esc = False
            if config.bot_token:
                try:
                    from aiogram import Bot
                    b_inst = Bot(token=config.bot_token)
                    try:
                        await b_inst.send_message(
                            chat_id=cid,
                            text=alert_msg,
                            disable_notification=False,
                        )
                        sent_esc = True
                        logger.info("🚨 Favqulodda uyg'otish xabari bot orqali (%s) ga yuborildi.", cid)
                    finally:
                        await b_inst.session.close()
                except Exception as be:
                    logger.debug("Bot orqali favqulodda kontaktga (%s) yuborishda ogohlantirish: %s", cid, be)

            if not sent_esc and client:
                try:
                    await client.send_message(cid, alert_msg, silent=False)
                    logger.info("🚨 Favqulodda uyg'otish xabari Telethon orqali (%s) ga yuborildi.", cid)
                except Exception as ce:
                    logger.error("Telethon orqali favqulodda kontaktga (%s) yuborib bo'lmadi: %s", cid, ce)

        # Vazifalar guruhiga ham bildirishnoma tashlash (ovozli bildirishnoma va teg bilan)
        from config import get_vazifalar_chat_target
        vazifalar_chat = await get_vazifalar_chat_target(client)
        if str(vazifalar_chat).strip().lower() in ("me", "self", "0", "8105823872", str(config.mentor_user_id)):
            vazifalar_chat = -1005388159517

        contacts_str = ", ".join(f"`{c}`" for c in contact_ids)
        target_user = config.mentor_user_id or 8105823872
        group_notice = (
            f"⚠️ **Uyg'onish tasdiqlanmadi (10 daqiqa o'tdi).** [Nuriddin](tg://user?id={target_user})\n\n"
            f"Nuriddinni uyg'otish uchun favqulodda kontaktlarga ({contacts_str}) xushmuomala ogohlantirish yuborildi."
        )
        sent_g = False
        if client:
            try:
                await client.send_message(vazifalar_chat, group_notice, silent=False)
                sent_g = True
                logger.info("⚠️ Uyg'onish eskalatsiya xabari Telethon orqali Vazifalar guruhiga (%s) push bilan yetkazildi.", vazifalar_chat)
            except Exception as ge:
                logger.warning("Telethon orqali Vazifalar guruhiga eskalatsiya yuborishda ogohlantirish: %s", ge)

        if not sent_g and config.bot_token:
            try:
                from aiogram import Bot
                b_inst = Bot(token=config.bot_token)
                try:
                    c_id = int(vazifalar_chat) if str(vazifalar_chat).lstrip("-").isdigit() else vazifalar_chat
                    await b_inst.send_message(
                        chat_id=c_id,
                        text=group_notice,
                        parse_mode="Markdown",
                        disable_notification=False,
                    )
                    logger.info("⚠️ Uyg'onish eskalatsiya xabari bot orqali Vazifalar guruhiga (%s) yetkazildi.", c_id)
                finally:
                    await b_inst.session.close()
            except Exception as be:
                logger.error("Bot orqali Vazifalar guruhiga eskalatsiya xabari yuborishda xatolik: %s", be)


def is_wakeup_confirmation_text(text: str) -> bool:
    """Matn uyg'onish tasdig'i ekanini tekshiradi."""
    clean = text.lower().strip().rstrip("!?.,~ ")
    triggers = {
        "turdim", "ha turdim", "uyg'ondim", "uygondim", "ha uyg'ondim", "turvoldim",
        "turibman", "ha", "xa", "salom", "xayrli tong", "boshladik", "tayyorman",
        "yaxshiman", "prosnulsya", "vstal", "da", "dobroe utro"
    }
    return clean in triggers or "turdim" in clean or "uyg'ondim" in clean or "uygondim" in clean


def confirm_wakeup_success() -> str:
    """Uyg'onishni tasdiqlaydi va javob matnini beradi."""
    global PENDING_WAKEUP
    PENDING_WAKEUP["confirmed"] = True
    return "Ajoyib, Nuriddin! Uyg'onganingiz tasdiqlandi. Kuningiz barakali va unumli o'tsin! 🚀"


async def start_morning_worker(client):
    """Har 30 soniyada soatni tekshirib, 08:00 bo'lganda tongi brifingni ishga tushiradi."""
    logger.info("Tongi brifing fon xizmati (08:00 Toshkent vaqti) faollashdi.")
    await asyncio.sleep(15)

    tashkent_tz = ZoneInfo("Asia/Tashkent")
    while True:
        try:
            now = datetime.now(tashkent_tz)
            # Har kuni soat 08:00 da (08:00:00 dan 08:00:59 gacha)
            if now.hour == 8 and now.minute == 0:
                await send_morning_briefing(client)
        except Exception as e:
            logger.error("Morning workerda kutilmagan xatolik: %s", e)

        await asyncio.sleep(30)
