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
        return datetime.now(tz).strftime("%H:%M:%S (%d.%m.%Y)")
    except Exception:
        return datetime.now().strftime("%H:%M:%S (%d.%m.%Y)")


def _get_tashkent_time_only() -> str:
    try:
        tz = ZoneInfo("Asia/Tashkent")
        return datetime.now(tz).strftime("%H:%M:%S")
    except Exception:
        return datetime.now().strftime("%H:%M:%S")


class AutonomousBrainService:
    """Orqa fonda to'xtovsiz tafakkur qiluvchi va o'rganuvchi 4-Miya xizmati."""

    def __init__(self):
        self._is_running = False
        self._is_busy = False
        self._task: asyncio.Task | None = None
        self._cycle_count: int = 0
        self._insights_generated: int = 0
        self._answers_precomputed: int = 0
        self._last_run_time: str = "Hali ishga tushmadi"
        self._next_run_estimated: str = "Kutilmoqda..."
        self._current_activity: str = "Tizim ishga tushirilishi kutilmoqda..."
        self._last_error: str | None = None
        self._recent_insights: list[dict[str, Any]] = []
        self._recent_precomputations: list[dict[str, Any]] = []
        self._activity_logs: list[dict[str, str]] = []

    def _log_activity(self, text: str, action_type: str = "info") -> None:
        entry = {
            "time": _get_tashkent_time_only(),
            "text": text,
            "type": action_type,
        }
        self._activity_logs.append(entry)
        if len(self._activity_logs) > 40:
            self._activity_logs = self._activity_logs[-40:]

    def get_status(self) -> dict[str, Any]:
        """Web App paneli va telemetriya uchun Miya 4 holati."""
        return {
            "is_running": self._is_running,
            "is_busy": self._is_busy,
            "cycle_count": self._cycle_count,
            "insights_generated": self._insights_generated,
            "answers_precomputed": self._answers_precomputed,
            "last_run_time": self._last_run_time,
            "next_run_estimated": self._next_run_estimated,
            "current_activity": self._current_activity,
            "last_error": self._last_error,
            "recent_insights": self._recent_insights[-6:],
            "recent_precomputations": self._recent_precomputations[-6:],
            "activity_logs": list(reversed(self._activity_logs[-15:])),
        }

    async def start(self, client=None) -> None:
        """Background daemoni ishga tushirish."""
        if self._is_running:
            return
        self._is_running = True
        self._log_activity("Miya 4 avtonom dvigateli yuklanmoqda...", "start")
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
        self._log_activity("Miya 4 to'xtatildi.", "stop")
        logger.info("🧬 Miya 4 to'xtatildi.")

    async def run_cycle_now(self) -> dict[str, Any]:
        """Web App panelidan zudlik bilan qo'lda tafakkur siklini ishga tushirish."""
        if self._is_busy:
            return {
                "ok": False,
                "message": "Miya 4 ayni paytda allaqachon tahlil bilan band. Iltimos, 15 soniya kuting.",
                "status": self.get_status(),
            }

        try:
            self._is_busy = True
            self._current_activity = "Mentor so'rovi bo'yicha zudlik bilan tafakkur sikli boshlandi..."
            self._log_activity("⚡ Qo'lda yangi tafakkur sikli ishga tushirildi!", "trigger")
            
            await self._synthesize_insights()
            await self._precompute_upcoming_answers()
            
            self._cycle_count += 1
            self._last_run_time = _get_tashkent_now_str()
            self._current_activity = f"Sikl muvaffaqiyatli yakunlandi ({self._last_run_time})."
            self._log_activity(f"✅ Sikl #{self._cycle_count} muvaffaqiyatli bajarildi.", "success")
            return {
                "ok": True,
                "message": f"Miya 4 muvaffaqiyatli fikrlab chiqdi! Jami saboqlar: {self._insights_generated}, Kesh yechimlar: {self._answers_precomputed}",
                "status": self.get_status(),
            }
        except Exception as e:
            self._last_error = str(e)
            self._log_activity(f"Xatolik: {e}", "error")
            return {
                "ok": False,
                "error": str(e),
                "status": self.get_status(),
            }
        finally:
            self._is_busy = False

    async def _run_loop(self, client=None) -> None:
        """Doimiy orqa fon tahlil va fikrlash davri."""
        # Bot ishga tushganda 5 soniya sokin kutish (sozlamalar yuklanishi uchun):
        self._current_activity = "Tizim modullari tekshirilmoqda (5s)..."
        await asyncio.sleep(5)

        while self._is_running:
            try:
                self._is_busy = True
                self._last_run_time = _get_tashkent_now_str()
                self._cycle_count += 1
                self._current_activity = f"Sikl #{self._cycle_count}: O'quvchilar xatolari va amaliy bilimlar tahlili..."
                self._log_activity(f"🧬 Sikl #{self._cycle_count} boshlandi...", "cycle")
                logger.info("🧬 Miya 4 tafakkur davri boshlandi (Davr #%d)...", self._cycle_count)

                # 1. Sikl: O'quvchilarning so'nggi savollaridan xulosa va saboq chiqarish
                await self._synthesize_insights()

                # So'rovlar orasida Groq TPM xotirjam bo'lishi uchun 4s tanaffus:
                await asyncio.sleep(4.0)

                # 2. Sikl: Keyinchalik so'ralishi mumkin bo'lgan savollarga oldindan yechim tayyorlash
                await self._precompute_upcoming_answers()

                self._last_error = None
                self._is_busy = False
                
                # Keyingi sikl vaqti (1200 soniya / 20 daqiqa):
                try:
                    from datetime import timedelta
                    tz = ZoneInfo("Asia/Tashkent")
                    next_time = (datetime.now(tz) + timedelta(seconds=1200)).strftime("%H:%M:%S")
                    self._next_run_estimated = f"{next_time} da"
                except Exception:
                    self._next_run_estimated = "20 daqiqadan so'ng"

                self._current_activity = f"Sokin rejimda. Keyingi tafakkur sikli: {self._next_run_estimated}"
                self._log_activity(f"Sikl yakunlandi. Jami: {self._insights_generated} saboq, {self._answers_precomputed} kesh yechim.", "info")
                logger.info(
                    "🧬 Miya 4 davri yakunlandi: Jami %d saboq, %d kesh yechim tayyorlandi.",
                    self._insights_generated,
                    self._answers_precomputed,
                )

                # Har bir chuqur tafakkur davridan so'ng 20 daqiqa oraliq (1200 soniya):
                await asyncio.sleep(1200)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._is_busy = False
                self._last_error = str(e)
                self._current_activity = f"Kutilmagan ogohlantirish: {str(e)[:60]}"
                self._log_activity(f"Ogohlantirish: {e}", "warning")
                logger.warning("Miya 4 tafakkur davrida ogohlantirish: %s", e)
                # Limit yoki xatolik bo'lsa 120 soniya kutib davom etish:
                await asyncio.sleep(120)

    async def _synthesize_insights(self) -> None:
        """So'nggi savollardan umumiy saboq va tavsiyalar sintezi."""
        from services.ai_service import ai_service
        questions = memory_service.get_recent_user_questions(limit=8)
        
        fallback_topics = [
            "Python list comprehension vs for loop tezligi va xotirasi",
            "JavaScript Event Loop, Microtasks va Macrotasks ishlashi",
            "FastAPI da asinxron def vs oddiy def funksiyalar farqi",
            "React da useEffect dependency array va infinite loop xatosi",
            "Telegram Bot API da FloodWait va rate limit boshqaruvi",
            "SQL da B-Tree Index qanday ishlaydi va qachon sekinlashadi",
            "Python da mutable default argument (def f(x=[])) tuzog'i",
            "JavaScript da closure va xotira sizib chiqishi (memory leak)",
            "Python da asyncio.gather vs asyncio.wait_for va TimeoutError",
            "Docker konteynerlarida caching va multiline RUN optimallashtirish",
        ]

        if questions and len(questions) >= 2:
            q_list_str = "\n".join(f"- {q}" for q in questions[:6])
            self._current_activity = "O'quvchilarning jonli savollaridan universal saboq chiqarilmoqda..."
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
        else:
            chosen_topic = fallback_topics[self._cycle_count % len(fallback_topics)]
            self._current_activity = f"'{chosen_topic}' bo'yicha muhim texnik saboq tahlil qilinmoqda..."
            prompt = (
                "Siz CoddyCamp IT akademiyasining Avtonom Tafakkur Miyasisiz (Miya 4).\n"
                f"Mavzu: '{chosen_topic}'\n\n"
                "Vazifa: Dasturchilar va o'quvchilar ushbu mavzuda eng ko'p yo'l qo'yadigan jiddiy xatoni aniqlang "
                "va uning oldini olish bo'yicha 1 ta oltin qoida (insight) bering.\n"
                "Javobingizni quyidagi aniq formatda bering:\n"
                f"MAVZU: {chosen_topic}\n"
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
            self._recent_insights.append({
                "time": _get_tashkent_time_only(),
                "topic": topic[:50],
                "content": content[:180],
            })
            if len(self._recent_insights) > 15:
                self._recent_insights = self._recent_insights[-15:]
            self._log_activity(f"💡 Yangi saboq: [{topic[:30]}] {content[:80]}...", "insight")
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
            "JavaScript async await va fetch xatolari",
            "React useState va props uzatish xatolari",
            "LMS dasturlash topshiriqlari tahlili",
            "Python try except va error handling",
        ]
        topic = core_topics[self._cycle_count % len(core_topics)]
        self._current_activity = f"'{topic}' mavzusida kelgusi savollarga ideal yechim tayyorlanmoqda..."

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
                    self._recent_precomputations.append({
                        "time": _get_tashkent_time_only(),
                        "topic": topic,
                        "question": q_pattern[:100],
                        "answer": answer_code[:180],
                    })
                    if len(self._recent_precomputations) > 15:
                        self._recent_precomputations = self._recent_precomputations[-15:]
                    self._log_activity(f"⚡ Yechim keshlandi: [{topic}] {q_pattern[:40]}...", "precompute")
                    logger.info("✅ Miya 4 oldindan yechim tayyorlab qo'ydi: [%s] -> %s", topic, q_pattern[:35])
            except Exception as e:
                logger.debug("Pre-compute javobini ajratishda ogohlantirish: %s", e)


autonomous_brain_service = AutonomousBrainService()
