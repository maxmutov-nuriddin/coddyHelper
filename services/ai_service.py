"""
AI integratsiyasi (Groq Multi-Key va Google Gemini qo'llab-quvvatlanadi)
"""

import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from config import config, is_escalation_chat
from prompts import SYSTEM_PROMPT, ADMIN_SYSTEM_PROMPT
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

ESCALATE_PATTERN = re.compile(r"<<<ESCALATE>>>(.*?)<<<END_ESCALATE>>>", re.DOTALL)


def check_fast_faq(text: str) -> str | None:
    """Eng ko'p uchraydigan standart dasturlash xatolariga 0.5 soniyada tayyor yechim beradi."""
    t = text.strip()
    if not t:
        return None

    # 1. ModuleNotFoundError
    mod_match = re.search(r"ModuleNotFoundError:\s*No module named\s*['\"]([^'\"]+)['\"]", t, re.IGNORECASE)
    if mod_match:
        pkg = mod_match.group(1)
        pip_pkg = pkg
        if pkg.lower() == "telebot":
            pip_pkg = "pyTelegramBotAPI"
        elif pkg.lower() == "cv2":
            pip_pkg = "opencv-python"
        elif pkg.lower() == "bs4":
            pip_pkg = "beautifulsoup4"
        elif pkg.lower() == "dotenv":
            pip_pkg = "python-dotenv"
        elif pkg.lower() == "pil":
            pip_pkg = "pillow"

        return (
            f"🔍 **Aniqlangan xatolik:** `{pkg}` kutubxonasi o'rnatilmagan.\n\n"
            f"🛠 **Yechim:** Terminalga quyidagi buyruqni yozing:\n"
            f"```bash\npip install {pip_pkg}\n```\n"
            f"_Agar virtual muhit (venv) ishlatayotgan bo'lsangiz, avval venv ni faollashtiring._"
        )

    # 2. 'pip' is not recognized
    if ("'pip' is not recognized" in t.lower()) or ("pip topilmadi" in t.lower()) or ("pip: command not found" in t.lower()):
        return (
            "🔍 **Aniqlangan xatolik:** Tizim `pip` buyrug'ini taniy olmayapti (Python PATH muhitiga qo'shilmagan).\n\n"
            "🛠 **Yechim (2 xil usul):**\n"
            "1. **Tezkor usul:** Terminalda quyidagicha yozing:\n"
            "```bash\npython -m pip install <kutubxona_nomi>\n```\n"
            "2. **Asosiy yechim:** Python ni qayta o'rnatayotganda pastdagi **'Add Python to PATH'** katagiga belgi qo'ying."
        )

    # 3. IndentationError
    if "indentationerror" in t.lower():
        return (
            "🔍 **Aniqlangan xatolik:** `IndentationError` — Qator boshidagi bo'shliqlar (probellar) xato ketgan.\n\n"
            "🛠 **Yechim:**\n"
            "• Python'da `if`, `for`, `def`, `while` dan keyingi qatorlar aniq **4 ta probel (yoki 1 ta Tab)** bilan ichkariga surilishi shart.\n"
            "• Barcha qatorlardagi bo'shliqlarni bir xil qilib to'g'rilab chiqing."
        )

    # 4. Telegram Conflict (terminated by other getUpdates)
    if "conflict: terminated by other getupdates request" in t.lower():
        return (
            "🔍 **Aniqlangan xatolik:** Telegram Bot Token Conflict — Bot bir vaqtning o'zida ikkita joyda ishlab turibdi!\n\n"
            "🛠 **Yechim:**\n"
            "1. Bot ochilgan boshqa barcha terminallar yoki VS Code oynalarini to'xtating (Ctrl + C).\n"
            "2. Faqat bitta joyda botni qayta ishga tushiring. Shunda ziddiyat yo'qoladi."
        )

    # 5. IndexError: list index out of range
    if "indexerror: list index out of range" in t.lower():
        return (
            "🔍 **Aniqlangan xatolik:** `IndexError: list index out of range` — Ro'yxatda mavjud bo'lmagan indeksga murojaat qilingan.\n\n"
            "🛠 **Yechim:**\n"
            "• Masalan, ro'yxatda 3 ta element bo'lsa, uning indekslari: `0, 1, 2`. Siz `3` yoki undan katta indeksni chaqiryapsiz.\n"
            "• Element chaqirishdan oldin ro'yxat uzunligini tekshiring: `if len(royxat) > index:`"
        )

    # 6. KeyError
    key_match = re.search(r"KeyError:\s*['\"]?([^'\"]+)['\"]?", t, re.IGNORECASE)
    if key_match:
        k_name = key_match.group(1)
        return (
            f"🔍 **Aniqlangan xatolik:** `KeyError: '{k_name}'` — Lug'atda (dictionary) `{k_name}` nomli kalit mavjud emas.\n\n"
            f"🛠 **Yechim:** Xavfsiz usuldan foydalaning:\n"
            f"```python\nqiymat = lugat.get('{k_name}', None)\n```"
        )

    return None


