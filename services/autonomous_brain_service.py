"""
services/autonomous_brain_service.py
4-Miya: Avtonom O'rganuvchi, Fikrlovchi va O'zini Takomillashtiruvchi Dvigatel (Autonomous Adaptive Cognitive Brain).
Orqa fonda to'xtovsiz ishlaydi (Background Daemon):
- O'quvchilar va guruhlardagi savollarni tahlil qiladi (Bounded Governor: chegaralangan bilim sintezi).
- Mentorning leksikoni, internet slangi va qisqartmalarini o'rganadi (_learn_mentor_lexicon).
- O'z xatolari va mentor tuzatishlarini tahlil qilib, qat'iy oltin qoidalar chiqaradi (_reflect_on_mistakes).
- Kelgusida so'ralishi mumkin bo'lgan savollarga mukammal yechimlarni oldindan tayyorlab keshga joylaydi (Pre-computation Cache).
- Har kecha 20:00 da Vazifalar guruhiga qisqa, lo'nda kunlik kognitiv hisobot yuboradi (_check_and_send_daily_debrief).
- Faqat Miya 4 uchun ajratilgan mustaqil kalitlardan foydalanadi (jonli chatlarga 0% ta'sir).
"""

import asyncio
import logging
import re
import textwrap
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from services.memory_service import memory_service

logger = logging.getLogger(__name__)


