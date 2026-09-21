"""
services/profile_intelligence_service.py
Miya 5: Silent Public Profiler, Sequential Dialog Crawler va Telegram Bot Ecosystem Observer.

1. Barcha eski va yangi chatlardagi odamlarni 100% yashirin tahlil qilish.
2. 1 marta qoidasi (Deduplication): Oldin tahlil qilinganlar qayta tekshirilmaydi.
3. Ketma-ket (bitta-bitta) xavfsiz ishlash (Sequential FIFO Queue + FloodWait pauzasi).
4. Telegram guruhlaridagi botlarning ishlash uslubini (UI/UX) o'rganish.
5. Dosyeni faqat Mentor (@mentor_cc) va Vazifalar guruhiga (-5388159517) yuborish.
"""

import asyncio
import logging
import re
from typing import Any
from config import config, is_escalation_chat
from services.memory_service import memory_service

logger = logging.getLogger(__name__)


class ProfileIntelligenceService:
    """Miya 5: Kognitiv Razvedka, Ketma-ket Skaner va Bot Observer Xizmati."""

    def __init__(self):
        self._client = None
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._enqueued_ids: set[int] = set()
        self._is_running = False
        self._is_crawling = False
        self._worker_task: asyncio.Task | None = None
        self._current_user: str | None = None
        self._total_analyzed_session: int = 0

    def start(self, client=None) -> None:
        """Profiler ishchi fon daemonini ishga tushiradi."""
        if self._is_running:
            return
        if client:
            self._client = client
        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("🕵️‍♂️ Miya 5: Silent Profiler & Sequential Crawler ishga tushirildi.")

    def stop(self) -> None:
        """Profiler daemonini to'xtatadi."""
        self._is_running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        logger.info("⏸️ Miya 5: Silent Profiler to'xtatildi.")

    def is_enabled(self) -> bool:
        """Profiler yoqilgan yoki yo'qligini tekshiradi."""
        return memory_service.get_setting("auto_profiler_enabled", "true").lower() == "true"

    def set_enabled(self, enabled: bool) -> None:
        """Profilerni yoqish/o'chirish."""
        memory_service.set_setting("auto_profiler_enabled", "true" if enabled else "false")

    def get_delay_seconds(self) -> int:
        """Har bir shaxs orasidagi xavfsiz tanaffus soniyasi (15-60s)."""
        val = memory_service.get_setting("auto_profiler_delay", "20")
        try:
            return max(10, min(120, int(val)))
        except ValueError:
            return 20

    def set_delay_seconds(self, seconds: int) -> None:
        """Tanaffus soniyasini saqlash."""
        sec = max(10, min(120, int(seconds)))
        memory_service.set_setting("auto_profiler_delay", str(sec))

    def get_destination(self) -> str:
        """Dosye yuborish manzili: 'both' | 'vazifalar' | 'mentor'."""
        return memory_service.get_setting("auto_profiler_destination", "both")

    def set_destination(self, dest: str) -> None:
        """Dosye yuborish manzilini saqlash."""
        if dest in ("both", "vazifalar", "mentor"):
            memory_service.set_setting("auto_profiler_destination", dest)

    @property
    def queue_length(self) -> int:
        return self._queue.qsize()

    def enqueue_user(self, user_id: int) -> bool:
        """
        Yangi foydalanuvchini navbatga qo'shadi (1 marta qoidasi).
        Agar oldin tahlil qilingan bo'lsa yoki navbatda bo'lsa, qo'shilmaydi.
        """
        if not self.is_enabled() or not user_id or user_id <= 0:
            return False

        # Mentor yoki botning o'zi bo'lsa tekshirilmaydi
        if user_id in (config.mentor_user_id, 8105823872):
            return False

        # 1. Oldin tahlil qilinganmi? (Deduplication)
        if memory_service.is_user_dossier_exists(user_id):
            return False

        # 2. Hozir navbatdami?
        if user_id in self._enqueued_ids:
            return False

        self._enqueued_ids.add(user_id)
        self._queue.put_nowait(user_id)
        logger.debug("📥 Profiler navbatiga qo'shildi: user_id=%s (Navbat hajmi: %d)", user_id, self._queue.qsize())
        return True

    async def scan_historic_dialogs(self, client=None) -> int:
        """
        Mavjud barcha shaxsiy dialoglarni birma-bir skaner qilib,
        tahlil qilinmagan foydalanuvchilarni navbatga terib chiqadi.
        """
        cl = client or self._client
        if not cl:
            logger.warning("Historic Dialog Scan: Telethon client mavjud emas.")
            return 0

        if self._is_crawling:
            logger.info("Historic Dialog Scan allaqachon davom etmoqda.")
            return self._queue.qsize()

        self._is_crawling = True
        added_count = 0
        try:
            logger.info("🔍 Tarixiy chatlarni skanerlash boshlandi...")
            async for dialog in cl.iter_dialogs(limit=300):
                if not self._is_running:
                    break
                # Faqat shaxsiy yozishmalar (guruh va kanallar emas)
                if dialog.is_user:
                    entity = dialog.entity
                    if getattr(entity, "bot", False) or getattr(entity, "is_self", False):
                        continue
                    uid = getattr(entity, "id", None)
                    if uid and uid not in (config.mentor_user_id, 8105823872):
                        if not memory_service.is_user_dossier_exists(uid) and uid not in self._enqueued_ids:
                            self._enqueued_ids.add(uid)
                            self._queue.put_nowait(uid)
                            added_count += 1
            logger.info("✅ Tarixiy chatlar skanerlandi: %d ta yangi shaxs navbatga qo'shildi.", added_count)
        except Exception as e:
            logger.error("scan_historic_dialogs xatolik: %s", e)
        finally:
            self._is_crawling = False

        return added_count

    async def _inspect_single_user(self, client: Any, user_id: int) -> dict[str, Any] | None:
        """
        Bitta foydalanuvchining ochiq profilini Telethon orqali to'liq o'qiydi:
        bio, rasmlar soni, stories, bog'langan kanal va postlar.
        100% yashirin (foydalanuvchiga hech qanday bildirishnoma bormaydi).
        """
        try:
            from telethon.tl.functions.users import GetFullUserRequest

            entity = await client.get_entity(user_id)
            if not entity or getattr(entity, "bot", False):
                return None

            first_name = getattr(entity, "first_name", "") or ""
            last_name = getattr(entity, "last_name", "") or ""
            full_name = f"{first_name} {last_name}".strip() or "Noma'lum"
            username = getattr(entity, "username", "") or ""
            phone = getattr(entity, "phone", "") or ""

            # 1. Bio va to'liq ma'lumotlar
            full_user_res = await client(GetFullUserRequest(entity))
            full_user = getattr(full_user_res, "full_user", None)
            bio = getattr(full_user, "about", "") or ""

            # 2. Profil rasmlari
            photo_count = 0
            try:
                photos = await client.get_profile_photos(entity, limit=5)
                photo_count = len(photos) if photos else 0
            except Exception:
                pass

            # 3. Stories mavjudligi
            has_stories = False
            try:
                if full_user and getattr(full_user, "stories", None):
                    has_stories = True
            except Exception:
                pass

            # 4. Bog'langan kanal yoki tashqi linklar tahlili
            channel_username = ""
            channel_summary = ""

            # Bio ichidan @kanal yoki t.me/kanal qidirish
            channel_match = re.search(r"@([a-zA-Z0-9_]{4,32})|t\.me/([a-zA-Z0-9_]{4,32})", bio)
            if channel_match:
                ch_tag = channel_match.group(1) or channel_match.group(2)
                # O'zining username'i emasligini tekshirish
                if ch_tag and ch_tag.lower() != username.lower():
                    channel_username = f"@{ch_tag}"
                    try:
                        ch_entity = await client.get_entity(ch_tag)
                        if ch_entity and getattr(ch_entity, "broadcast", False):
                            ch_title = getattr(ch_entity, "title", "")
                            # Kanalning oxirgi 3 ta postini o'qish
                            posts_snippets = []
                            async for post_msg in client.iter_messages(ch_entity, limit=3):
                                if post_msg.text:
                                    posts_snippets.append(post_msg.text[:120].replace("\n", " "))
                            summary_posts = " | ".join(posts_snippets) if posts_snippets else "Postlar matnsiz"
                            channel_summary = f"Kanal nomi: '{ch_title}'. So'nggi postlar: {summary_posts}"
                    except Exception as ch_err:
                        logger.debug("Kanalni o'qishda ogohlantirish (%s): %s", ch_tag, ch_err)
                        channel_summary = f"Kanal havolasi: @{ch_tag}"

            return {
                "user_id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "username": username,
                "phone": phone,
                "bio": bio,
                "photo_count": photo_count,
                "has_stories": has_stories,
                "channel_username": channel_username,
                "channel_summary": channel_summary,
            }
        except Exception as e:
            logger.warning("Foydalanuvchi profilini o'qishda xatolik (%s): %s", user_id, e)
            return None

    async def _synthesize_dossier_with_ai(self, profile: dict[str, Any]) -> str:
        """Miya 5 orqali foydalanuvchining to'liq kognitiv dosyesini sintez qiladi."""
        from services.ai_service import ai_service

        prompt = (
            f"Foydalanuvchi Telegram ochiq ma'lumotlari:\n"
            f"• Ismi: {profile.get('full_name')}\n"
            f"• Username: @{profile.get('username') or 'yoq'}\n"
            f"• Bio: {profile.get('bio') or 'Kiritilmagan'}\n"
            f"• Profil rasmlari soni: {profile.get('photo_count')} ta\n"
            f"• Stories: {'Mavjud' if profile.get('has_stories') else 'Yoq'}\n"
            f"• Bog'langan kanali: {profile.get('channel_username') or 'Yoq'}\n"
            f"• Kanal mazmuni: {profile.get('channel_summary') or 'Yoq'}\n\n"
            "Vazifa: Ushbu shaxs haqida Katta Dasturlash Mentori (Teacher) uchun 3-4 jumla lo'nda kognitiv xulosa yozing:\n"
            "1. Kimligi (yoshi taxminan, o'quvchimi, dasturchimi yoki ota-onami?)\n"
            "2. Qiziqish sohasi nima?\n"
            "3. Muloqot uslubi va unga javob berishda nimalarga e'tibor berish kerak (sodda bolalar tili yoki professional IT kodi?)."
        )

        try:
            # Miya 5 yoki Mavjud Asosiy Miya orqali xulosa olish
            pool = ai_service._frontline_clients if ai_service._frontline_clients else ai_service._groq_clients
            if pool:
                client = pool[0]
                res = await client.chat.completions.create(
                    model=config.groq_model or "openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": "Siz CoddyCamp Kognitiv Razvedka Tahlilchisisiz. Qisqa, aniq va foydali pedagogik xulosa yozing."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=350,
                )
                return res.choices[0].message.content.strip()
        except Exception as ai_err:
            logger.warning("Dosye sintezida xatolik: %s", ai_err)

        # Fallback xulosa
        return (
            f"Telegram profili tahlili: {profile.get('full_name')}. "
            f"Bio: {profile.get('bio') or 'Mavjud emas'}. "
            f"Tavsiya: Standart muloyimlik va aniq yondashuv bilan muloqot qiling."
        )

    def _format_full_dossier_card(self, profile: dict[str, Any], ai_summary: str) -> str:
        """Mentor va Vazifalar guruhi uchun to'liq chiroyli dosye kartasini formatlaydi."""
        uname_str = f"@{profile['username']}" if profile.get("username") else "Mavjud emas"
        phone_str = f"+{profile['phone']}" if profile.get("phone") else "Yashirilgan"
        bio_str = profile.get("bio") or "Kiritilmagan"
        stories_str = "Ha (Faol)" if profile.get("has_stories") else "Yo'q"

        channel_block = ""
        if profile.get("channel_username"):
            channel_block = (
                f"\n📢 **Bog'langan Kanali:** {profile['channel_username']}\n"
                f"• {profile.get('channel_summary') or 'Ma\'lumot olinmadi'}\n"
            )

        return (
            f"🕵️‍♂️ **[Miya 5: Shaxs Kognitiv Dosyesi]**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Asosiy Ma'lumotlar:**\n"
            f"• **Haqiqiy ismi:** {profile.get('full_name')}\n"
            f"• **Telegram User:** {uname_str}\n"
            f"• **Telegram ID:** `{profile['user_id']}`\n"
            f"• **Telefon raqami:** {phone_str}\n\n"
            f"📝 **Bio va Statusi:**\n"
            f"_{bio_str}_\n\n"
            f"🖼 **Profil Rasmlari va Stories:**\n"
            f"• Rasmlar soni: {profile.get('photo_count', 0)} ta\n"
            f"• Ochiq Stories: {stories_str}\n"
            f"{channel_block}\n"
            f"🧠 **AI Kognitiv Xulosasi va Tavsiya:**\n"
            f"{ai_summary}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"_Ushbu tahlil 100% yashirin o'tkazildi (foydalanuvchiga bildirilmagan)._"
        )

    async def _dispatch_dossier(self, client: Any, card_text: str) -> None:
        """Dosyeni belgilangan manzilga (Vazifalar guruhi va/yoki Mentorga) yuboradi."""
        dest = self.get_destination()
        targets = []

        if dest in ("both", "vazifalar"):
            # Vazifalar guruhi (-5388159517)
            targets.append(config.escalation_group_id or -5388159517)

        if dest in ("both", "mentor"):
            # Mentor shaxsan
            targets.append(config.mentor_user_id or 8105823872)

        for target in targets:
            try:
                await client.send_message(target, card_text)
                logger.info("📢 Miya 5 Dosyesi yuborildi -> %s", target)
            except Exception as e:
                logger.warning("Dosye yuborishda ogohlantirish (%s): %s", target, e)

    async def _worker_loop(self) -> None:
        """Ketma-ket (bitta-bitta) xavfsiz navbat ishchisi (Sequential Worker)."""
        logger.info("🏃‍♂️ Miya 5 Worker ishga tushdi, navbat kutilmoqda...")
        while self._is_running:
            try:
                user_id = await self._queue.get()
                self._enqueued_ids.discard(user_id)

                if not self.is_enabled():
                    self._queue.task_done()
                    continue

                # 1 marta qoidasi (Deduplication)
                if memory_service.is_user_dossier_exists(user_id):
                    self._queue.task_done()
                    continue

                if not self._client:
                    self._queue.task_done()
                    continue

                self._current_user = f"ID: {user_id}"
                logger.info("🕵️‍♂️ [Miya 5] Shaxs tahlil qilinmoqda: %s...", user_id)

                # Profil ma'lumotlarini o'qish (100% yashirin)
                profile = await self._inspect_single_user(self._client, user_id)
                if profile:
                    # AI xulosa sintezi
                    ai_summary = await self._synthesize_dossier_with_ai(profile)
                    card_text = self._format_full_dossier_card(profile, ai_summary)

                    # Saqlash (SQLite + MongoDB)
                    memory_service.save_user_dossier(
                        user_id=profile["user_id"],
                        username=profile.get("username", ""),
                        first_name=profile.get("first_name", ""),
                        last_name=profile.get("last_name", ""),
                        phone=profile.get("phone", ""),
                        bio=profile.get("bio", ""),
                        channel_username=profile.get("channel_username", ""),
                        channel_summary=profile.get("channel_summary", ""),
                        photo_count=profile.get("photo_count", 0),
                        has_stories=profile.get("has_stories", False),
                        dossier_text=card_text,
                    )

                    # Belgilangan manzilga yuborish
                    await self._dispatch_dossier(self._client, card_text)
                    self._total_analyzed_session += 1

                self._queue.task_done()
                self._current_user = None

                # Xavfsiz tanaffus (Telegram FloodWait dan 100% himoya)
                delay_sec = self.get_delay_seconds()
                logger.debug("⏳ Miya 5 xavfsiz tanaffus: %d soniya kutmoqda...", delay_sec)
                await asyncio.sleep(delay_sec)

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error("Miya 5 Worker xatolik: %s", loop_err)
                await asyncio.sleep(5)

    def observe_bot_message(self, message: Any) -> None:
        """Guruhdagi boshqa botlarning xabarlarini kuzatib, UI/UX andozalarini o'rganadi."""
        try:
            if not message or not getattr(message, "sender", None):
                return
            sender = message.sender
            if not getattr(sender, "bot", False):
                return

            bot_uname = getattr(sender, "username", "") or getattr(sender, "first_name", "bot")
            msg_text = getattr(message, "text", "") or ""
            if not msg_text or len(msg_text) < 15:
                return

            # Pattern turi (inline menu, quiz, error, notification)
            buttons = getattr(message, "buttons", None)
            has_buttons = bool(buttons)
            btn_texts = []
            if has_buttons:
                for row in buttons:
                    for b in row:
                        if hasattr(b, "text"):
                            btn_texts.append(b.text)

            p_type = "inline_buttons" if has_buttons else "formatted_text"
            btn_info = f" Tugmalar: [{', '.join(btn_texts[:5])}]" if btn_texts else ""
            summary = f"Format: {p_type}.{btn_info} Xabar namunasi: {msg_text[:180].replace(chr(10), ' ')}"

            memory_service.record_bot_pattern(bot_uname, p_type, summary)
            logger.debug("🤖 Miya 5 Bot patternini o'rgandi [@%s: %s]", bot_uname, p_type)
        except Exception as be:
            logger.debug("observe_bot_message ogohlantirish: %s", be)

    def get_status(self) -> dict[str, Any]:
        """Web App telemetriyasi uchun profiler holati."""
        return {
            "enabled": self.is_enabled(),
            "is_running": self._is_running,
            "is_crawling": self._is_crawling,
            "queue_length": self._queue.qsize(),
            "total_analyzed_db": memory_service.get_dossier_count(),
            "session_analyzed": self._total_analyzed_session,
            "delay_seconds": self.get_delay_seconds(),
            "destination": self.get_destination(),
            "current_user": self._current_user or "Sokin (Kutilmoqda)",
        }


# Global singleton
profile_intelligence_service = ProfileIntelligenceService()