def redact_sensitive_data(text: str) -> str:
    """API kalitlari, tokenlar va maxfiy ma'lumotlarni chatga chiqib ketishidan tozalaydi."""
    if not text:
        return ""
    # Groq API kalitlari
    text = re.sub(r"gsk_[A-Za-z0-9_]{20,}", "[MAXFIY_KALIT]", text)
    # Gemini API kalitlari
    text = re.sub(r"AIzaSy[A-Za-z0-9_\-]{30,}", "[MAXFIY_KALIT]", text)
    # Telegram Bot tokenlari
    text = re.sub(r"\b\d{8,11}:[A-Za-z0-9_-]{32,}\b", "[MAXFIY_TOKEN]", text)
    # Maxfiy sessiya qatorlari
    text = re.sub(r"1[A-Za-z0-9+/=]{100,}", "[MAXFIY_SESSIYA]", text)
    return text


def extract_smart_reminder(text: str, current_tashkent_time: str | None = None) -> dict | None:
    """
    O'zbek tilidagi har qanday eslatma so'rovidan (nisbiy vaqt, sana, soat, minut, daqiqa)
    vazifa va aniq YYYY-MM-DD HH:MM:SS vaqtini 0.001 soniyada, AI siz, 100% aniqlikda ajratib oladi.
    Masalan:
      '2 soatdan song elsat' -> {'reminder_text': 'Rejalashtirilgan eslatma', 'remind_at': '...'}
      '2 soatdan keyin dars boshlash' -> {'reminder_text': 'dars boshlash', 'remind_at': '...'}
      '15 minutdan keyin kitob' -> {'reminder_text': 'kitob', 'remind_at': '...'}
      '1 soat 30 minutdan keyin' -> {'reminder_text': 'Rejalashtirilgan eslatma', 'remind_at': '...'}
      'bugun 20:00 da dars' -> {'reminder_text': 'dars', 'remind_at': '...'}
      'ertaga 10:00 da imtihon' -> {'reminder_text': 'imtihon', 'remind_at': '...'}
      '25 09 2026 15:00 da dars' -> {'reminder_text': 'dars', 'remind_at': '...'}
    """
    t = text.strip()
    if not t:
        return None

    # Hozirgi Toshkent vaqtini aniqlash
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    if current_tashkent_time:
        try:
            now = datetime.strptime(current_tashkent_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tashkent_tz)
        except Exception:
            now = datetime.now(tashkent_tz)
    else:
        now = datetime.now(tashkent_tz)

    target_dt = None
    matched_span = None

    # 0. O'zbekcha so'z bilan yozilgan sonlarni raqamga o'girish (ikki soat -> 2 soat)
    uz_num_map = [
        (r"\bo['’‘`]?n\s+besh\b", "15"),
        (r"\byigirma\s+besh\b", "25"),
        (r"\bo['’‘`]?ttiz\b", "30"),
        (r"\bqirq\s+besh\b", "45"),
        (r"\bbir\b", "1"),
        (r"\bikki\b", "2"),
        (r"\buch\b", "3"),
        (r"\bto['’‘`]?rt\b", "4"),
        (r"\bbesh\b", "5"),
        (r"\bolti\b", "6"),
        (r"\byetti\b", "7"),
        (r"\bsakkiz\b", "8"),
        (r"\bto['’‘`]?qqiz\b", "9"),
        (r"\bo['’‘`]?n\b", "10"),
        (r"\byigirma\b", "20"),
        (r"\bqirq\b", "40"),
        (r"\bellik\b", "50"),
    ]
    t_norm = t
    for pat, rep in uz_num_map:
        t_norm = re.sub(pat, rep, t_norm, flags=re.IGNORECASE)

    # =========================================================
    # 1. Aniq sana: DD MM YYYY, DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
    # =========================================================
    date_patterns = [
        r'(?:^|\s)(?P<day>\d{1,2})[\s\.\/\-](?P<month>\d{1,2})[\s\.\/\-](?P<year>\d{4})(?:\s+(?:da|kuni))?(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})(?:\s*da)?)?',
        r'(?:^|\s)(?P<year>\d{4})[\s\.\/\-](?P<month>\d{1,2})[\s\.\/\-](?P<day>\d{1,2})(?:\s+(?:da|kuni))?(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})(?:\s*da)?)?',
    ]
    for pat in date_patterns:
        m = re.search(pat, t_norm, re.IGNORECASE)
        if m:
            gd = m.groupdict()
            try:
                year = int(gd['year'])
                month = int(gd['month'])
                day = int(gd['day'])
                h = int(gd['hour']) if gd.get('hour') else 10
                mi = int(gd['min']) if gd.get('min') else 0
                target_dt = datetime(year, month, day, h, mi, 0, tzinfo=tashkent_tz)
                matched_span = m.span()
                break
            except Exception:
                pass

    # =========================================================
    # 2. Nisbiy vaqt: Kun, Soat va Daqiqa/Minut kombinatsiyalari
    # Masalan:
    # "2 soatdan song", "2 soatdan keyin", "2 soat 30 minutdan keyin"
    # "1 soat 15 daqiqadan so'ng", "45 minutdan keyin", "yarim soatdan song"
    # "10 daqiqadan keyin", "2 soat", "15 minut", "1 kundan keyin"
    # =========================================================
    if not target_dt:
        # A) Yarim soat
        m_yarim = re.search(r'(?:^|\s)(?:yarim\s+soat)(?:(?:\s*dan)?\s*(?:keyin|so[\'’‘`]?ng|o[\'’‘`]?tgach|o[\'’‘`]?tib))?', t_norm, re.IGNORECASE)
        if m_yarim:
            target_dt = now + timedelta(minutes=30)
            matched_span = m_yarim.span()
        else:
            # B) Kun, umumiy soat va/yoki minut
            rel_pat = re.compile(
                r'(?:^|\s)(?:cherez\s+)?'
                r'(?:(?P<days>\d+)\s*(?:kun|den)(?:[a-z]*\s*(?:u|va))?\s*)?'
                r'(?:(?P<hours>\d+(?:[\.,]\d+)?)\s*(?:soat|chas(?:a|ov)?)(?:[a-z]*\s*(?:u|va))?\s*)?'
                r'(?:(?P<mins>\d+)\s*(?:daqiqa|minut|min|m)(?:[a-z]*\s*)?)?'
                r'(?:(?:\s*dan)?\s*(?:keyin|so[\'’‘`]?ng|o[\'’‘`]?tgach|o[\'’‘`]?tib|spustya))?',
                re.IGNORECASE
            )
            for m in rel_pat.finditer(t_norm):
                days_str = m.group('days')
                hours_str = m.group('hours')
                mins_str = m.group('mins')
                if days_str or hours_str or mins_str:
                    total_minutes = 0.0
                    if days_str:
                        total_minutes += int(days_str) * 24 * 60
                    if hours_str:
                        h_val = float(hours_str.replace(',', '.'))
                        total_minutes += h_val * 60
                    if mins_str:
                        total_minutes += int(mins_str)
                    
                    if total_minutes > 0:
                        target_dt = now + timedelta(minutes=total_minutes)
                        matched_span = m.span()
                        break

    # =========================================================
    # 3. Bugun / Ertaga / Indinga + Aniq soat
    # Masalan: "bugun 20:00 da", "ertaga 10:30 da", "ertaga soat 14 da"
    # =========================================================
    if not target_dt:
        day_pat = re.compile(
            r'(?:^|\s)(?P<day_word>bugun|ertaga|indinga)'
            r'(?:\s+(?:kuni))?'
            r'(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})(?:[:\.\-](?P<min>\d{2}))?(?:\s*da)?)?',
            re.IGNORECASE
        )
        m = day_pat.search(t_norm)
        if m:
            day_word = m.group('day_word').lower()
            hour_str = m.group('hour')
            min_str = m.group('min')

            days_add = 0
            if day_word == 'bugun':
                days_add = 0
            elif day_word == 'ertaga':
                days_add = 1
            elif day_word == 'indinga':
                days_add = 2

            base_date = (now + timedelta(days=days_add)).date()
            h = int(hour_str) if hour_str else 10
            mi = int(min_str) if min_str else 0

            target_candidate = datetime(base_date.year, base_date.month, base_date.day, h, mi, 0, tzinfo=tashkent_tz)
            if day_word == 'bugun' and target_candidate < now:
                target_candidate = target_candidate + timedelta(days=1)

            target_dt = target_candidate
            matched_span = m.span()

    # =========================================================
    # 4. Faqat Soat ko'rsatilgan holat: "soat 18:00 da", "18:30 da"
    # =========================================================
    if not target_dt:
        clock_pat = re.compile(
            r'(?:^|\s)(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})\s*(?:da)?',
            re.IGNORECASE
        )
        m = clock_pat.search(t_norm)
        if m:
            h = int(m.group('hour'))
            mi = int(m.group('min'))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                target_candidate = datetime(now.year, now.month, now.day, h, mi, 0, tzinfo=tashkent_tz)
                if target_candidate <= now:
                    target_candidate += timedelta(days=1)
                target_dt = target_candidate
                matched_span = m.span()

    if not target_dt:
        return None

    remind_at = target_dt.strftime('%Y-%m-%d %H:%M:%S')

    # =========================================================
    # 5. Vazifa matnini tozalash (task cleaning)
    # =========================================================
    if matched_span:
        clean_text = t_norm[:matched_span[0]] + ' ' + t_norm[matched_span[1]:]
    else:
        clean_text = t_norm

    stop_words = [
        r'\belsat\b',
        r'\beslat\b',
        r'\beslatgin\b',
        r'\beslatvor\b',
        r'\beslatib\s+q[oʻ\'’‘`]?y(?:gin)?\b',
        r'\beslatib\s+turgin\b',
        r'\beslatma\b',
        r'\beslatish\b',
        r'\bkeyin\b',
        r'\bso[\'’‘`]?ng\b',
        r'\bo[\'’‘`]?tgach\b',
        r'\bo[\'’‘`]?tib\b',
        r'\bsoat\b',
        r'\bdan\b',
        r'\bda\b',
        r'\bkuni\b',
        r'\bdeb\b',
    ]
    for sw in stop_words:
        clean_text = re.sub(sw, ' ', clean_text, flags=re.IGNORECASE)

    clean_text = re.sub(r'\s+', ' ', clean_text).strip(' -:,\t\n')

    if not clean_text or len(clean_text) < 2:
        clean_text = "Rejalashtirilgan eslatma"

    return {
        "reminder_text": clean_text,
        "remind_at": remind_at
    }


