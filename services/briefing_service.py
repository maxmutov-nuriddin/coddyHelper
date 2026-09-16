"""
services/briefing_service.py
JARVIS Tonggi Brifing (Morning Briefing) xizmati.
Mentor uchun kun tartibi, darslar, rejalashtirilgan vazifalar va muhim xabarlarni
ham matnli karta, ham jonli audio xabar (Telegram + Mac spikeri) ko'rinishida taqdim etadi.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from config import config
from services.memory_service import memory_service
from services.tts_service import generate_voice_message
from services.speaker_service import speaker_service

logger = logging.getLogger(__name__)


class BriefingService:
    def __init__(self):
        self._tz = ZoneInfo("Asia/Tashkent")

    def _get_current_tashkent_time(self) -> datetime:
        return datetime.now(self._tz)

    async def generate_briefing(self) -> tuple[str, str]:
        """
        Kunlik brifingni shakllantiradi.
        Qaytaradi:
          - full_telegram_text: Telegram uchun formatlangan chiroyli hisobot
          - spoken_text: TTS va karnay uchun qisqa (15-20 soniyalik) lo'nda nutq
        """
        now = self._get_current_tashkent_time()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        # 1. Faol eslatmalar va rejalarni olish
        reminders = memory_service.get_active_reminders(limit=10)
        daily_plans = memory_service.get_plans_for_date(plan_date=date_str)
        stats = memory_service.get_agent_stats()

        total_students = stats.get("total_students", 0)
        iq_score = stats.get("iq_score", 148)

        # 2. Vazifalar punktlarini tayyorlash
        plan_lines = []
        spoken_tasks = []

        if daily_plans:
            for p in daily_plans[:5]:
                t_title = p.get("task") or p.get("title", "Vazifa")
                plan_lines.append(f"  • 📌 {t_title}")
                spoken_tasks.append(t_title)

        if reminders:
            for r in reminders[:3]:
                r_text = r.get("message") or r.get("text", "Eslatma")
                r_time = r.get("remind_time", "")
                short_time = r_time[-8:-3] if len(r_time) >= 8 else ""
                plan_lines.append(f"  • ⏰ {r_text} ({short_time})")
                spoken_tasks.append(r_text)

        if not plan_lines:
            plan_lines.append("  • 🟢 Hozircha yangi qat'iy reja kiritilmagan. Kun tartibingiz erkin.")

        tasks_str = "\n".join(plan_lines)

        # 3. Telegram to'liq matni
        greeting = "Xayrli tong" if now.hour < 12 else ("Assalomu alaykum" if now.hour < 18 else "Xayrli kech")
        full_telegram_text = (
            f"🌅 **{greeting}, Nuriddin aka!**\n"
            f"🗓 Sana: **{date_str}** | Vaqt: **{time_str}**\n"
            f"🧠 **Jarvis Tizim Holati:** IQ {iq_score} | 36 Kalit Klasteri Faol\n\n"
            f"📋 **Bugungi Rejalar va Eslatmalar:**\n"
            f"{tasks_str}\n\n"
            f"👨‍🎓 **O'quvchilar Bazasi:** {total_students} nafar faol o'quvchi\n\n"
            f"⚡ Kuningiz unumli va barakali o'tsin, Ustoz! Buyruqlaringizga tayyorman."
        )

        # 4. Spoken (TTS) qisqa nutq matni (AirPods / Mac karnayi uchun samimiy va jonli)
        spoken_parts = [
            f"{greeting}, Nuriddin aka!",
            f"Bugun {date_str}, soat {time_str}."
        ]
        if spoken_tasks:
            spoken_parts.append(f"Bugun rejalarda: {', '.join(spoken_tasks[:2])}.")
        else:
            spoken_parts.append("Bugungi jadvalingiz erkin, barcha tizimlar to'liq nazorat ostida.")

        spoken_parts.append(f"O'quvchilar soni {total_students} nafar. Barcha vazifalarga tayyorman, Ustoz!")
        spoken_text = " ".join(spoken_parts)

        return full_telegram_text, spoken_text

    async def deliver_briefing(
        self,
        client=None,
        chat_id: int | str | None = None,
        speak_locally: bool = True,
        send_telegram: bool = True,
    ) -> dict:
        """
        Brifingni tayyorlab, Telegramga (matn + ovoz) yetkazadi va
        agar speak_locally=True bo'lsa Mac karnayidan yangratadi.
        """
        full_text, spoken_text = await self.generate_briefing()
        result = {
            "ok": True,
            "text": full_text,
            "spoken": spoken_text,
            "telegram_sent": False,
            "voice_sent": False,
            "local_spoken": False,
        }

        # 1. Mac karnayidan gapirish (Local Speaker)
        if speak_locally and speaker_service.is_available():
            try:
                # Orqa fonda audio yangraydi
                asyncio.create_task(speaker_service.speak_text(spoken_text))
                result["local_spoken"] = True
            except Exception as spk_err:
                logger.debug("Local speaker xatolik: %s", spk_err)

        # 2. Telegramga xabar va ovozli xabar yuborish
        target_chat = chat_id or config.escalation_chat or config.mentor_user_id
        if send_telegram and client and target_chat:
            try:
                target_entity = int(target_chat) if str(target_chat).lstrip("-").isdigit() else target_chat
                # Avval matnli hisobot kartasi
                sent_msg = await client.send_message(target_entity, full_text)
                result["telegram_sent"] = bool(sent_msg)

                # So'ngra ovozli xabar (Voice Note)
                voice_reply_enabled = memory_service.get_setting("voice_reply_enabled", "true").lower() == "true"
                if voice_reply_enabled:
                    voice_path = await generate_voice_message(spoken_text, is_mentor=True)
                    if voice_path and voice_path.exists():
                        await client.send_file(
                            target_entity,
                            file=str(voice_path),
                            voice_note=True,
                            caption="🎙 **Jarvis Ovozli Brifingi**",
                            reply_to=sent_msg.id if sent_msg else None,
                        )
                        result["voice_sent"] = True
                        voice_path.unlink(missing_ok=True)
            except Exception as tg_err:
                logger.error("Telegramga brifing yuborishda xatolik: %s", tg_err)
                result["telegram_error"] = str(tg_err)

        return result


briefing_service = BriefingService()
