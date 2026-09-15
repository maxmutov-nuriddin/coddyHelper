"""
services/autonomous_brain_service.py
4-Miya: Avtonom O'rganuvchi va Fikrlovchi Dvigatel (Autonomous Pre-Cognition Brain).
Orqa fonda to'xtovsiz ishlaydi (Background Daemon):
- O'quvchilar va guruhlardagi savollarni tahlil qiladi.
- Bilimlar bazasini kengaytiradi (Autonomous Insights).
- Kelgusida so'ralishi mumkin bo'lgan savollarga mukammal yechimlarni oldindan tayyorlab keshga joylaydi (Pre-computation Cache).
- Faqat Miya 4 uchun ajratilgan mustaqil kalitlardan foydalanadi (jonli chatlarga 0% ta'sir).
"""

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from services.memory_service import memory_service

logger = logging.getLogger(__name__)


def _get_tashkent_now_str() -> str:
    try:
        tz = ZoneInfo("Asia/Tashkent")
        return datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


class AutonomousBrainService:
    """Orqa fonda to'xtovsiz tafakkur qiluvchi va o'rganuvchi 4-Miya xizmati."""

    def __init__(self):
        self._is_running = False
        self._task: asyncio.Task | None = None
        self._cycle_count: int = 0
        self._insights_generated: int = 0
        self._answers_precomputed: int = 0
        self._last_run_time: str = "Hali ishga tushmadi"
        self._last_error: str | None = None

    def get_status(self) -> dict[str, Any]:
        """Web App paneli va telemetriya uchun Miya 4 holati."""
        return {
            "is_running": self._is_running,
            "cycle_count": self._cycle_count,
            "insights_generated": self._insights_generated,
            "answers_precomputed": self._answers_precomputed,
            "last_run_time": self._last_run_time,
            "last_error": self._last_error,
        }

    async def start(self, client=None) -> None:
        """Background daemoni ishga tushirish."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(client))
        logger.info("🧬 Miya 4: Avtonom Tafakkur Dvigateli (Autonomous Cogitation Daemon) ishga tushirildi.")

    async def stop(self) -> None:
        """Background daemoni to'xtatish."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🧬 Miya 4 to'xtatildi.")

    async def _run_loop(self, client=None) -> None:
        """Doimiy orqa fon tahlil va fikrlash davri."""
        # Bot ishga tushganda birinchi 60 soniya sokin kutish (bot to'liq yuklanishi uchun):
        await asyncio.sleep(60)

        while self._is_running:
            try:
                self._last_run_time = _get_tashkent_now_str()
                self._cycle_count += 1
                logger.info("🧬 Miya 4 tafakkur davri boshlandi (Davr #%d)...", self._cycle_count)

                # 1. Sikl: O'quvchilarning so'nggi savollaridan xulosa va saboq chiqarish
                await self._synthesize_insights()

                # 2. Sikl: Keyinchalik so'ralishi mumkin bo'lgan savollarga oldindan yechim tayyorlash
                await self._precompute_upcoming_answers()

                self._last_error = None
                logger.info(
                    "🧬 Miya 4 davri yakunlandi: Jami %d saboq, %d kesh yechim tayyorlandi.",
                    self._insights_generated,
                    self._answers_precomputed,
                )

                # Har bir chuqur tafakkur davridan so'ng 7 daqiqa oraliq (420 soniya):
                await asyncio.sleep(420)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = str(e)
                logger.warning("Miya 4 tafakkur davrida ogohlantirish: %s", e)
                # Xatolik bo'lsa 60 soniya kutib davom etish
                await asyncio.sleep(60)

    async def _synthesize_insights(self) -> None:
        """So'nggi savollardan umumiy saboq va tavsiyalar sintezi."""
        from services.ai_service import ai_service
        questions = memory_service.get_recent_user_questions(limit=8)
        if not questions or len(questions) < 2:
            return

        q_list_str = "\n".join(f"- {q}" for q in questions[:6])
        prompt = (
            "Siz CoddyCamp IT akademiyasi o'quv markazining Avtonom Tafakkur Miyasisiz (Miya 4).\n"
            "Quyida o'quvchilar va guruhlardan kelgan so'nggi savollar berilgan:\n"
            f"{q_list_str}\n\n"
            "Vazifa: Ushbu savollar asosida o'quvchilar eng ko'p qaysi mavzuda qiynalayotganini aniqlang va "
            "bitta muhim amaliy tushuntirish/xulosa (insight) chiqaring.\n"
            "Javobingizni quyidagi aniq formatda bering:\n"
            "MAVZU: [Mavzu nomi]\n"
            "XULOSA: [1-2 ta lo'nda, foydali, aniq qoida yoki dasturlash tushuntirishi]"
        )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply:
            return

        topic = "Dasturlash sabog'i"
        content = reply.strip()
        if "MAVZU:" in reply and "XULOSA:" in reply:
            try:
                parts = reply.split("XULOSA:", 1)
                topic = parts[0].replace("MAVZU:", "").strip()
                content = parts[1].strip()
            except Exception:
                pass

        if content and len(content) >= 15:
            memory_service.add_autonomous_insight(topic[:50], content)
            self._insights_generated += 1
            logger.info("✅ Miya 4 yangi saboq kashf qildi: [%s]", topic[:30])

    async def _precompute_upcoming_answers(self) -> None:
        """Keyinchalik so'ralishi mumkin bo'lgan savollarga oldindan yechim tayyorlash."""
        from services.ai_service import ai_service
        core_topics = [
            "Python ro'yxatlar (lists) va metodlar",
            "Python funksiyalar (def, return, args)",
            "Python sikllar (for, while) xatolari",
            "Telegram bot (Telethon, Aiogram) asinxron xatolar",
            "SQL va SQLite baza ulanish xatolari",
            "Python string metodlari va formatlash",
            "LMS dasturlash topshiriqlari tahlili",
        ]
        topic = core_topics[self._cycle_count % len(core_topics)]

        prompt = (
            f"Siz CoddyCamp IT akademiyasining Avtonom Tafakkur Miyasisiz.\n"
            f"Mavzu: '{topic}'\n"
            "O'quvchilar ushbu mavzuda eng ko'p so'raydigan yoki kelgusida so'rashi mumkin bo'lgan 1 ta qiyin savolni bashorat qiling "
            "va unga ideal, to'liq kodli, tushunarli yechim tayyorlang.\n"
            "Javobni quyidagi aniq formatda bering:\n"
            "SAVOL: [O'quvchi berishi mumkin bo'lgan savol yoki xato matni]\n"
            "YECHIM: [Mukammal, qisqa va to'g'ri kodli javob]"
        )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply:
            return

        if "SAVOL:" in reply and "YECHIM:" in reply:
            try:
                parts = reply.split("YECHIM:", 1)
                q_pattern = parts[0].replace("SAVOL:", "").strip()
                answer_code = parts[1].strip()
                if q_pattern and answer_code:
                    memory_service.add_precomputed_answer(topic, q_pattern, answer_code)
                    self._answers_precomputed += 1
                    logger.info("✅ Miya 4 oldindan yechim tayyorlab qo'ydi: [%s] -> %s", topic, q_pattern[:35])
            except Exception as e:
                logger.debug("Pre-compute javobini ajratishda ogohlantirish: %s", e)


autonomous_brain_service = AutonomousBrainService()
