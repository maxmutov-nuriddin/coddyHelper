"""
AI integratsiyasi (Groq Multi-Key va Google Gemini qo'llab-quvvatlanadi)
"""

import asyncio
import base64
import logging
import re
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
    ) -> AIResult:
        """
        Xabarni tahlil qilib AI javobini qaytaradi (matn yoki rasm/skrinshot bilan).
        """
        if not self._groq_clients and not self._gemini_client:
            self._setup_clients()
            if not self._groq_clients and not self._gemini_client:
                return AIResult("⚠️ **Xatolik:** Hech qanday AI provayderi sozlanmagan. Iltimos `.env` faylini tekshiring.")

        # Javob berilayotgan kontekst
        effective_prompt = user_message
        if reply_to_context:
            effective_prompt = f"[Javob berilayotgan xabar: \"{reply_to_context}\"]\n{user_message}"

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


# Global AI xizmati instansiyasi
ai_service = AIService()
