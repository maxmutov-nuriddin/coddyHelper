"""
AI integratsiyasi (Groq Multi-Key va Google Gemini qo'llab-quvvatlanadi)
"""

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any
from config import config
from prompts import SYSTEM_PROMPT
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

ESCALATE_PATTERN = re.compile(r"<<<ESCALATE>>>(.*?)<<<END_ESCALATE>>>", re.DOTALL)


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
                        self._groq_clients.append(AsyncGroq(api_key=k))
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
    ) -> str:
        """Groq orqali javob generatsiya qilish (avtomatik kalit almashtirish va model tanlash)."""
        history = memory_service.get_history(chat_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for msg in history:
            role = "user" if msg.role == "user" else "assistant"
            messages.append({"role": role, "content": msg.content})

        if image_bytes:
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")
            prompt_text = (
                effective_prompt
                if effective_prompt
                else "Ushbu rasm/skrinshotdagi LMS vazifasi yoki xatolikni tahlil qilib, o'quvchiga to'g'ri yechim va yo'nalish ber."
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
                    temperature=0.6,
                    max_tokens=2048,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("Groq kalitida xatolik, zaxira kalitga o'tilmoqda: %s", e)
                last_error = e

        if last_error:
            raise last_error
        return "Javob olinmadi."

    def _generate_with_genai(self, prompt: str, history_context: str) -> str:
        """Google GenAI orqali javob generatsiya qilish (fallback)."""
        from google.genai import types

        full_content = prompt
        if history_context:
            full_content = f"Avvalgi suhbat konteksti:\n{history_context}\n\nFoydalanuvchining yangi xabari:\n{prompt}"

        response = self._gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=full_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
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

        # Javob berilayotgan kontekst
        effective_prompt = user_message
        if file_name and file_text:
            effective_prompt = f"[Yuklangan fayl: {file_name}]\n```\n{file_text[:6000]}\n```\n\n{effective_prompt}"

        if reply_to_context:
            effective_prompt = f"[Javob berilayotgan xabar: \"{reply_to_context}\"]\n{effective_prompt}"

        try:
            # 1-ustuvorlik: Groq (Multi-key)
            if self._groq_clients:
                answer = await self._generate_with_groq(chat_id, effective_prompt, image_bytes=image_bytes)
            else:
                # 2-ustuvorlik: Gemini
                history = memory_service.get_history(chat_id)
                history_lines = [f"{'Foydalanuvchi' if m.role == 'user' else 'AI'}: {m.content}" for m in history]
                history_context = "\n".join(history_lines)

                loop = asyncio.get_running_loop()
                answer = await loop.run_in_executor(
                    None, self._generate_with_genai, effective_prompt, history_context
                )

            if not answer:
                answer = "Kechirasiz, ushbu xabarga aniq javob shakllantirib bo'lmadi."

            # Eskalyatsiya blokini ajratish
            escalation_info = None
            match = ESCALATE_PATTERN.search(answer)
            if match:
                escalation_info = match.group(1).strip()
                answer = ESCALATE_PATTERN.sub("", answer).strip()

            # Xotiraga tozalangan javobni saqlash
            memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
            memory_service.add_message(chat_id=chat_id, role="model", content=answer)

            return AIResult(answer, escalation=escalation_info)

        except Exception as e:
            logger.exception("AI so'rovida xatolik yuz berdi: %s", e)
            return AIResult(f"⚠️ **AI xizmatida xatolik yuz berdi:** {str(e)}")

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
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("Mentor hisobotini tuzishda xatolik: %s", e)

        return "⚠️ Hisobotni shakllantirishda xatolik yuz berdi."

    async def parse_reminder_text(self, text: str, current_tashkent_time: str) -> dict | None:
        """
        O'zbek tilidagi eslatma matnidan vazifa va aniq YYYY-MM-DD HH:MM:SS vaqtini ajratib oladi.
        """
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
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("GitHub tahlilida xatolik: %s", e)

        return "⚠️ GitHub repozitoriysini tahlil qilishda xatolik yuz berdi."


# Global AI xizmati instansiyasi
ai_service = AIService()
