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
        self._force_recheck_ids: set[int] = set()
        self._is_running = False
        self._is_crawling = False
        self._worker_task: asyncio.Task | None = None
        self._current_user: str | None = None
        self._total_analyzed_session: int = 0
        self._chat_stats: dict[str, int] = {}
        self._last_stale_check_time: float = 0.0

    def is_vazifalar_group(self, chat_id: Any, title: str = "") -> bool:
        """
        Vazifalar (Boshqaruv markazi) guruhini tekshiradi.
        Ushbu guruh MUTLAQO tahlil qilinmaydi va umumiy chatlar soniga ham kiritilmaydi!
        """
        try:
            from config import get_vazifalar_chat_target_sync, normalize_group_id
            v_id = get_vazifalar_chat_target_sync()
            clean_str = str(chat_id).strip()
            norm_str = str(normalize_group_id(clean_str)) if clean_str else ""
            excluded_ids = {
                "-5388159517", "-1005388159517", "5388159517", "1005388159517",
                str(v_id), str(normalize_group_id(v_id)),
                str(memory_service.get_setting("vazifalar_group_id", "")),
                str(memory_service.get_setting("tasks_group_id", "")),
            }
            if clean_str in excluded_ids or norm_str in excluded_ids:
                return True
        except Exception:
            pass

        t_lower = (title or "").lower()
        if "vazifa" in t_lower or "boshqaruv" in t_lower:
            return True

        return False

    def get_chat_stats(self) -> dict[str, int]:
        """Barcha chatlar (Vazifalar guruhi chiqarilgan) statistikasini qaytaradi."""
        if self._chat_stats and self._chat_stats.get("total_chats", 0) > 0:
            return self._chat_stats
        try:
            import json
            raw = memory_service.get_setting("profiler_chat_stats", "")
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    self._chat_stats = loaded
                    return loaded
        except Exception:
            pass
        return {
            "total_chats": 0,
            "private_chats": 0,
            "group_chats": 0,
            "channel_chats": 0,
            "bots_chats": 0,
        }

    async def count_all_dialogs(self, client=None, limit: int = 500) -> dict[str, int]:
        """
        Barcha mavjud chatlar (shaxsiy, guruhlar, kanallar) sonini sanaydi.
        Vazifalar guruhi va Mentor hisobga olinmaydi va tahlil qilinmaydi!
        """
        cl = client or self._client
        if not cl:
            try:
                import main
                cl = getattr(main, "CURRENT_CLIENT", None)
            except Exception:
                pass
        if not cl:
            return self.get_chat_stats()

        private_count = 0
        groups_count = 0
        channels_count = 0
        bots_count = 0

        try:
            async for dialog in cl.iter_dialogs(limit=limit):
                d_id = dialog.id
                d_name = getattr(dialog, "name", "") or ""

                # 1. Vazifalar guruhini MUTLAQO chiqarib tashlash
                if self.is_vazifalar_group(d_id, d_name):
                    continue

                entity = getattr(dialog, "entity", None)
                if getattr(entity, "is_self", False):
                    continue

                uid = d_id or getattr(entity, "id", None)
                if uid in (config.mentor_user_id, 8105823872):
                    continue

                if dialog.is_user:
                    if getattr(entity, "bot", False):
                        bots_count += 1
                    else:
                        private_count += 1
                elif dialog.is_group:
                    groups_count += 1
                elif dialog.is_channel:
                    channels_count += 1

            total = private_count + groups_count + channels_count
            self._chat_stats = {
                "total_chats": total,
                "private_chats": private_count,
                "group_chats": groups_count,
                "channel_chats": channels_count,
                "bots_chats": bots_count,
            }
            try:
                import json
                memory_service.set_setting("profiler_chat_stats", json.dumps(self._chat_stats))
            except Exception:
                pass
        except Exception as e:
            logger.error("count_all_dialogs xatolik: %s", e)

        return self.get_chat_stats()

    def start(self, client=None) -> None:
        """Profiler ishchi fon daemonini ishga tushiradi."""
        if client:
            self._client = client
        if self._is_running:
            return
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

    def enqueue_user(self, user_id: int, force: bool = False) -> bool:
        """
        Foydalanuvchini navbatga qo'shadi.
        Agar force=True bo'lsa, mavjud dosye bo'lishiga qaramay yangidan tekshirish uchun navbatga qo'shiladi.
        Aks holda, oldin tahlil qilingan bo'lsa yoki hozir navbatda bo'lsa, o'tkazib yuboriladi.
        """
        if not self.is_enabled() or not user_id or user_id <= 0:
            return False

        # Mentor yoki botning o'zi bo'lsa tekshirilmaydi
        if user_id in (config.mentor_user_id, 8105823872):
            return False

        # 1. Oldin tahlil qilinganmi? (force bo'lmasa tekshiriladi)
        if not force and memory_service.is_user_dossier_exists(user_id):
            return False

        # 2. Hozir navbatdami?
        if user_id in self._enqueued_ids:
            return False

        if force:
            self._force_recheck_ids.add(user_id)

        self._enqueued_ids.add(user_id)
        self._queue.put_nowait(user_id)
        logger.debug("📥 Profiler navbatiga qo'shildi: user_id=%s (Force: %s, Navbat hajmi: %d)", user_id, force, self._queue.qsize())
        return True

    def is_auto_recheck_enabled(self) -> bool:
        """Har 3 kunda avto-takroran tekshiruv yoqilganligini tekshiradi."""
        return memory_service.get_setting("profiler_auto_recheck_enabled", "true").lower() == "true"

    def set_auto_recheck_enabled(self, enabled: bool) -> None:
        """Har 3 kunda avto-takroran tekshiruvni yoqish / o'chirish."""
        memory_service.set_setting("profiler_auto_recheck_enabled", "true" if enabled else "false")

    def get_auto_recheck_days(self) -> int:
        """Avto-takroran tekshiruv davri (standart: 3 kun)."""
        val = memory_service.get_setting("profiler_auto_recheck_days", "3")
        try:
            return max(1, min(30, int(val)))
        except ValueError:
            return 3

    def set_auto_recheck_days(self, days: int) -> None:
        """Avto-takroran tekshiruv kunini belgilash."""
        d = max(1, min(30, int(days)))
        memory_service.set_setting("profiler_auto_recheck_days", str(d))

    def recheck_user(self, user_id: int) -> bool:
        """Bitta foydalanuvchini majburiy yangidan tekshirish navbatiga qo'yadi."""
        return self.enqueue_user(user_id, force=True)

    def recheck_all_users(self, max_limit: int = 1000) -> int:
        """Barcha mavjud dosyelarni navbatga terib, yangidan tekshirishni boshlaydi."""
        user_ids = memory_service.get_all_dossier_user_ids(limit=max_limit)
        added = 0
        for uid in user_ids:
            if self.enqueue_user(uid, force=True):
                added += 1
        logger.info("🔁 Barcha dosyelar (%d ta) yangidan tekshiruv navbatiga olindi.", added)
        return added

    def check_stale_dossiers_for_recheck(self, days: int = 3, limit: int = 100) -> int:
        """
        Agar avto-takroran tekshiruv yoqilgan bo'lsa, oxirgi tahlili 3 kundan oshgan
        foydalanuvchilarni topib, avtomatik yangilanish navbatiga qo'shadi.
        """
        if not self.is_auto_recheck_enabled():
            return 0
        days_cfg = self.get_auto_recheck_days()
        stale_ids = memory_service.get_stale_user_dossier_ids(days=days_cfg, limit=limit)
        added = 0
        for uid in stale_ids:
            if self.enqueue_user(uid, force=True):
                added += 1
        if added > 0:
            logger.info("⏳ Avto-takroran tekshiruv: %d ta eski dosye (>=%d kun) yangilanish navbatiga qo'shildi.", added, days_cfg)
        return added

    async def scan_historic_dialogs(self, client=None, limit: int = 500) -> dict[str, Any]:
        """
        Mavjud barcha dialoglarni skanerlab, umumiy statistika to'playdi
        va tahlil qilinmagan foydalanuvchilarni navbatga terib chiqadi.
        FAKAT: Vazifalar guruhi MUTLAQO analiz qilinmaydi va hisobga olinmaydi!
        """
        cl = client or self._client
        if not cl:
            try:
                import main
                cl = getattr(main, "CURRENT_CLIENT", None)
            except Exception:
                pass

        if cl:
            if not self._client:
                self._client = cl
            if not self._is_running:
                self.start(cl)

        if not cl:
            logger.warning("Historic Dialog Scan: Telethon client mavjud emas.")
            return {"added": 0, "chat_stats": self.get_chat_stats()}

        if self._is_crawling:
            logger.info("Historic Dialog Scan allaqachon davom etmoqda.")
            return {"added": self._queue.qsize(), "chat_stats": self.get_chat_stats()}

        self._is_crawling = True
        added_count = 0
        private_count = 0
        groups_count = 0
        channels_count = 0
        bots_count = 0

        try:
            logger.info("🔍 Tarixiy chatlarni skanerlash boshlandi (Limit: %d)...", limit)
            async for dialog in cl.iter_dialogs(limit=limit):
                d_id = dialog.id
                d_name = getattr(dialog, "name", "") or ""

                # 1. Vazifalar guruhini MUTLAQO chiqarib tashlash (analiz qilinmaydi, hisobga olinmaydi)
                if self.is_vazifalar_group(d_id, d_name):
                    logger.debug("🛡️ Vazifalar guruhi chiqarib tashlandi: %s (%s)", d_name, d_id)
                    continue

                entity = getattr(dialog, "entity", None)
                if getattr(entity, "is_self", False):
                    continue

                uid = d_id or getattr(entity, "id", None)
                if uid in (config.mentor_user_id, 8105823872):
                    continue

                if dialog.is_user:
                    if getattr(entity, "bot", False):
                        bots_count += 1
                    else:
                        private_count += 1
                        if uid and uid > 0:
                            if not memory_service.is_user_dossier_exists(uid) and uid not in self._enqueued_ids:
                                self._enqueued_ids.add(uid)
                                self._queue.put_nowait(uid)
                                added_count += 1
                elif dialog.is_group:
                    groups_count += 1
                    try:
                        # Guruh a'zolarini ham tahlil qilish uchun xavfsiz navbatga teramiz
                        async for participant in cl.iter_participants(dialog.entity, limit=200):
                            if getattr(participant, "bot", False) or getattr(participant, "is_self", False):
                                continue
                            p_uid = getattr(participant, "id", None)
                            if not p_uid or p_uid in (config.mentor_user_id, 8105823872):
                                continue
                            if not memory_service.is_user_dossier_exists(p_uid) and p_uid not in self._enqueued_ids:
                                self._enqueued_ids.add(p_uid)
                                self._queue.put_nowait(p_uid)
                                added_count += 1
                    except Exception as g_err:
                        logger.debug("Guruh a'zolarini skanerlashda xatolik (%s): %s", d_name, g_err)
                elif dialog.is_channel:
                    channels_count += 1

            total_chats = private_count + groups_count + channels_count
            self._chat_stats = {
                "total_chats": total_chats,
                "private_chats": private_count,
                "group_chats": groups_count,
                "channel_chats": channels_count,
                "bots_chats": bots_count,
            }
            try:
                import json
                memory_service.set_setting("profiler_chat_stats", json.dumps(self._chat_stats))
            except Exception:
                pass

            logger.info(
                "✅ Tarixiy chatlar skanerlandi: Jami %d ta chat (Shaxsiy: %d, Guruh: %d, Kanal: %d). %d ta yangi shaxs navbatga qo'shildi.",
                total_chats, private_count, groups_count, channels_count, added_count
            )
        except Exception as e:
            logger.error("scan_historic_dialogs xatolik: %s", e)
        finally:
            self._is_crawling = False

        return {
            "added": added_count,
            "chat_stats": self.get_chat_stats(),
        }

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

            # 2. Profil rasmlari va video avatar tekshiruvi
            photo_count = 0
            has_video_avatar = False
            try:
                photos = await client.get_profile_photos(entity, limit=5)
                photo_count = len(photos) if photos else 0
                if photos:
                    for p in photos:
                        if getattr(p, "video_sizes", None) or getattr(p, "has_video", False):
                            has_video_avatar = True
                            break
            except Exception:
                pass

            # 3. Stories mavjudligi
            has_stories = False
            try:
                if full_user and getattr(full_user, "stories", None):
                    has_stories = True
            except Exception:
                pass

            # 4. Bog'langan kanal yoki tashqi linklar tahlili (Media, Voice, Video, Obunachilar)
            channel_username = ""
            channel_summary = ""
            channel_is_private = False
            channel_subscribers = 0
            channel_media_stats = {"photos": 0, "videos": 0, "voices": 0, "audios": 0}

            # Bio yoki profil ichidan @kanal yoki t.me/kanal qidirish
            channel_match = re.search(r"@([a-zA-Z0-9_]{4,32})|t\.me/([a-zA-Z0-9_]{4,32})|t\.me/\+([a-zA-Z0-9_-]+)", bio)
            if channel_match:
                ch_tag = channel_match.group(1) or channel_match.group(2)
                ch_invite = channel_match.group(3)

                if ch_invite:
                    channel_username = f"t.me/+{ch_invite}"
                    channel_is_private = True
                    channel_summary = "🔒 Yopiq (private) kanal yoki taklif havolasi. Ichki postlarni yopiq bo'lgani sababli o'qib bo'lmadi."
                elif ch_tag and ch_tag.lower() != (username or "").lower():
                    channel_username = f"@{ch_tag}"
                    try:
                        ch_entity = await client.get_entity(ch_tag)
                        if ch_entity:
                            ch_title = getattr(ch_entity, "title", "")
                            
                            # Obunachilar sonini olish
                            try:
                                from telethon.tl.functions.channels import GetFullChannelRequest
                                ch_full_res = await client(GetFullChannelRequest(ch_entity))
                                if ch_full_res and getattr(ch_full_res, "full_chat", None):
                                    channel_subscribers = getattr(ch_full_res.full_chat, "participants_count", 0) or 0
                            except Exception:
                                pass

                            # Kanalning oxirgi 8 ta postini va undagi media turlarini chuqur ko'rish
                            posts_snippets = []
                            post_count = 0
                            async for post_msg in client.iter_messages(ch_entity, limit=8):
                                post_count += 1
                                if post_msg.text:
                                    posts_snippets.append(post_msg.text[:120].replace("\n", " "))
                                
                                # Media turlarini aniqlash (ovozli, video, rasm)
                                if post_msg.photo:
                                    channel_media_stats["photos"] += 1
                                elif post_msg.voice:
                                    channel_media_stats["voices"] += 1
                                elif post_msg.audio:
                                    channel_media_stats["audios"] += 1
                                elif post_msg.video or getattr(post_msg, "video_note", False):
                                    channel_media_stats["videos"] += 1

                            summary_posts = " | ".join(posts_snippets[:4]) if posts_snippets else "Postlar matnsiz yoki faqat media"
                            
                            media_desc_parts = []
                            if channel_media_stats["photos"]:
                                media_desc_parts.append(f"{channel_media_stats['photos']} ta rasm")
                            if channel_media_stats["videos"]:
                                media_desc_parts.append(f"{channel_media_stats['videos']} ta video")
                            if channel_media_stats["voices"] or channel_media_stats["audios"]:
                                v_tot = channel_media_stats["voices"] + channel_media_stats["audios"]
                                media_desc_parts.append(f"{v_tot} ta ovozli/audio xabar")

                            media_str = ", ".join(media_desc_parts) if media_desc_parts else "mediasiz"
                            subs_str = f"{channel_subscribers} ta obunachi" if channel_subscribers else "Obunachilar soni yashirin"

                            channel_summary = (
                                f"Kanal nomi: '{ch_title}' ({subs_str}). "
                                f"So'nggi postlarda: {media_str}. "
                                f"Mavzular / matnlar: {summary_posts}"
                            )
                    except Exception as ch_err:
                        err_str = str(ch_err).lower()
                        if "private" in err_str or "forbidden" in err_str or "cannot find" in err_str:
                            channel_is_private = True
                            channel_summary = f"🔒 Yopiq (private) yoki maxfiy kanal (@{ch_tag}). Obuna bo'lmasdan ko'rib bo'lmaydi."
                        else:
                            channel_summary = f"Kanal havolasi: @{ch_tag} (Ma'lumot cheklangan)"

            # 5. Xabarlarni to'plash: to'g'ridan-to'g'ri chat + guruh bazasi (birlashtirib, ko'proq namuna)
            #    Aniqlik uchun signal soni muhim: faqat SHAXS o'zi yozgan matnlarni alohida yig'amiz.
            recent_user_messages = []       # ko'rsatish uchun (Biz/U)
            own_texts = []                   # faqat shaxsning o'z matnlari (til/rol/yosh tahlili uchun)
            try:
                async for user_msg in client.iter_messages(entity, limit=40):
                    if user_msg and user_msg.text:
                        clean = user_msg.text[:220].replace(chr(10), " ")
                        if user_msg.out:
                            recent_user_messages.append(f"Biz: {clean}")
                        else:
                            recent_user_messages.append(f"U: {clean}")
                            own_texts.append(user_msg.text)
            except Exception:
                pass

            # Guruhlardagi yozishmalar bazasidan ham (shaxsiy chat kam bo'lsa qo'shimcha signal)
            try:
                with memory_service._get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 30",
                        (user_id,)
                    )
                    for r_role, r_content in cur.fetchall():
                        if r_content:
                            if r_role == "user":
                                own_texts.append(r_content)
                                if len(recent_user_messages) < 45:
                                    recent_user_messages.append(f"U: {r_content[:220].replace(chr(10), ' ')}")
            except Exception:
                pass

            own_msg_count = len(own_texts)
            own_text_blob = " ".join(own_texts)

            # 5.1 Til / shevani aniqlash (uz / ru / en)
            langs = set()
            low_blob = own_text_blob.lower()
            if re.search(r"[а-яё]", low_blob):
                langs.add("ruscha")
            if re.search(r"[a-z]", low_blob) and re.search(r"\b(the|and|please|hello|thanks|how|what)\b", low_blob):
                langs.add("inglizcha")
            if re.search(r"[oʻgʻ]|['`]|\b(salom|rahmat|ustoz|yaxshi|qachon|kerak|bo'l|iltimos)\b", low_blob):
                langs.add("o'zbekcha")
            language_str = ", ".join(sorted(langs)) if langs else "Aniqlanmadi (yetarli matn yo'q)"

            # 6. Biz bilan umumiy guruhlarini Telethon orqali aniqlash (kuchli signal manbai)
            common_chats = []
            try:
                from telethon.tl.functions.messages import GetCommonChatsRequest
                common_res = await client(GetCommonChatsRequest(user_id=entity, max_id=0, limit=100))
                if common_res and getattr(common_res, "chats", None):
                    for ch in common_res.chats:
                        ch_t = getattr(ch, "title", "")
                        if ch_t and ch_t not in common_chats:
                            common_chats.append(ch_t)
            except Exception as cc_err:
                logger.debug("Common chats olishda ogohlantirish (%s): %s", user_id, cc_err)

            # 7. Ijtimoiy rol ishoralari — har bir signalga aniq izoh (AI xolis baholashi uchun)
            role_clues = []
            common_chats_str = " ".join(common_chats).lower() if common_chats else ""
            if any(kw in common_chats_str for kw in ["ota-ona", "ota ona", "parents", "parent", "majlis", "родител"]):
                role_clues.append("KUCHLI: Ota-onalar guruhida a'zo")
            if any(kw in common_chats_str for kw in ["python", "backend", "frontend", "dasturlash", "kurs", "it academy", "coddy", "student", "sinf", "guruh"]):
                role_clues.append("O'RTA: Dasturlash/o'quv kursi guruhida a'zo")

            grade_match = re.search(r"\b(\d{1,2})[- ]?(sinf|klass|класс)\b", common_chats_str)
            if grade_match:
                role_clues.append(f"KUCHLI: '{grade_match.group(1)}-sinf' guruhida (maktab o'quvchisi)")

            low_own = own_text_blob.lower()
            if any(kw in low_own for kw in ["o'g'lim", "og'lim", "qizim", "farzandim", "bolam", "farzandimni", "мой сын", "моя дочь"]):
                role_clues.append("KUCHLI: O'z farzandi haqida gapirgan (Ota-ona)")
            if any(kw in low_own for kw in ["to'lov qildim", "tolov qildim", "pul o'tkaz", "oplatil", "kvitansiya"]):
                role_clues.append("O'RTA: To'lov haqida gapirgan (Ota-ona yoki mijoz)")
            if any(kw in low_own for kw in ["uyga vazifa", "kodim", "xato chiqdi", "error", "vazifa", "tushunmadim", "domla", "ustoz", "dars", "kod ishlamayapti"]):
                role_clues.append("O'RTA: Dars/vazifa/kod haqida so'ragan (O'quvchi)")
            if any(kw in low_own for kw in ["narx", "buyurtma", "yetkazib", "sotib", "mahsulot", "xizmat", "zakaz", "dostavka"]):
                role_clues.append("O'RTA: Xarid/xizmat haqida so'ragan (Mijoz)")

            # 8. Yosh ishoralari — FAQAT ishonchli manbalar (xato "yil" topishning oldini olamiz)
            age_clues = []
            now_year = 2026
            # 8a. Ochiq yosh e'loni: "17 yosh", "мне 25", "25 yoshdaman"
            for m in re.finditer(r"\b(\d{1,2})\s*(yosh|yoshda|yoshdaman|лет|года)\b", low_own):
                a = int(m.group(1))
                if 6 <= a <= 80:
                    age_clues.append(f"KUCHLI: O'zi yoshini aytgan — {a} yosh")
            # 8b. To'liq tug'ilgan yil (2000, 1998) — ism/username/bio ichida
            id_text = f"{username} {full_name} {bio}".lower()
            for ym in re.findall(r"(?:19[7-9]\d|20[01]\d)", id_text):
                y = int(ym)
                if 1970 <= y <= 2015:
                    age_clues.append(f"O'RTA: Username/ismda tug'ilgan yil — {y} (~{now_year - y} yosh)")
            # 8c. Username oxiridagi 2 xonali yil qo'shimchasi: ali_05, kamol07 (harfdan keyin kelsa)
            um = re.search(r"[a-z](0[0-9]|1[0-5])\b", (username or "").lower())
            if um:
                yy = int(um.group(1))
                age_clues.append(f"ZAIF: Username oxirida '{yy:02d}' — ehtimoliy 20{yy:02d} (~{now_year - (2000 + yy)} yosh)")

            return {
                "user_id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "username": username,
                "phone": phone,
                "bio": bio,
                "photo_count": photo_count,
                "has_video_avatar": has_video_avatar,
                "has_stories": has_stories,
                "channel_username": channel_username,
                "channel_summary": channel_summary,
                "channel_is_private": channel_is_private,
                "channel_subscribers": channel_subscribers,
                "channel_media_stats": channel_media_stats,
                "common_chats": common_chats,
                "own_msg_count": own_msg_count,
                "language": language_str,
                "role_clues": "; ".join(role_clues) if role_clues else "Ochiq rol belgisi topilmadi",
                "age_clues": "; ".join(dict.fromkeys(age_clues)) if age_clues else "Ishonchli yosh belgisi topilmadi",
                "recent_chat_context": " // ".join(recent_user_messages[:30]) if recent_user_messages else "Yozishmalar tarixi mavjud emas",
            }
        except Exception as e:
            logger.warning("Foydalanuvchi profilini o'qishda xatolik (%s): %s", user_id, e)
            return None

    async def _synthesize_dossier_with_ai(self, profile: dict[str, Any], existing_dossier: dict[str, Any] | None = None) -> str:
        """Miya 5 orqali foydalanuvchining to'liq kognitiv dosyesini sintez qiladi."""
        from services.ai_service import ai_service

        video_avatar_str = "Ha (Video profil)" if profile.get("has_video_avatar") else "Yo'q"
        existing_info = ""
        if existing_dossier and existing_dossier.get("dossier_text"):
            existing_info = (
                f"\n\n--- AVVALGI TAHLIL TARIXI ---\n"
                f"{existing_dossier['dossier_text'][:350]}\n"
                f"--- TAHLIL YANGILANISHI TALABI ---\n"
                f"Ushbu shaxs qayta tekshirilmoqda. Agar uning ismi, bio, kanali yoki yozishmalarida yangiliklar bo'lsa, "
                f"avvalgi xulosani yangilang, to'g'rilang va boyiting.\n"
            )

        common_chats_list = profile.get("common_chats", [])
        common_chats_str = ", ".join(common_chats_list) if common_chats_list else "Umumiy guruhlar aniqlanmadi"
        role_clues_str = profile.get("role_clues") or "Aniq rol belgisi yo'q"
        own_msg_count = profile.get("own_msg_count", 0)

        prompt = (
            f"Telegram foydalanuvchisi haqida to'plangan ochiq signallar:\n"
            f"• Ismi: {profile.get('full_name')}\n"
            f"• Username: @{profile.get('username') or 'yoq'}\n"
            f"• Bio / Status: {profile.get('bio') or 'Kiritilmagan'}\n"
            f"• Umumiy guruhlari: {common_chats_str}\n"
            f"• Rol belgilari (KUCHLI/O'RTA/ZAIF darajali): {role_clues_str}\n"
            f"• Yosh belgilari (KUCHLI/O'RTA/ZAIF): {profile.get('age_clues')}\n"
            f"• Ishlatgan tili: {profile.get('language')}\n"
            f"• Undan olingan xabarlar soni: {own_msg_count} ta\n"
            f"• Bog'langan kanali: {profile.get('channel_username') or 'Yoq'} — {profile.get('channel_summary') or ''}\n"
            f"• So'nggi yozishmalar: {profile.get('recent_chat_context') or 'Yozishmalar mavjud emas'}\n"
            f"{existing_info}\n"
            "VAZIFA: Faqat yuqoridagi signallarga tayanib, shaxsni baholang. QAT'IY QOIDALAR:\n"
            "1. TAXMIN QILMANG. Agar signal yetarli bo'lmasa, qiymatni \"Aniq emas\" deb qo'ying va ishonchni past bering.\n"
            "2. Har bir maydonga 0-100 ishonch foizi bering. Ishonch faqat MUSTAQIL signallar bir-birini tasdiqlaganda yuqori bo'ladi:\n"
            "   - KUCHLI belgi yoki 2+ signal mos kelsa: 80-95.\n"
            "   - Bitta O'RTA belgi: 55-70. Faqat ZAIF belgi yoki umumiy taxmin: 20-45.\n"
            "   - Hech qanday to'g'ridan-to'g'ri signal yo'q (masalan xabar 0 ta): 10-30 va \"Aniq emas\".\n"
            "3. Yoshni faqat KUCHLI/O'RTA yosh belgisi bo'lsa aniq bering; aks holda rol va leksikadan keng oraliq (masalan 25-45) va past ishonch.\n"
            "FAQAT quyidagi JSON'ni qaytaring (boshqa matnsiz):\n"
            "{\n"
            '  "role": "Oquvchi | Ota-ona | Mijoz/Tadbirkor | Hamkasb/Ustoz | Aniq emas",\n'
            '  "role_confidence": 0-100,\n'
            '  "age_range": "masalan 14-17 yoki Aniq emas",\n'
            '  "age_confidence": 0-100,\n'
            '  "profession": "kasbi yoki Aniq emas",\n'
            '  "communication_style": "u bilan qanday ohangda gaplashish (1 jumla)",\n'
            '  "summary": "2-3 jumlalik xolis xulosa; qaror signallar bilan asoslansin",\n'
            '  "overall_confidence": 0-100\n'
            "}"
        )

        raw = ""
        pool = ai_service._frontline_clients if ai_service._frontline_clients else ai_service._groq_clients
        try:
            if pool:
                client = pool[0]
                res = await client.chat.completions.create(
                    model=config.groq_model or "openai/gpt-oss-120b",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Siz aniq va xolis Kognitiv Shaxs Tahlilchisiz. Faqat berilgan signallarga tayanasiz, "
                                "hech narsani to'qib chiqarmaysiz. Dalil kam bo'lsa — buni ochiq tan olib, past ishonch va "
                                "\"Aniq emas\" qaytarasiz. Faqat valid JSON qaytarasiz."
                            )
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=700,
                    response_format={"type": "json_object"},
                )
                raw = (res.choices[0].message.content or "").strip()
        except Exception as ai_err:
            logger.warning("Dosye sintezida (JSON) xatolik: %s", ai_err)
            # response_format qo'llab-quvvatlanmasa, oddiy rejimda qayta urinish
            try:
                if pool:
                    res = await pool[0].chat.completions.create(
                        model=config.groq_model or "openai/gpt-oss-120b",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=700,
                    )
                    raw = (res.choices[0].message.content or "").strip()
            except Exception as ai_err2:
                logger.warning("Dosye sintezida (fallback) xatolik: %s", ai_err2)

        parsed = self._parse_dossier_json(raw)
        if parsed:
            return self._render_dossier_analysis(parsed, own_msg_count)

        if raw:
            return raw
        return (
            f"Telegram profili tahlili: {profile.get('full_name')}. "
            f"Bio: {profile.get('bio') or 'Mavjud emas'}. Signal kam — ishonch past. "
            f"Tavsiya: standart muloyimlik bilan muloqot qiling."
        )

    @staticmethod
    def _parse_dossier_json(raw: str) -> dict | None:
        """AI qaytargan matndan JSON obyektni ajratib oladi (kod bloklari va ortiqcha matndan tozalab)."""
        if not raw:
            return None
        import json
        text = raw.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _conf_badge(pct: int) -> str:
        """Ishonch foizini vizual belgiga aylantiradi."""
        try:
            p = int(pct)
        except (TypeError, ValueError):
            p = 0
        if p >= 80:
            return f"🟢 {p}% (yuqori)"
        if p >= 55:
            return f"🟡 {p}% (o'rta)"
        return f"🔴 {p}% (past — ehtiyot bo'ling)"

    def _render_dossier_analysis(self, d: dict, own_msg_count: int) -> str:
        """Parslangan JSON tahlildan ishonch foizli, o'qishga qulay xulosa yasaydi."""
        role = str(d.get("role") or "Aniq emas").strip()
        age = str(d.get("age_range") or "Aniq emas").strip()
        prof = str(d.get("profession") or "Aniq emas").strip()
        style = str(d.get("communication_style") or "Standart hurmatli muloqot").strip()
        summary = str(d.get("summary") or "").strip()
        overall = d.get("overall_confidence", d.get("role_confidence", 0))

        lines = [
            f"🎯 **Ijtimoiy rol:** {role} — {self._conf_badge(d.get('role_confidence', 0))}",
            f"🎂 **Yosh oralig'i:** {age} — {self._conf_badge(d.get('age_confidence', 0))}",
            f"💼 **Kasbi/faoliyati:** {prof}",
            f"💬 **Tavsiya etilgan muloqot:** {style}",
        ]
        if summary:
            lines.append(f"\n📌 {summary}")
        lines.append(f"\n📊 **Umumiy ishonch:** {self._conf_badge(overall)} · (tahlil {own_msg_count} ta xabar asosida)")
        if own_msg_count == 0:
            lines.append("⚠️ _Bu shaxsdan hech qanday xabar topilmadi — xulosa faqat profil/guruhlarga asoslangan, ishonch past._")
        return "\n".join(lines)

    def _format_full_dossier_card(self, profile: dict[str, Any], ai_summary: str, is_recheck: bool = False) -> str:
        """Mentor va Vazifalar guruhi uchun to'liq chiroyli dosye kartasini formatlaydi."""
        uname_str = f"@{profile['username']}" if profile.get("username") else "Mavjud emas"
        phone_str = f"+{profile['phone']}" if profile.get("phone") else "Yashirilgan"
        bio_str = profile.get("bio") or "Kiritilmagan"
        stories_str = "Ha (Faol)" if profile.get("has_stories") else "Yo'q"
        video_av_str = "Ha (Video profil)" if profile.get("has_video_avatar") else "Faqat rasm"

        channel_block = ""
        if profile.get("channel_username"):
            ch_status = "🔒 Yopiq (Private)" if profile.get("channel_is_private") else "🌐 Ochiq (Public)"
            subs_text = f" • Obunachilar: {profile.get('channel_subscribers')} ta" if profile.get("channel_subscribers") else ""
            channel_block = (
                f"\n📢 **Bog'langan Kanali ({ch_status}{subs_text}):** {profile['channel_username']}\n"
                f"• {profile.get('channel_summary') or 'Ma\'lumot olinmadi'}\n"
            )

        common_groups_str = ", ".join(profile.get("common_chats", [])) if profile.get("common_chats") else "Mavjud emas (Faqat shaxsiy chat)"

        header_title = "🕵️‍♂️ **[Miya 5: Shaxs Kognitiv Dosyesi (♻️ Qayta tekshirildi / Yangilandi)]**" if is_recheck else "🕵️‍♂️ **[Miya 5: Shaxs Kognitiv Dosyesi]**"

        return (
            f"{header_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Asosiy Ma'lumotlar:**\n"
            f"• **Haqiqiy ismi:** {profile.get('full_name')}\n"
            f"• **Telegram User:** {uname_str}\n"
            f"• **Telegram ID:** `{profile['user_id']}`\n"
            f"• **Telefon raqami:** {phone_str}\n"
            f"• **Biz bilan umumiy guruhlari:** {common_groups_str}\n\n"
            f"📝 **Bio va Statusi:**\n"
            f"_{bio_str}_\n\n"
            f"🖼 **Profil Rasmlari, Video va Stories:**\n"
            f"• Rasmlar soni: {profile.get('photo_count', 0)} ta\n"
            f"• Video Avatar: {video_av_str}\n"
            f"• Ochiq Stories: {stories_str}\n"
            f"{channel_block}\n"
            f"🧠 **AI Kognitiv Tahlili va Tavsiya:**\n"
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

                is_force = user_id in self._force_recheck_ids
                self._force_recheck_ids.discard(user_id)

                # 1 marta qoidasi (Deduplication) - faqat force bo'lmaganda tekshiriladi
                if not is_force and memory_service.is_user_dossier_exists(user_id):
                    self._queue.task_done()
                    continue

                if not self._client:
                    try:
                        import main
                        self._client = getattr(main, "CURRENT_CLIENT", None)
                    except Exception:
                        pass
                if not self._client:
                    self._queue.task_done()
                    await asyncio.sleep(2.0)
                    continue

                self._current_user = f"ID: {user_id}"
                action_word = "qayta tekshirilmoqda (yangilanmoqda)" if is_force else "tahlil qilinmoqda"
                logger.info("🕵️‍♂️ [Miya 5] Shaxs %s: %s...", action_word, user_id)

                # Profil ma'lumotlarini o'qish (100% yashirin)
                profile = await self._inspect_single_user(self._client, user_id)
                if profile:
                    # Mavjud eski dosye bo'lsa olish (yangilash va to'g'rilash uchun)
                    existing_dossier = memory_service.get_user_dossier(user_id)

                    # AI xulosa sintezi
                    ai_summary = await self._synthesize_dossier_with_ai(profile, existing_dossier=existing_dossier)
                    card_text = self._format_full_dossier_card(profile, ai_summary, is_recheck=bool(existing_dossier))

                    # Saqlash (SQLite + MongoDB)
                    common_chats_saved = ", ".join(profile.get("common_chats", [])) if profile.get("common_chats") else ""
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
                        common_chats=common_chats_saved,
                    )

                    # Belgilangan manzilga yuborish
                    await self._dispatch_dossier(self._client, card_text)
                    self._total_analyzed_session += 1

                self._queue.task_done()
                self._current_user = None

                # Navbat bo'shaganda va avto-takroran tekshiruv yoqilgan bo'lsa
                if self._queue.empty() and self.is_auto_recheck_enabled():
                    try:
                        import time
                        now_ts = time.time()
                        if now_ts - self._last_stale_check_time > 1800:  # Har 30 daqiqada tekshirish
                            self._last_stale_check_time = now_ts
                            self.check_stale_dossiers_for_recheck(days=self.get_auto_recheck_days())
                    except Exception as sce:
                        logger.debug("Auto recheck check ogohlantirish: %s", sce)

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

            # Vazifalar guruhi MUTLAQO tekshirilmaydi
            chat_id = getattr(message, "chat_id", None)
            if chat_id and self.is_vazifalar_group(chat_id):
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

    async def scan_and_analyze_admin_chat(self, client=None, limit: int = 80) -> dict[str, Any]:
        """
        CoddyCamp Sergeli ma'muriyati (@coddycamp_sergeli / 7754389150) chatini
        Telethon orqali chuqur skanerlab, muloqot tarixi, mavzular va kelishuvlarni
        AI orqali tahlil qiladi va Kognitiv Dosye (admin_dossier) shakllantiradi.
        Hisobot darhol Vazifalar guruhiga yuboriladi.
        """
        cl = client or self._client
        if not cl:
            try:
                import main
                cl = getattr(main, "CURRENT_CLIENT", None)
            except Exception:
                pass
        if not cl:
            logger.warning("scan_and_analyze_admin_chat: Telethon client mavjud emas.")
            return {"ok": False, "error": "Telethon client topilmadi"}

        logger.info("🔍 CoddyCamp ma'muriyati (@coddycamp_sergeli) chati tahlili boshlanmoqda (Limit: %d)...", limit)
        target_entities = ["@coddycamp_sergeli", "coddycamp_sergeli", 7754389150]
        entity = None
        for t in target_entities:
            try:
                entity = await cl.get_entity(t)
                if entity:
                    break
            except Exception:
                continue

        if not entity:
            logger.warning("scan_and_analyze_admin_chat: @coddycamp_sergeli entity topilmadi.")
            return {"ok": False, "error": "@coddycamp_sergeli entity topilmadi"}

        raw_messages = []
        try:
            async for msg in cl.iter_messages(entity, limit=limit):
                text = (msg.text or "").strip()
                if text:
                    is_me = msg.out or (msg.sender_id in (config.mentor_user_id, 8105823872))
                    sender_tag = "Ustoz Nuriddin" if is_me else "CoddyCamp Ma'muriyati (@coddycamp_sergeli)"
                    raw_messages.append(f"{sender_tag}: {text}")
        except Exception as read_err:
            logger.error("Admin chat xabarlarini o'qishda xatolik: %s", read_err)
            return {"ok": False, "error": str(read_err)}

        if not raw_messages:
            logger.info("Admin chatda hali xabarlar mavjud emas.")
            empty_summary = (
                "CoddyCamp Sergeli filiali ma'muriyati. "
                "Asosiy mavzular: dars jadvali, xonalar, o'quvchilar davomati va to'lovlari. "
                "Muloqot uslubi: rasmiy, hamkasblarcha va hurmat bilan."
            )
            memory_service.set_setting("admin_dossier_coddycamp_sergeli", empty_summary)
            return {"ok": True, "dossier": empty_summary, "msg_count": 0}

        # Xabarlarni xronologik tartibga solamiz
        dialog_transcript = "\n".join(reversed(raw_messages[:70]))

        prompt = (
            "Quyida dasturlash ustozi Nuriddin Mahmudov va CoddyCamp Sergeli filiali Ma'muriyati (@coddycamp_sergeli) "
            "o'rtasidagi Telegram yozishmalari tarixi keltirilgan.\n\n"
            f"=== CHAT TARIXI ===\n{dialog_transcript}\n=== CHAT TUGADI ===\n\n"
            "Vazifa: Ushbu chatni tahlil qilib, Ustozning AI Yordamchisi (Agente) uchun ma'muriyat bilan qanday muloqot qilish bo'yicha "
            "Kognitiv Dosye (qo'llanma) tuzing:\n"
            "1. Ko'rilgan asosiy masalalar (davomat, to'lov, guruhlar, dars vaqtlari, xonalar va h.k.);\n"
            "2. Ma'muriyatning muloqot tili (o'zbekcha / ruscha) va ohangi;\n"
            "3. O'zaro kelishilgan qoidalar va odatlar;\n"
            "4. AI assistent ma'muriyatga qanday javob berishi kerak (lo'nda, aniq, hurmat bilan, dasturlash darsi o'tmasdan).\n"
            "Javobni aniq, punktma-punkt, 4-6 banddan iborat lo'nda tahlil ko'rinishida yozing."
        )

        dossier_text = ""
        try:
            from services.ai_service import ai_service
            pool = ai_service._frontline_clients if ai_service._frontline_clients else ai_service._groq_clients
            if pool:
                llm = pool[0]
                res = await llm.chat.completions.create(
                    model=config.groq_model,
                    messages=[
                        {"role": "system", "content": "Siz tajribali tahlilchi va AI yordamchisiz."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=700,
                    temperature=0.3,
                )
                dossier_text = res.choices[0].message.content.strip()
            elif ai_service._gemini_client:
                g_res = ai_service._gemini_client.models.generate_content(
                    model=config.gemini_model,
                    contents=prompt
                )
                dossier_text = (g_res.text or "").strip()
        except Exception as ai_err:
            logger.warning("Admin dosyesini AI orqali sintez qilishda xatolik: %s", ai_err)
            dossier_text = (
                "CoddyCamp Sergeli filiali ma'muriyati. "
                "Tahlil qilingan xabarlar soni: " + str(len(raw_messages)) + ". "
                "Muloqot mavzulari: o'quvchilar davomati, dars jadvallari, markaz yangiliklari. "
                "Uslub: rasmiy va hurmatli hamkasblarcha."
            )

        if not dossier_text:
            dossier_text = "CoddyCamp Sergeli ma'muriyati bilan muloqot dosyesi."

        memory_service.set_setting("admin_dossier_coddycamp_sergeli", dossier_text)
        logger.info("✅ CoddyCamp ma'muriyat dosyesi muvaffaqiyatli saqlandi (%d ta xabar tahlil qilindi).", len(raw_messages))

        # Vazifalar guruhiga hisobot yuborish
        try:
            from handlers.auto_reply import dispatch_vazifalar_alert
            alert = (
                "🏛 **CODDYCAMP MA'MURIYAT CHATI (@coddycamp_sergeli) TAHLIL QILINDI:**\n\n"
                f"📊 **Tahlil qilingan xabarlar:** {len(raw_messages)} ta\n\n"
                f"📋 **Kognitiv Dosye:**\n{dossier_text}\n\n"
                "ℹ️ *Agent endilikda ushbu tajriba asosida ma'muriyatga professional munosabatda bo'ladi va o'quvchidek muomala qilmaydi. "
                "Barcha yangi xabarlar va qarorlar ushbu Vazifalar guruhida sizga yetkaziladi.*"
            )
            await dispatch_vazifalar_alert(cl, alert)
        except Exception as esc_e:
            logger.warning("Vazifalar guruhiga admin tahlil hisobotini yuborishda ogohlantirish: %s", esc_e)

        return {"ok": True, "dossier": dossier_text, "msg_count": len(raw_messages)}

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
            "chat_stats": self.get_chat_stats(),
            "auto_recheck_enabled": self.is_auto_recheck_enabled(),
            "auto_recheck_days": self.get_auto_recheck_days(),
        }


# Global singleton
profile_intelligence_service = ProfileIntelligenceService()