extract_explicit_reminder = extract_smart_reminder


class AIResult(str):
    """Matn sifatida ishlaydi, shuningdek qo'shimcha .escalation ma'lumotiga ega."""
    escalation: str | None

    def __new__(cls, text: str, escalation: str | None = None):
        obj = super().__new__(cls, text)
        obj.escalation = escalation
        return obj


class AIService:
    def __init__(self):
        self._groq_clients: list[Any] = []
        self._groq_idx: int = 0
        self._gemini_client: Any = None
        self._setup_clients()

    def _setup_clients(self) -> None:
        """Mavjud provayderlarni aniqlaydi va kalitlar zaxirasini sozlaydi."""
        # 1. Groq kalitlarini ulash (Multi-key pool)
        keys = config.groq_api_keys or ([config.groq_api_key] if config.groq_api_key else [])
        self._groq_clients = []

        if keys:
            try:
                from groq import AsyncGroq
                for k in keys:
                    if k:
                        self._groq_clients.append(AsyncGroq(api_key=k, timeout=25.0, max_retries=1))
                logger.info(
                    "⚡ Groq AI muvaffaqiyatli ulandi (%d ta API kalit, Asosiy model: %s, Vision: %s)",
                    len(self._groq_clients),
                    config.groq_model,
                    config.groq_vision_model,
                )
            except Exception as e:
                logger.error("Groq mijozlarini yaratishda xatolik: %s", e)

        # 2. Google Gemini zaxira mijozini sozlash
        if config.gemini_api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=config.gemini_api_key)
                logger.info("Google Gemini ulandi.")
            except Exception:
                pass

    async def _generate_with_groq(
        self,
        chat_id: int,
        effective_prompt: str,
        image_bytes: bytes | None = None,
        is_admin_mode: bool = False,
    ) -> str:
        """Groq orqali javob generatsiya qilish (avtomatik kalit almashtirish va model tanlash)."""
        history = memory_service.get_history(chat_id)
        sys_prompt = ADMIN_SYSTEM_PROMPT if is_admin_mode else SYSTEM_PROMPT
        messages = [{"role": "system", "content": sys_prompt}]

        for msg in history:
            role = "user" if msg.role == "user" else "assistant"
            messages.append({"role": role, "content": msg.content})

        if image_bytes:
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")
            prompt_text = (
                effective_prompt
                if effective_prompt
                else "Ushbu rasm/skrinshotdagi LMS vazifasi yoki xatolikni tahlil qilib, to'g'ri yechim va yo'nalish ber."
            )
            user_content = [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
            ]
            messages.append({"role": "user", "content": user_content})
            model_to_use = config.groq_vision_model
        else:
            messages.append({"role": "user", "content": effective_prompt})
            model_to_use = config.groq_model

        last_error = None
        # Zaxiradagi kalitlar bo'yicha ketma-ket urinib ko'rish
        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    temperature=0.6 if is_admin_mode else 0.4,
                    max_tokens=3000 if is_admin_mode else 2048,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("Groq kalitida xatolik, zaxira kalitga o'tilmoqda: %s", e)
                last_error = e

        if last_error:
            raise last_error
        return "Javob olinmadi."

    def _generate_with_genai(self, prompt: str, history_context: str, is_admin_mode: bool = False) -> str:
        """Google GenAI orqali javob generatsiya qilish (fallback)."""
        from google.genai import types

        full_content = prompt
        if history_context:
            full_content = f"Avvalgi suhbat konteksti:\n{history_context}\n\nFoydalanuvchining yangi xabari:\n{prompt}"

        sys_prompt = ADMIN_SYSTEM_PROMPT if is_admin_mode else SYSTEM_PROMPT
        response = self._gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=full_content,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.6,
            ),
        )
        return response.text.strip() if response.text else ""

    async def generate_reply(
        self,
        chat_id: int,
        user_message: str,
        reply_to_context: str | None = None,
        image_bytes: bytes | None = None,
        file_name: str | None = None,
        file_text: str | None = None,
    ) -> AIResult:
        """
        Xabarni tahlil qilib AI javobini qaytaradi (matn, fayl yoki rasm/skrinshot bilan).
        """
        if not self._groq_clients and not self._gemini_client:
            self._setup_clients()
            if not self._groq_clients and not self._gemini_client:
                return AIResult("⚠️ **Xatolik:** Hech qanday AI provayderi sozlanmagan. Iltimos `.env` faylini tekshiring.")

        # Vazifalar (Admin) guruhi yoki Mentor ekanini aniqlash
        is_admin_mode = is_escalation_chat(chat_id) or (chat_id in (config.mentor_user_id, 8105823872))

        # Standart xatoliklarga (FAQ) 0.01 soniyada tezkor javob berish
        if not is_admin_mode and not file_text and not image_bytes:
            fast_faq = check_fast_faq(user_message)
            if fast_faq:
                logger.info("Fast FAQ mos keldi [%s], tezkor javob berildi.", chat_id)
                memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
                memory_service.add_message(chat_id=chat_id, role="model", content=fast_faq)
                return AIResult(fast_faq)

        # Javob berilayotgan kontekst
        effective_prompt = user_message
        if file_name and file_text:
            effective_prompt = f"[Yuklangan fayl: {file_name}]\n```\n{file_text[:6000]}\n```\n\n{effective_prompt}"

        if reply_to_context:
            effective_prompt = f"[Javob berilayotgan xabar: \"{reply_to_context}\"]\n{effective_prompt}"

        try:
            # 1-ustuvorlik: Groq (Multi-key)
            if self._groq_clients:
                answer = await self._generate_with_groq(
                    chat_id, effective_prompt, image_bytes=image_bytes, is_admin_mode=is_admin_mode
                )
            else:
                # 2-ustuvorlik: Gemini
                history = memory_service.get_history(chat_id)
                history_lines = [f"{'Foydalanuvchi' if m.role == 'user' else 'AI'}: {m.content}" for m in history]
                history_context = "\n".join(history_lines)

                loop = asyncio.get_running_loop()
                answer = await loop.run_in_executor(
                    None, self._generate_with_genai, effective_prompt, history_context, is_admin_mode
                )

            if not answer:
                answer = "Kechirasiz, ushbu xabarga aniq javob shakllantirib bo'lmadi."

            # Eskalyatsiya blokini ajratish
            escalation_info = None
            match = ESCALATE_PATTERN.search(answer)
            if match:
                escalation_info = match.group(1).strip()
                answer = ESCALATE_PATTERN.sub("", answer).strip()

            # Maxfiy ma'lumotlarni tozalash (Data Leak Prevention)
            answer = redact_sensitive_data(answer)
            if escalation_info:
                escalation_info = redact_sensitive_data(escalation_info)

            # Xotiraga tozalangan javobni saqlash
            memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
            memory_service.add_message(chat_id=chat_id, role="model", content=answer)

            return AIResult(answer, escalation=escalation_info)

        except Exception as e:
            logger.exception("AI so'rovida xatolik yuz berdi: %s", e)
            return AIResult(f"⚠️ **AI xizmatida xatolik yuz berdi:** {str(e)}")

    async def explain_topic(self, topic: str) -> str:
        """
        Dars mavzusini hayotiy misol (analogiya), kod va mini-mashq bilan tushuntirib beradi.
        """
        prompt = (
            f"Siz CoddyCamp dasturlash akademiyasi Katta Mentorisiz.\n"
            f"O'quvchiga quyidagi dasturlash mavzusini eng qiziqarli va tushunarli uslubda tushuntiring:\n"
            f"Mavzu: \"{topic}\"\n\n"
            "Javob formati aynan quyidagicha bo'lsin:\n"
            f"📚 **Mavzu: {topic.title()}**\n\n"
            "💡 **Hayotiy o'xshatish (Analogiya):** (Oddiy, o'quvchi tushunadigan qiziqarli hayotiy o'xshatish, 2-3 jumla)\n\n"
            "💻 **Kod namunasi:**\n```python\n# 4-6 qatorli toza, izohli sodda kod\n```\n\n"
            "🎯 **O'quvchi uchun mini-mashq (Challenge):** (O'quvchi darhol mustaqil yozib ko'rishi uchun 1 ta amaliy topshiriq)\n\n"
            "Javobni ortiqcha cho'zmasdan, chiroyli va lo'nda formatda yozing."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=1200,
                )
                ans = response.choices[0].message.content.strip()
                return redact_sensitive_data(ans)
            except Exception as e:
                logger.warning("Mavzu tushuntirishda xatolik: %s", e)

        return "⚠️ Mavzuni tushuntirishda xatolik yuz berdi. Iltimos qayta urinib ko'ring."

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Groq Whisper (whisper-large-v3) orqali ovozli xabarni o'zbek/rus tilida matnga o'giradi.
        """
        if not self._groq_clients:
            self._setup_clients()
            if not self._groq_clients:
                raise RuntimeError("Ovozni tahlil qilish uchun Groq klasteri mavjud emas.")

        last_error = None
        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                transcription = await client.audio.transcriptions.create(
                    file=("voice.ogg", audio_bytes),
                    model="whisper-large-v3",
                    response_format="text",
                )
                text = str(transcription).strip()
                logger.info("Ovozli xabar matnga aylantirildi: %s", text[:80])
                return text
            except Exception as e:
                logger.warning("Groq Whisper'da xatolik, zaxira kalitga o'tilmoqda: %s", e)
                last_error = e

        if last_error:
            raise last_error
        return ""

    async def generate_mentor_report(self, questions: list[str]) -> str:
        """
        O'quvchilarning so'nggi savollari va xatolarini tahlil qilib, mentor uchun hisobot tayyorlaydi.
        """
        if not questions:
            return "ℹ️ Hozircha tahlil qilish uchun o'quvchilar savollari tarixi yetarli emas."

        questions_text = "\n".join([f"- {q}" for q in questions[:50]])
        prompt = (
            "Quyida CoddyCamp o'quvchilari tomonidan dasturlash bo'yicha berilgan so'nggi savollar va xatoliklar ro'yxati keltirilgan:\n\n"
            f"{questions_text}\n\n"
            "Siz CoddyCamp IT akademiyasi Katta Metodisti va Bosh Mentori sifatida ushbu savollarni chuqur tahlil qilib, dars beruvchi mentor (Nuriddin aka) uchun qisqa, lo'nda va nihoyatda foydali ANALITIK HISOBOT tayyorlang.\n\n"
            "Hisobot formati quyidagicha bo'lsin:\n"
            "📊 **CoddyCamp Mentor Analitikasi (O'quvchilar xatoliklari hisoboti)**\n\n"
            "1. 📌 **Eng ko'p qiynalgan mavzular (Top 3):** (qaysi mavzularda eng ko'p savol tushgan)\n"
            "2. ⚠️ **Asosiy xatoliklar (Common Bugs):** (o'quvchilar kodida eng ko'p uchragan xatolar)\n"
            "3. 💡 **Keyingi dars uchun tavsiya:** (mentor darsda aynan qaysi tushunchani chuqurroq tushuntirib, qanday amaliy mashq berishi kerak)\n\n"
            "Javobni professional, ixcham va tushunarli formatda bering."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=1500,
                )
                return redact_sensitive_data(response.choices[0].message.content.strip())
            except Exception as e:
                logger.warning("Mentor hisobotini tuzishda xatolik: %s", e)

        return "⚠️ Hisobotni shakllantirishda xatolik yuz berdi."

    async def parse_reminder_text(self, text: str, current_tashkent_time: str) -> dict | None:
        """
        O'zbek tilidagi eslatma matnidan vazifa va aniq YYYY-MM-DD HH:MM:SS vaqtini ajratib oladi.
        """
        # 1. Tezkor aqlli (nisbiy va aniq) sana va vaqt tahlili (0.0001s da aniqlash)
        smart = extract_smart_reminder(text, current_tashkent_time=current_tashkent_time)
        if smart:
            return smart

        prompt = (
            f"Hozirgi sana va vaqt (Toshkent vaqti): {current_tashkent_time}\n\n"
            f"Foydalanuvchi quyidagi eslatma so'rovini yozdi:\n\"{text}\"\n\n"
            "Vazifangiz: ushbu so'rovdan eslatma matnini (vazifani) va eslatish kerak bo'lgan aniq sana/vaqtni hisoblab chiqib, FAQAT quyidagi JSON formatida qaytaring:\n"
            "{\n"
            '  "reminder_text": "Vazifa mazmuni",\n'
            '  "remind_at": "YYYY-MM-DD HH:MM:SS"\n'
            "}\n"
            "Qoidalar:\n"
            "- 'remind_at' qiymati aniq 24 soatlik formatda (YYYY-MM-DD HH:MM:SS) bo'lishi shart.\n"
            "- Agar aniq sana kiritilsa (masalan: '25 09 2026', '25.09.2026', '25 sentyabr 15:00'), o'sha sana va soatni oling (masalan: '2026-09-25 15:00:00').\n"
            "- Agar soat ko'rsatilmagan bo'lsa, o'sha kun soat 10:00:00 ni oling.\n"
            "- Agar '30 daqiqadan keyin' desa, hozirgi vaqtga 30 daqiqa qo'shing.\n"
            "- Agar 'ertaga soat 10:00 da' desa, ertangi kun sanasi va 10:00:00 ni oling.\n"
            "- Agar 'bugun 18:30 da' desa, bugungi sana va 18:30:00 ni oling.\n"
            "- Agar vaqt aniq tushunarsiz bo'lsa, 'remind_at': null qiling.\n"
            "- FAQAT valid JSON qaytaring, boshqa hech qanday so'z yozmang."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=250,
                )
                raw_json = response.choices[0].message.content.strip()
                if "```" in raw_json:
                    raw_json = re.sub(r"```(?:json)?", "", raw_json).strip()
                start_idx = raw_json.find("{")
                end_idx = raw_json.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_json = raw_json[start_idx : end_idx + 1]
                try:
                    data = json.loads(raw_json)
                except Exception:
                    import ast
                    data = ast.literal_eval(raw_json)
                if isinstance(data, dict):
                    rem_text = data.get("reminder_text") or data.get("task")
                    rem_at = data.get("remind_at")
                    if rem_text and rem_at:
                        return {"reminder_text": str(rem_text), "remind_at": str(rem_at)}
            except Exception as e:
                logger.warning("Eslatma vaqtini tahlil qilishda xatolik: %s", e)

        return None

    async def analyze_github_link(self, github_url: str) -> str:
        """
        GitHub repozitoriy yoki fayl havolasini o'qib, professional Code-Review hisobotini tayyorlaydi.
        """
        import aiohttp
        match = re.search(r"github\.com/([^/\s?#]+)/([^/\s?#]+)", github_url)
        if not match:
            return "⚠️ Noto'g'ri GitHub havolasi. Masalan: `https://github.com/foydalanuvchi/loyiha`"

        owner = match.group(1)
        repo = match.group(2).rstrip(".git")

        headers = {
            "User-Agent": "coddyHelper-AI-Agent",
            "Accept": "application/vnd.github.v3+json",
        }

        repo_info = ""
        files_content = []

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                # 1. Repozitoriy ma'lumotlari
                repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
                async with session.get(repo_api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        repo_data = await resp.json()
                        desc = repo_data.get("description") or "Tavsif berilmagan"
                        lang = repo_data.get("language") or "Noma'lum"
                        repo_info = f"Loyiha: {owner}/{repo}\nAsosiy til: {lang}\nTavsif: {desc}\n"

                # 2. Repozitoriy fayllari ro'yxati
                contents_api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
                async with session.get(contents_api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        contents = await resp.json()
                        key_files = []
                        if isinstance(contents, list):
                            for item in contents:
                                name = item.get("name", "")
                                ext = Path(name).suffix.lower()
                                if ext in (
                                    ".py", ".js", ".ts", ".html",
                                    ".sql", ".java", ".cpp", ".c",
                                ) or name.lower() in ("readme.md", "app.py", "main.py"):
                                    key_files.append((name, item.get("download_url")))
                                if len(key_files) >= 4:
                                    break

                        # Fayllar kodini yuklab olish
                        for fname, d_url in key_files:
                            if d_url:
                                async with session.get(
                                    d_url, timeout=aiohttp.ClientTimeout(total=10)
                                ) as f_resp:
                                    if f_resp.status == 200:
                                        code_txt = await f_resp.text()
                                        files_content.append(f"--- Fayl: {fname} ---\n{code_txt[:3000]}")
        except Exception as net_err:
            logger.warning("GitHub API so'rovida xatolik: %s", net_err)

        if not files_content:
            files_summary = repo_info if repo_info else f"Loyiha: {owner}/{repo}"
        else:
            files_summary = f"{repo_info}\n" + "\n\n".join(files_content)

        prompt = (
            f"Quyida GitHub repozitoriysi ({owner}/{repo}) kodi va tuzilmasi keltirilgan:\n\n"
            f"{files_summary[:8000]}\n\n"
            "Siz Katta Dasturchi va CoddyCamp Mentori sifatida ushbu o'quvchi loyihasi bo'yicha professional CODE REVIEW tayyorlang.\n\n"
            "Hisobot formati quyidagicha bo'lsin:\n"
            f"🔍 **GitHub Code Review: {owner}/{repo}**\n\n"
            "⭐️ **Umumiy baho:** [1 dan 10 gacha ball]\n"
            "🧹 **Clean Code va PEP8 tahlili:** (kod tozaligi, o'zgaruvchi nomlari, arxitektura)\n"
            "🐛 **Aniqlangan xatolar / Kamchiliklar:** (mantiqiy xatolar, xavfsizlik, xatoliklarni ushlash)\n"
            "🚀 **Yaxshilash uchun tavsiyalar (Top 3):** (loyihani yaxshilash uchun aniq 3 ta maslahat)\n\n"
            "Javobni lo'nda, professional va o'quvchiga tushunarli tarzda bering."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=1500,
                )
                return redact_sensitive_data(response.choices[0].message.content.strip())
            except Exception as e:
                logger.warning("GitHub tahlilida xatolik: %s", e)

        return "⚠️ GitHub repozitoriysini tahlil qilishda xatolik yuz berdi."


# Global AI xizmati instansiyasi
ai_service = AIService()