def _clean_field(text: str) -> str:
    """Belgilarni tozalaydi, boshidagi/oxiridagi bo'shliqlarni va dedent qiladi."""
    if not text:
        return ""
    text = textwrap.dedent(text).strip()
    text = re.sub(r"^[\s*#:\-_]+", "", text).strip()
    text = re.sub(r"[\s*#:\-_]+$", "", text).strip()
    return text


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
    """Orqa fonda to'xtovsiz tafakkur qiluvchi va o'zini takomillashtiruvchi 4-Miya xizmati."""

    def __init__(self):
        self._is_running = False
        self._is_busy = False
        self._task: asyncio.Task | None = None
        self._client = None
        self._cycle_count: int = 0
        self._insights_generated: int = 0
        self._answers_precomputed: int = 0
        self._lexicon_learned: int = 0
        self._mistakes_reflected: int = 0
        self._last_run_time: str = "Hali ishga tushmadi"
        self._next_run_estimated: str = "Kutilmoqda..."
        self._current_activity: str = "Tizim ishga tushirilishi kutilmoqda..."
        self._last_error: str | None = None
        self._recent_insights: list[dict[str, Any]] = []
        self._recent_precomputations: list[dict[str, Any]] = []
        self._recent_lexicon: list[dict[str, Any]] = []
        self._recent_mistakes: list[dict[str, Any]] = []
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

    def is_enabled(self) -> bool:
        """Miya 4 yoqilgan yoki o'chirilganligini tekshiradi."""
        return memory_service.get_setting("autonomous_brain_enabled", "true").lower() == "true"

    def set_enabled(self, enabled: bool) -> None:
        """Miya 4 ni yoqish yoki to'xtatish (on/off switch)."""
        memory_service.set_setting("autonomous_brain_enabled", "true" if enabled else "false")
        act = "faollashtirildi" if enabled else "to'xtatildi (pauza)"
        self._log_activity(f"Miya 4 {act}.", "config")

    def get_mode(self) -> str:
        """Joriy tezlik rejimini oladi: 'sokin' (20 daq), 'optimal' (10 daq), 'tezkor' (5 daq)."""
        val = memory_service.get_setting("autonomous_brain_mode", "optimal").lower().strip()
        return val if val in ("sokin", "optimal", "tezkor") else "optimal"

    def set_mode(self, mode: str) -> None:
        """Miya 4 tezlik rejimini o'zgartirish."""
        m = str(mode).lower().strip()
        if m in ("sokin", "optimal", "tezkor"):
            memory_service.set_setting("autonomous_brain_mode", m)
            self._log_activity(f"Miya 4 tezlik rejimi o'zgartirildi: {m.upper()}", "config")

    def get_interval_seconds(self) -> int:
        """Tanlangan rejim bo'yicha interval soniyasini qaytaradi."""
        mode = self.get_mode()
        if mode == "tezkor":
            return 300   # 5 daqiqa
        elif mode == "sokin":
            return 1200  # 20 daqiqa
        return 600       # 10 daqiqa (optimal - default)

    def get_status(self) -> dict[str, Any]:
        """Web App paneli va telemetriya uchun Miya 4 holati."""
        priorities = self._assess_priorities()
        interval_sec = self.get_interval_seconds()
        return {
            "is_running": self._is_running,
            "is_busy": self._is_busy,
            "enabled": self.is_enabled(),
            "mode": self.get_mode(),
            "interval_seconds": interval_sec,
            "interval_minutes": interval_sec // 60,
            "cycle_count": self._cycle_count,
            "insights_generated": self._insights_generated,
            "answers_precomputed": self._answers_precomputed,
            "lexicon_learned": self._lexicon_learned,
            "mistakes_reflected": self._mistakes_reflected,
            "curriculum_saturated": priorities.get("curriculum_saturated", False),
            "priority_topic": priorities.get("priority_topic", "General"),
            "last_run_time": self._last_run_time,
            "next_run_estimated": self._next_run_estimated,
            "current_activity": self._current_activity,
            "last_error": self._last_error,
            "recent_insights": self._recent_insights[-6:],
            "recent_precomputations": self._recent_precomputations[-6:],
            "recent_lexicon": self._recent_lexicon[-6:],
            "recent_mistakes": self._recent_mistakes[-6:],
            "activity_logs": list(reversed(self._activity_logs[-15:])),
        }

    def _assess_priorities(self) -> dict[str, Any]:
        """Kognitiv byudjet va prioritetlarni dinamik baholash (Dynamic Bounded Governor)."""
        try:
            topic_counts = memory_service.get_curriculum_insights_count_by_topic()
            curriculum_topics = memory_service.get_curriculum_topics()
            if not curriculum_topics:
                curriculum_topics = list(memory_service.DEFAULT_CURRICULUM_TOPICS)

            # Agar barcha mavzularda yetarlicha (>= 15 tadan) bilim to'plangan bo'lsa:
            threshold = 15
            saturated_topics = [t for t in curriculum_topics if topic_counts.get(t, 0) >= threshold]
            is_curriculum_saturated = len(saturated_topics) >= len(curriculum_topics)

            unsaturated = [t for t in curriculum_topics if topic_counts.get(t, 0) < threshold]
            priority_topic = unsaturated[0] if unsaturated else curriculum_topics[self._cycle_count % len(curriculum_topics)]

            return {
                "curriculum_saturated": is_curriculum_saturated,
                "priority_topic": priority_topic,
                "topic_counts": topic_counts,
            }
        except Exception as e:
            logger.debug("Prioritetlarni baholashda ogohlantirish: %s", e)
            return {"curriculum_saturated": False, "priority_topic": None, "topic_counts": {}}

    async def start(self, client=None) -> None:
        """Background daemoni ishga tushirish."""
        if self._is_running:
            return
        self._is_running = True
        self._client = client
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

            priorities = self._assess_priorities()
            is_saturated = priorities.get("curriculum_saturated", False)
            priority_topic = priorities.get("priority_topic")

            if is_saturated:
                await self._learn_mentor_lexicon()
                await self._reflect_on_mistakes()
                await self._precompute_upcoming_answers(topic=priority_topic)
            else:
                await self._synthesize_insights(topic=priority_topic)
                await self._learn_mentor_lexicon()
                await self._reflect_on_mistakes()
                await self._precompute_upcoming_answers(topic=priority_topic)

            self._cycle_count += 1
            self._last_run_time = _get_tashkent_now_str()
            self._current_activity = f"Sikl muvaffaqiyatli yakunlandi ({self._last_run_time})."
            self._log_activity(f"✅ Sikl #{self._cycle_count} muvaffaqiyatli bajarildi.", "success")
            return {
                "ok": True,
                "message": f"Miya 4 muvaffaqiyatli fikrlab chiqdi! Saboqlar: {self._insights_generated}, Leksikon: {self._lexicon_learned}, Xato qoidalari: {self._mistakes_reflected}, Kesh yechimlar: {self._answers_precomputed}",
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
        """Doimiy orqa fon tahlil, o'rganish va fikrlash davri."""
        self._client = client
        self._current_activity = "Tizim modullari tekshirilmoqda (5s)..."
        await asyncio.sleep(5)

        while self._is_running:
            try:
                # Agar o'chirilgan bo'lsa, sokin kutib turadi:
                if not self.is_enabled():
                    self._is_busy = False
                    self._current_activity = "⏸️ Miya 4 to'xtatilgan (O'chirilgan rejimda)."
                    self._next_run_estimated = "To'xtatilgan"
                    await asyncio.sleep(10)
                    continue

                # 0. 20:00 Kunlik hisobot (Daily Debrief) tekshiruvi:
                await self._check_and_send_daily_debrief()

                self._is_busy = True
                self._last_run_time = _get_tashkent_now_str()
                self._cycle_count += 1

                priorities = self._assess_priorities()
                is_curriculum_saturated = priorities.get("curriculum_saturated", False)
                priority_topic = priorities.get("priority_topic")
                mode = self.get_mode()

                self._current_activity = f"Sikl #{self._cycle_count} [{mode.upper()}]: Kognitiv adaptatsiya va tahlil..."
                self._log_activity(f"🧬 Sikl #{self._cycle_count} boshlandi ({mode.upper()} rejim)...", "cycle")
                logger.info(
                    "🧬 Miya 4 tafakkur davri boshlandi (Davr #%d, Rejim: %s, Saturated: %s)...",
                    self._cycle_count,
                    mode,
                    is_curriculum_saturated,
                )

                # DINAMIK RESURS TAQSIMOTI:
                # Agar o'quv dasturi yetarlicha to'yingan bo'lsa (har bir mavzuda >= 15 ta insight):
                # Resurslar to'liq o'z ustida ishlash (slang + xatolar) ga yo'naltiriladi!
                if is_curriculum_saturated:
                    # 1. Mentor slangi va qisqartmalarini o'rganish:
                    await self._learn_mentor_lexicon()
                    await asyncio.sleep(4.0)

                    # 2. Xatolar va mentor tanqididan saboq chiqarish:
                    await self._reflect_on_mistakes()
                    await asyncio.sleep(4.0)

                    # 3. Kesh yechimlarni to'ldirish (agar sikl toq bo'lsa):
                    if self._cycle_count % 2 == 1:
                        await self._precompute_upcoming_answers(topic=priority_topic)
                else:
                    # Hali bilimlar bazasida o'quv mavzulari kam:
                    # Sikllar navbati: 0 -> O'quv sabog'i, 1 -> Mentor slangi, 2 -> Xatolar tahlili
                    mod = self._cycle_count % 3
                    if mod == 0:
                        await self._synthesize_insights(topic=priority_topic)
                    elif mod == 1:
                        await self._learn_mentor_lexicon()
                    else:
                        await self._reflect_on_mistakes()

                    await asyncio.sleep(4.0)
                    await self._precompute_upcoming_answers(topic=priority_topic)

                self._last_error = None
                self._is_busy = False

                # Tanlangan tezlik rejimi bo'yicha intervalni hisoblash:
                interval_sec = self.get_interval_seconds()
                interval_min = interval_sec // 60

                try:
                    tz = ZoneInfo("Asia/Tashkent")
                    next_time = (datetime.now(tz) + timedelta(seconds=interval_sec)).strftime("%H:%M:%S")
                    self._next_run_estimated = f"{next_time} da ({interval_min} daq)"
                except Exception:
                    self._next_run_estimated = f"{interval_min} daqiqadan so'ng"

                self._current_activity = f"Sokin rejimda [{mode.upper()}]. Keyingi tafakkur sikli: {self._next_run_estimated}"
                self._log_activity(
                    f"Sikl #{self._cycle_count} yakunlandi [{mode.upper()}]. Jami: {self._insights_generated} saboq, {self._lexicon_learned} leksikon, {self._mistakes_reflected} xato qoidasi, {self._answers_precomputed} kesh.",
                    "info",
                )

                # Har 15 soniyada rejim yoki to'xtatish o'zgarishini tekshirish (foydalanuvchi appda rejimni o'zgartirsa darhol sezish uchun):
                steps = max(1, interval_sec // 15)
                for _ in range(steps):
                    if not self._is_running or not self.is_enabled():
                        break
                    await asyncio.sleep(15)
                    await self._check_and_send_daily_debrief()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._is_busy = False
                self._last_error = str(e)
                self._current_activity = f"Kutilmagan ogohlantirish: {str(e)[:60]}"
                self._log_activity(f"Ogohlantirish: {e}", "warning")
                logger.warning("Miya 4 tafakkur davrida ogohlantirish: %s", e)
                await asyncio.sleep(120)

    async def _check_and_send_daily_debrief(self) -> None:
        """Kechasi soat 20:00 da Vazifalar guruhiga kunlik kognitiv rivojlanish hisobotini yuborish."""
        try:
            from services.mongo_memory_service import mongo_memory_service
            tz = ZoneInfo("Asia/Tashkent")
            now = datetime.now(tz)

            # Faqat soat 20:00 dan so'ng (20:00 - 23:59 oralig'ida) ishlaydi:
            if now.hour < 20:
                return

            today_str = now.strftime("%Y-%m-%d")
            # Bugun hisobot allaqachon yuborilganmi?
            if mongo_memory_service.is_daily_debrief_sent(today_str):
                return

            # Agar client mavjud bo'lmasa:
            if not self._client:
                return

            from config import get_vazifalar_chat_target
            target_chat = await get_vazifalar_chat_target(self._client)
            if not target_chat:
                logger.warning("Debrief: Vazifalar guruhi topilmadi.")
                return

            # Hisobot matnini tayyorlash:
            all_lexicon = memory_service.get_all_mentor_lexicon()
            lex_sample = ", ".join(f"`{x['phrase']}` ({x['meaning'][:15]})" for x in all_lexicon[-2:]) if all_lexicon else "faol tahlil qilinmoqda"
            recent_mistakes = memory_service.get_recent_self_mistakes(limit=2)
            rule_sample = f"\"{recent_mistakes[-1]['correction_rule'][:60]}...\"" if recent_mistakes else "barcha qoidalarga qat'iy amal qilinmoqda"

            debrief_msg = (
                "🧠 **Miya 4: Kunlik Kognitiv Rivojlanish Hisoboti (20:00)**\n"
                f"📅 *Sana: {now.strftime('%d.%m.%Y')}*\n\n"
                f"• 📚 **Leksikon & Slang:** Mentor muloqot uslubidan jami {len(all_lexicon)} ta ibora o'zlashtirildi ({lex_sample}).\n"
                f"• 🛡 **Xatolar tahlili:** Jami {len(recent_mistakes)} ta operatsion xato tahlil qilinib, qoidalar shakllantirildi ({rule_sample}).\n"
                f"• 💡 **Amaliy Saboqlar:** O'quv dasturi bo'yicha {self._insights_generated} ta yangi tahliliy insight sintez qilindi.\n"
                f"• ⚡ **Kesh Yechimlar:** Savollarga oldindan tayyorlangan {self._answers_precomputed} ta tezkor yechim keshlandi.\n\n"
                "✨ *Tizim chegaralangan tejamkor rejimda o'z-o'zini mustaqil mukammallashtirishda davom etmoqda.*"
            )

            await self._client.send_message(target_chat, debrief_msg)
            stats = {
                "insights": self._insights_generated,
                "lexicon": len(all_lexicon),
                "mistakes": len(recent_mistakes),
                "precomputed": self._answers_precomputed,
            }
            mongo_memory_service.save_daily_debrief(today_str, debrief_msg, stats)
            self._log_activity("📢 20:00 Kunlik kognitiv hisobot Vazifalar guruhiga yetkazildi.", "debrief")
            logger.info("✅ 20:00 Kunlik hisobot Vazifalar guruhiga muvaffaqiyatli yuborildi.")
        except Exception as e:
            logger.error("20:00 kunlik hisobot yuborishda xatolik: %s", e)

    async def _learn_mentor_lexicon(self) -> None:
        """Mentorning so'zlashuv uslubi, internet slangi va qisqartmalarini o'rganish."""
        from services.ai_service import ai_service
        self._current_activity = "Mentor leksikoni, slangi va qisqartmalari tahlil qilinmoqda..."

        mentor_messages = memory_service.get_recent_mentor_messages(limit=25)
        if not mentor_messages or len(mentor_messages) < 2:
            return

        existing_lexicon = memory_service.get_all_mentor_lexicon()
        existing_phrases = [item["phrase"].lower() for item in existing_lexicon]
        existing_str = ", ".join(existing_phrases[:20]) if existing_phrases else "mavjud emas"

        msgs_text = "\n".join(f"- {m}" for m in mentor_messages[:15])

        prompt = (
            "Siz CoddyCamp IT akademiyasining Leksikon va Til O'rganish Miyasisiz (Miya 4).\n"
            "Vazifangiz — mentor (Nuriddin aka) ning xabarlaridagi o'zbekcha internet slangi, qisqartmalar, "
            "sheva yoki norasmiy so'zlarni tahlil qilish va ma'nosini anglash.\n"
            "Masalan: 'db' -> 'deb', 'tel qil' -> 'telefon qilish / qo'ng'iroq qilish', 'qiber' -> 'qilib ber', 'nma' -> 'nima', 'kordim' -> 'ko'rdim'.\n\n"
            f"Allaqachon o'rganilgan iboralar: [{existing_str}]. Bularni qayta takrorlamang!\n\n"
            "Mentorning so'nggi xabarlari:\n"
            f"{msgs_text}\n\n"
            "Talab: Ushbu xabarlardan hali o'rganilmagan eng muhim 1 ta qisqartma, so'zlashuv iborasi yoki slanging ma'nosini aniqlang.\n"
            "Javobni FAQAT quyidagi formatda bering:\n"
            "IBORA: [qisqartma yoki so'z]\n"
            "MANO: [to'liq ma'nosi va tushuntirishi]\n"
            "Agar yangi slang yoki qisqartma topilmasa, shunchaki 'HECH_QANDAY' deb yozing."
        )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply or "HECH_QANDAY" in reply.upper():
            return

        m_ibora = re.search(r"(?:\*{1,3}|#{1,3})?\s*IBORA\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)
        m_mano = re.search(r"(?:\*{1,3}|#{1,3})?\s*MANO\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)

        if m_ibora and m_mano:
            try:
                ibora_part = reply[m_ibora.end():m_mano.start()]
                mano_part = reply[m_mano.end():]
                phrase = _clean_field(ibora_part).strip("\"'").lower()
                meaning = _clean_field(mano_part).strip("\"'")
                if phrase and meaning and 2 <= len(phrase) <= 40:
                    if phrase not in existing_phrases:
                        memory_service.add_mentor_lexicon(phrase, meaning, category="slang")
                        self._lexicon_learned += 1
                        self._recent_lexicon.append({
                            "time": _get_tashkent_time_only(),
                            "phrase": phrase,
                            "meaning": meaning[:100],
                        })
                        if len(self._recent_lexicon) > 15:
                            self._recent_lexicon = self._recent_lexicon[-15:]
                        self._log_activity(f"📖 Yangi leksikon: '{phrase}' -> {meaning[:50]}", "lexicon")
                        logger.info("✅ Miya 4 yangi slang o'rgandi: [%s] = %s", phrase, meaning)
            except Exception as e:
                logger.debug("Leksikon ajratishda xatolik: %s", e)

    async def _reflect_on_mistakes(self) -> None:
        """O'z xatolarini, mentor tuzatishlarini tahlil qilish va qat'iy qoidalar chiqarish."""
        from services.ai_service import ai_service
        self._current_activity = "O'z xatolari va mentor ko'rsatmalari tahlil qilinmoqda..."

        dialogues = memory_service.get_recent_dialogues_for_reflection(limit=15)
        if not dialogues or len(dialogues) < 1:
            return

        dial_text = ""
        for i, d in enumerate(dialogues[-8:], 1):
            dial_text += f"Holat #{i}:\nAI javobi: {d['assistant']}\nMentor replikasi: {d['user_feedback']}\n\n"

        prompt = (
            "Siz CoddyCamp IT akademiyasining O'z-O'zini Tahlil Qiluvchi va Xatolardan Saboq Oluvchi Miyasisiz (Miya 4).\n"
            "Vazifangiz — quyidagi suhbatlarda AI qanday xatoga yo'l qo'ygani, tushunmovchilik qilgani yoki mentorning tanqidi/tuzatishini tahlil qilish.\n\n"
            "Suhbatlar:\n"
            f"{dial_text}\n"
            "Talab: Agar suhbatda AI xato qilgan bo'lsa (yoki mentor norozi bo'lib to'g'irlagan bo'lsa), kelgusida bu takrorlanmasligi uchun 1 ta qat'iy qoida (golden rule) chiqaring.\n"
            "Javobni FAQAT quyidagi formatda bering:\n"
            "XATO: [Qanday xatolik yoki noaniqlik bo'lgani]\n"
            "QOIDA: [Kelgusida AI qat'iy amal qilishi shart bo'lgan oltin qoida]\n"
            "Agar xatolik yoki tuzatish bo'lmasa, shunchaki 'HECH_QANDAY' deb yozing."
        )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply or "HECH_QANDAY" in reply.upper():
            return

        m_xato = re.search(r"(?:\*{1,3}|#{1,3})?\s*XATO\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)
        m_qoida = re.search(r"(?:\*{1,3}|#{1,3})?\s*QOIDA\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)

        if m_xato and m_qoida:
            try:
                xato_part = reply[m_xato.end():m_qoida.start()]
                qoida_part = reply[m_qoida.end():]
                mistake_desc = _clean_field(xato_part)
                correction_rule = _clean_field(qoida_part)
                if mistake_desc and correction_rule and len(correction_rule) >= 10:
                    memory_service.add_self_mistake(mistake_desc[:200], correction_rule[:300], context="reflection")
                    self._mistakes_reflected += 1
                    self._recent_mistakes.append({
                        "time": _get_tashkent_time_only(),
                        "mistake": mistake_desc[:100],
                        "rule": correction_rule[:150],
                    })
                    if len(self._recent_mistakes) > 15:
                        self._recent_mistakes = self._recent_mistakes[-15:]
                    self._log_activity(f"🛡 Xatodan saboq: {correction_rule[:60]}...", "mistake")
                    logger.info("✅ Miya 4 xatodan yangi qoida chiqardi: %s", correction_rule[:60])
            except Exception as e:
                logger.debug("Xatolik tahlilini ajratishda ogohlantirish: %s", e)

    async def _synthesize_insights(self, topic: str | None = None) -> None:
        """So'nggi savollardan umumiy saboq va tavsiyalar sintezi (Faqat rasmiy o'quv dasturi bo'yicha)."""
        from services.ai_service import ai_service

        curriculum_topics = memory_service.get_curriculum_topics()
        if not curriculum_topics:
            curriculum_topics = list(memory_service.DEFAULT_CURRICULUM_TOPICS)
        topics_str = ", ".join(curriculum_topics)

        chosen_topic = topic or curriculum_topics[self._cycle_count % len(curriculum_topics)]
        questions = memory_service.get_recent_user_questions(limit=8)

        if questions and len(questions) >= 2:
            q_list_str = "\n".join(f"- {q}" for q in questions[:6])
            self._current_activity = f"O'quvchilar savollaridan o'quv dasturi ({chosen_topic}) bo'yicha saboq tahlil qilinmoqda..."
            prompt = (
                "Siz CoddyCamp IT akademiyasining Avtonom Tafakkur Miyasisiz (Miya 4).\n"
                f"Markazimizning rasmiy o'quv dasturi va texnologiyalari: [{topics_str}].\n\n"
                "QAT'IY TALAB VA CHEKLOV:\n"
                "Siz FAQAT yuqoridagi CoddyCamp o'quv dasturi mavzulari doirasida saboq va xulosa chiqarishingiz shart! "
                "Dasturdan tashqari boshqa begona tillarga, freymvorklarga yoki mavzularga (masalan: C++, Java, PHP, Docker, Go va h.k.) aslo chiqmang!\n\n"
                "Quyida o'quvchilar va guruhlardan kelgan so'nggi savollar berilgan:\n"
                f"{q_list_str}\n\n"
                "Vazifa: Ushbu savollar orasidan markazimiz o'quv dasturiga mos keladigan qismini tahlil qiling va "
                "o'quvchilar ko'p yo'l qo'yadigan xato bo'yicha 1 ta oltin amaliy qoida (insight) chiqaring.\n"
                "Javobingizni quyidagi aniq formatda bering:\n"
                "MAVZU: [O'quv dasturidagi mavzu nomi]\n"
                "XULOSA: [1-2 ta lo'nda, foydali, aniq qoida yoki dasturlash tushuntirishi]"
            )
        else:
            self._current_activity = f"'{chosen_topic}' bo'yicha muhim amaliy saboq tahlil qilinmoqda..."
            prompt = (
                "Siz CoddyCamp IT akademiyasining Avtonom Tafakkur Miyasisiz (Miya 4).\n"
                f"O'quv dasturi mavzusi: '{chosen_topic}'\n\n"
                "QAT'IY TALAB VA CHEKLOV:\n"
                f"Siz FAQAT CoddyCamp o'quv dasturidagi ushbu belgilangan mavzu ('{chosen_topic}') doirasida fikrlashingiz shart. "
                "Belgilangan mavzular chegarasidan aslo chetga chiqmang!\n\n"
                f"Vazifa: Dasturchilar va o'quvchilar '{chosen_topic}' mavzusida eng ko'p yo'l qo'yadigan jiddiy xatoni aniqlang "
                "va uning oldini olish bo'yicha 1 ta oltin qoida (insight) bering.\n"
                "Javobingizni quyidagi aniq formatda bering:\n"
                f"MAVZU: {chosen_topic}\n"
                "XULOSA: [1-2 ta lo'nda, foydali, aniq qoida yoki dasturlash tushuntirishi]"
            )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply:
            return

        final_topic = chosen_topic
        content = _clean_field(reply)
        m_xulosa = re.search(r"(?:\*{1,3}|#{1,3})?\s*XULOSA\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)
        m_mavzu = re.search(r"(?:\*{1,3}|#{1,3})?\s*MAVZU\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)

        if m_xulosa:
            try:
                x_idx = m_xulosa.start()
                topic_part = reply[:x_idx]
                if m_mavzu:
                    topic_part = topic_part[m_mavzu.end():]
                parsed_topic = _clean_field(topic_part)
                matched = next((t for t in curriculum_topics if t.lower() in parsed_topic.lower() or parsed_topic.lower() in t.lower()), None)
                if matched:
                    if matched.lower() in parsed_topic.lower():
                        final_topic = parsed_topic
                    else:
                        final_topic = f"{matched}: {parsed_topic}"
                else:
                    final_topic = f"{chosen_topic}: {parsed_topic}" if parsed_topic else chosen_topic
                content = _clean_field(reply[m_xulosa.end():])
            except Exception:
                pass

        if content and len(content) >= 15:
            memory_service.add_autonomous_insight(final_topic[:50], content)
            self._insights_generated += 1
            self._recent_insights.append({
                "time": _get_tashkent_time_only(),
                "topic": final_topic[:50],
                "content": content[:180],
            })
            if len(self._recent_insights) > 15:
                self._recent_insights = self._recent_insights[-15:]
            self._log_activity(f"💡 Yangi saboq: [{final_topic[:30]}] {content[:80]}...", "insight")
            logger.info("✅ Miya 4 yangi saboq kashf qildi: [%s]", final_topic[:30])

    async def _precompute_upcoming_answers(self, topic: str | None = None) -> None:
        """Keyinchalik so'ralishi mumkin bo'lgan savollarga oldindan yechim tayyorlash (Faqat rasmiy o'quv dasturi bo'yicha)."""
        from services.ai_service import ai_service

        curriculum_topics = memory_service.get_curriculum_topics()
        if not curriculum_topics:
            curriculum_topics = list(memory_service.DEFAULT_CURRICULUM_TOPICS)

        target_topic = topic or curriculum_topics[self._cycle_count % len(curriculum_topics)]
        self._current_activity = f"'{target_topic}' mavzusida kelgusi savollarga ideal yechim tayyorlanmoqda..."

        prompt = (
            f"Siz CoddyCamp IT akademiyasining Avtonom Tafakkur Miyasisiz (Miya 4).\n"
            f"O'quv dasturi mavzusi: '{target_topic}'\n\n"
            f"QAT'IY TALAB VA CHEKLOV:\n"
            f"Siz FAQAT CoddyCamp o'quv dasturidagi belgilangan mavzu ('{target_topic}') doirasida fikrlashingiz shart. "
            f"Ushbu mavzudan boshqa begona tillarga yoki mavzularga aslo chiqmang!\n\n"
            f"Vazifa: O'quvchilar '{target_topic}' mavzusida eng ko'p so'raydigan yoki kelgusida so'rashi mumkin bo'lgan 1 ta qiyin savolni/xatoni aniqlang "
            "va unga ideal, to'liq kodli, tushunarli yechim tayyorlang.\n"
            "Javobni quyidagi aniq formatda bering:\n"
            "SAVOL: [O'quvchi berishi mumkin bo'lgan savol yoki xato matni]\n"
            "YECHIM: [Mukammal, qisqa va to'g'ri kodli javob]"
        )

        reply = await ai_service.generate_autonomous_reflection(prompt)
        if not reply:
            return

        m_yechim = re.search(r"(?:\*{1,3}|#{1,3})?\s*YECHIM\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)
        m_savol = re.search(r"(?:\*{1,3}|#{1,3})?\s*SAVOL\s*(?:\*{1,3}|#{1,3})?:?", reply, re.IGNORECASE)

        if m_yechim:
            try:
                y_idx = m_yechim.start()
                q_part = reply[:y_idx]
                if m_savol:
                    q_part = q_part[m_savol.end():]
                a_part = reply[m_yechim.end():]

                q_pattern = _clean_field(q_part)
                answer_code = textwrap.dedent(a_part).strip()
                answer_code = re.sub(r"^\*{1,3}\s*", "", answer_code).strip()
                answer_code = re.sub(r"\*{1,3}$", "", answer_code).strip()

                if q_pattern and answer_code:
                    memory_service.add_precomputed_answer(target_topic, q_pattern, answer_code)
                    self._answers_precomputed += 1
                    self._recent_precomputations.append({
                        "time": _get_tashkent_time_only(),
                        "topic": target_topic,
                        "question": q_pattern[:100],
                        "answer": answer_code[:180],
                    })
                    if len(self._recent_precomputations) > 15:
                        self._recent_precomputations = self._recent_precomputations[-15:]
                    self._log_activity(f"⚡ Yechim keshlandi: [{target_topic}] {q_pattern[:40]}...", "precompute")
                    logger.info("✅ Miya 4 oldindan yechim tayyorlab qo'ydi: [%s] -> %s", target_topic, q_pattern[:35])
            except Exception as e:
                logger.debug("Pre-compute javobini ajratishda ogohlantirish: %s", e)


autonomous_brain_service = AutonomousBrainService()
