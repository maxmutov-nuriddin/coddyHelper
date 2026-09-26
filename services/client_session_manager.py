"""
Har bir mijoz (obunachi) uchun alohida Telethon sessiya boshqaruvi — "har kimning o'z agenti".

Arxitektura:
  • Har bir mijoz O'Z Telegram akkaunti (HSS / StringSession) orqali ishlaydi.
  • Har bir mijozning handlerlari tenant_scope(owner_id) ichida ishlaydi — barcha o'qish/yozishlar
    faqat uning shaxsiy bazasiga (tenants/tenant_<id>.db) tushadi, boshqalar bilan aralashmaydi.
  • Sessiyalarni bir vaqtda faqat bitta server yuritadi (services/instance_lease.py) — aks holda Telegram
    AUTH_KEY_DUPLICATED bilan sessiyani bekor qilib, mijozni akkauntidan chiqarib yuboradi.

Xavfsizlik modeli:
  • Akkaunt EGASI agentni to'liq boshqaradi: o'z "Saqlangan xabarlar"iga (yoki shaxsiy akkauntidan agent
    akkauntiga) `ai <buyruq>` yozadi -> ReAct agent Telegramni boshqaradi (xabar yuborish, qidirish, ...).
  • BEGONALAR agentga buyruq bera olmaydi: ular faqat biznes personasi doirasida AI javob oladi
    (prompt-injection filtri, rate-limit, vositalarsiz).
  • Egasi biror chatga o'zi yozsa, AI shu chatda vaqtincha jim turadi (inson ustuvor).
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession

from config import config
from services.tenant_context import tenant_scope
from services.event_dedup import is_duplicate_event

logger = logging.getLogger(__name__)

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
TELEGRAM_SERVICE_ID = 777000  # Telegram xizmat xabarlari (login kodlari!) — hech qachon ishlanmaydi

# Sessiyani butunlay yaroqsiz qiladigan xatolar (qayta ulanishga urinish befoyda — yangi HSS kerak)
FATAL_AUTH_ERRORS = tuple(
    cls for cls in (
        getattr(errors, "AuthKeyDuplicatedError", None),
        getattr(errors, "AuthKeyUnregisteredError", None),
        getattr(errors, "AuthKeyInvalidError", None),
        getattr(errors, "SessionRevokedError", None),
        getattr(errors, "SessionExpiredError", None),
        getattr(errors, "UserDeactivatedError", None),
        getattr(errors, "UserDeactivatedBanError", None),
    ) if cls is not None
)

OWNER_COMMAND_PREFIXES = ("ai ", ".ai ", "/ai ", "agent ", ".agent ")

DEFAULT_DEBOUNCE_SECONDS = 4
DEFAULT_OWNER_PAUSE_SECONDS = 600
# Render free (512 MB) uchun himoya: har bir Telethon client ~20-40 MB. Kerak bo'lsa env orqali oshiring.
MAX_CLIENT_SESSIONS = int(os.getenv("MAX_CLIENT_SESSIONS", "12") or 12)
ESCALATION_COOLDOWN_SECONDS = 600

# AI aniq javob bera olmaganini bildiruvchi iboralar -> egasiga xabar beriladi
UNSURE_ANSWER_RE = re.compile(
    r"(aniqlab|aniqlashtirib|so'rab|surab)\s*(,\s*)?(sizga\s+)?(xabar\s+beraman|javob\s+beraman|aytaman)"
    r"|уточн\w*\s+и\s+(сообщ|напиш|отвеч)\w*"
    r"|i\s*('ll|\s+will)\s+(check|find\s+out)\s+and",
    re.IGNORECASE,
)


def _now_str() -> str:
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _session_fingerprint(session_string: str) -> str:
    return hashlib.sha256((session_string or "").encode("utf-8")).hexdigest()[:16]


def _extract_owner_command(text: str) -> str | None:
    low = (text or "").strip().lower()
    for p in OWNER_COMMAND_PREFIXES:
        if low.startswith(p):
            return text.strip()[len(p):].strip() or None
    return None


# Guruhni "boshqaruv guruhi" sifatida biriktirish uchun tan olinadigan iboralar
# ("ai " prefiksidan keyin). Aynan shu guruhda, egasi o'zi yozganda ishlaydi — shuning
# uchun avtomatik (bot qo'shilganda) bog'lashdan farqli o'laroq 100% xavfsiz: mijozning
# shaxsiy akkaunti (agent) a'zo bo'lgan istalgan tasodifiy guruh o'zi ulanib qolmaydi.
_LINK_GROUP_PHRASES = (
    "ulash", "guruhni ulash", "shu guruhni ulash", "bu guruhni ulash",
    "guruh ulash", "boshqaruv guruhi qil", "boshqaruv guruhiga qil",
    "biriktir", "guruhni biriktir", "link this group", "link group",
)


def _is_link_group_command(owner_command: str | None) -> bool:
    """`ai <buyruq>`dan ajratilgan matn guruhni ulash so'rovi ekanligini tekshiradi."""
    if not owner_command:
        return False
    c = owner_command.strip().lower().rstrip("?!. ")
    return c in _LINK_GROUP_PHRASES


# Guruh birinchi marta ulanganda agent so'raydigan tanishuv savollari (ketma-ket, bittadan).
# Har biri (kalit, savol matni) — javoblar shu kalitlar bilan saqlanadi va oxirida
# AI orqali bitta tartibli "biznes qo'llanmasi"ga (system_prompt) aylantiriladi.
ONBOARDING_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("business_name", "1️⃣ Birinchi savol: biznesingizning nomi nima?"),
    ("profession", "2️⃣ Qaysi sohada faoliyat yuritasiz? (masalan: mebel savdosi, go'zallik saloni, IT xizmatlari)"),
    ("products", "3️⃣ Qanday mahsulot yoki xizmatlar taqdim etasiz? Asosiylarini va narxlarini yozing."),
    ("hours_location", "4️⃣ Ish vaqtingiz va manzilingiz (yoki yetkazib berish hududi) qanday?"),
    ("faq", "5️⃣ Mijozlar sizdan ko'pincha nimalarni so'rashadi? 2-3 ta misol yozing (masalan: yetkazib berish bepulmi, kafolat bormi)."),
    ("tone", "6️⃣ Mijozlar bilan qanday ohangda gaplashishimni xohlaysiz — rasmiy, samimiy yoki qisqa-lo'nda?"),
    ("extra", "7️⃣ (Ixtiyoriy, oxirgi savol) Yana muhim qoida yoki ma'lumot bo'lsa yozing (chegirma, kafolat, to'lov usuli va h.k.). Bo'lmasa \"yo'q\" deb yozing."),
)
_ONBOARDING_SKIP_WORDS = {"yo'q", "yoq", "yoʻq", "skip", "-", "yo'q.", "yoq."}
_ONBOARDING_SETTING_KEY = "onboarding_state"


def _is_same_group(chat_id, group_id) -> bool:
    """
    Ikkita guruh ID sini solishtiradi ("-100xxxxxxxxxx" supergroup prefiksidan qat'i nazar).
    `link_user_group` va Telethon'ning turli joylarda ID ni har xil ko'rinishda
    (prefiksli/prefiksiz) saqlashi mumkinligiga qarshi himoya.
    """
    if not chat_id or not group_id:
        return False
    a, b = str(chat_id).strip(), str(group_id).strip()
    if a == b:
        return True
    return a.replace("-100", "-", 1) == b.replace("-100", "-", 1)


class ClientSessionManager:
    """
    - start_session(user_id, session_string) -> client yaratib, handlerlarni ro'yxatga oladi
    - stop_session(user_id) -> clientni to'xtatadi
    - start_all_saved_sessions() -> lease olingach barcha faol mijozlarni ishga tushiradi
    """

    def __init__(self):
        self._clients: dict[int, TelegramClient] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._me: dict[int, dict] = {}                     # {owner_id: {"id", "username", "name"}}
        self._stopping: set[int] = set()                   # qo'lda to'xtatilayotganlar (reconnect qilinmaydi)
        self._reconnect_attempts: dict[int, int] = {}
        self._activity: dict[int, deque] = {}
        # Debounce (bir nechta ketma-ket xabarni birlashtirish)
        self._pending: dict[tuple[int, int], asyncio.Task] = {}
        self._buffers: dict[tuple[int, int], list[str]] = {}
        # Egasi aralashgan chatlar: {(owner_id, chat_id): pause_until_ts}
        self._owner_pause_until: dict[tuple[int, int], float] = {}
        # Agent o'zi yuborayotgan chatlar (outgoing hodisasini egasining xabari deb o'ylamaslik uchun)
        self._agent_sending: dict[tuple[int, int], int] = {}
        self._agent_sent_ids: dict[int, deque] = {}
        self._voice_chats: set[tuple[int, int]] = set()      # oxirgi xabari ovozli bo'lgan chatlar
        self._last_escalation: dict[tuple[int, int], float] = {}
        self._workers_started = False

    # ──────────────────────────────────────────────────────
    # HOLAT (Mini App uchun)
    # ──────────────────────────────────────────────────────
    def _log(self, user_id: int, text: str) -> None:
        buf = self._activity.setdefault(user_id, deque(maxlen=40))
        buf.append({"time": datetime.now(TASHKENT_TZ).strftime("%H:%M:%S"), "text": text[:300]})

    def get_activity(self, user_id: int) -> list[dict]:
        return list(reversed(self._activity.get(user_id, [])))

    def _save_status(self, user_id: int, state: str, error: str = "", fingerprint: str | None = None) -> None:
        from services.memory_service import memory_service
        prev = self.get_status(user_id)
        data = {
            "state": state,
            "error": error,
            "updated_at": _now_str(),
            "fingerprint": fingerprint if fingerprint is not None else prev.get("fingerprint", ""),
        }
        me = self._me.get(user_id)
        if me:
            data["account"] = me
        elif prev.get("account"):
            data["account"] = prev["account"]
        memory_service.set_setting(f"tenant_status_{user_id}", json.dumps(data, ensure_ascii=False))

    def get_status(self, user_id: int) -> dict:
        from services.memory_service import memory_service
        raw = memory_service.get_setting(f"tenant_status_{user_id}", "")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        data["running"] = self.is_active(user_id)
        if data["running"]:
            data["state"] = "running"
        return data

    def get_client(self, user_id: int) -> TelegramClient | None:
        return self._clients.get(user_id)

    def is_active(self, user_id: int) -> bool:
        client = self._clients.get(user_id)
        return client is not None and client.is_connected()

    def active_sessions(self) -> list[int]:
        return [uid for uid, c in self._clients.items() if c.is_connected()]

    # ──────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────
    async def start_session(self, user_id: int, session_string: str | None = None) -> bool:
        """
        Mijoz sessiyasini ishga tushiradi. Xato bo'lsa sababini get_status(user_id)["error"] da qoldiradi.
        """
        from services.instance_lease import instance_lease
        from services.memory_service import memory_service

        user_id = int(user_id)
        if session_string is None:
            sub = memory_service.get_subscription(user_id) or {}
            session_string = sub.get("session_string", "")
        session_string = (session_string or "").strip()
        if not session_string:
            self._save_status(user_id, "no_session", "HSS (StringSession) kodi kiritilmagan.")
            return False

        if user_id not in self._clients and len(self.active_sessions()) >= MAX_CLIENT_SESSIONS:
            self._save_status(
                user_id, "error",
                f"Server limiti: bir vaqtda {MAX_CLIENT_SESSIONS} ta agent. Administrator (@mentor_cc) bilan bog'laning.",
            )
            logger.warning("Mijoz sessiyalari limiti (%d) to'ldi, user_id=%s kutmoqda.", MAX_CLIENT_SESSIONS, user_id)
            return False

        if not instance_lease.is_holder:
            self._save_status(
                user_id, "waiting",
                "Sessiyalar hozir boshqa serverda ishlamoqda (dublikat ulanish akkauntni chiqarib yuboradi). "
                "Asosiy server avtomatik ishga tushiradi.",
            )
            return False

        await self.stop_session(user_id, mark_inactive=False)
        fingerprint = _session_fingerprint(session_string)
        self._save_status(user_id, "connecting", "", fingerprint=fingerprint)

        client = TelegramClient(
            session=StringSession(session_string),
            api_id=config.api_id,
            api_hash=config.api_hash,
            device_model="Agent Assistent",
            system_version="Executive AI Co-Pilot",
            app_version="coddyHelper Client 2.0",
            lang_code="uz",
            system_lang_code="uz",
            connection_retries=5,
            retry_delay=3,
            auto_reconnect=True,
        )

        try:
            await client.connect()
            # MUHIM: client.start() ishlatilmaydi — sessiya yaroqsiz bo'lsa u terminaldan telefon so'rab
            # (input()) butun serverni qotirib qo'yadi.
            if not await client.is_user_authorized():
                await client.disconnect()
                await self._mark_invalid(user_id, "Sessiya kodi yaroqsiz yoki Telegram tomonidan bekor qilingan. Qayta ulaning.")
                return False

            me = await client.get_me()
            self._me[user_id] = {
                "id": me.id,
                "username": me.username or "",
                "name": " ".join(x for x in (me.first_name, me.last_name) if x).strip(),
            }
            self._register_handlers(client, user_id)
            self._clients[user_id] = client
            self._reconnect_attempts[user_id] = 0
            memory_service.set_session_active(user_id, True)
            self._save_status(user_id, "running", "", fingerprint=fingerprint)
            self._log(user_id, f"✅ Agent ishga tushdi (@{me.username or me.id})")
            logger.info("✅ Mijoz agenti ishga tushdi: owner=%s, account=%s (@%s)", user_id, me.id, me.username)

            self._tasks[user_id] = asyncio.create_task(self._run_client(user_id, client))
            self._ensure_workers()
            return True

        except FATAL_AUTH_ERRORS as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            await self._mark_invalid(user_id, self._describe_auth_error(e))
            return False
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            logger.error("❌ Mijoz sessiyasini ishga tushirishda xatolik [user_id=%s]: %s", user_id, e)
            memory_service.set_session_active(user_id, False)
            self._save_status(user_id, "error", f"Ulanishda xatolik: {e}")
            return False

    async def stop_session(self, user_id: int, mark_inactive: bool = True) -> bool:
        """Mijoz sessiyasini to'xtatadi (qayta ulanmaydi)."""
        user_id = int(user_id)
        stopped = False
        self._stopping.add(user_id)
        try:
            task = self._tasks.pop(user_id, None)
            client = self._clients.pop(user_id, None)
            if client:
                try:
                    if client.is_connected():
                        await client.disconnect()
                except Exception as e:
                    logger.debug("Client disconnect xatolik [%s]: %s", user_id, e)
                stopped = True
            if task and not task.done():
                task.cancel()
                stopped = True
            for key in [k for k in self._pending if k[0] == user_id]:
                t = self._pending.pop(key, None)
                if t and not t.done():
                    t.cancel()
                self._buffers.pop(key, None)
        finally:
            self._stopping.discard(user_id)

        if stopped and mark_inactive:
            from services.memory_service import memory_service
            memory_service.set_session_active(user_id, False)
            self._save_status(user_id, "stopped", "")
            self._log(user_id, "🛑 Agent to'xtatildi")
            logger.info("🛑 Mijoz sessiyasi to'xtatildi: user_id=%s", user_id)
        return stopped

    async def start_all_saved_sessions(self) -> int:
        """Lease olingach: barcha faol (muddati o'tmagan) mijozlarning sessiyalarini ishga tushiradi."""
        from services.memory_service import memory_service
        subs = memory_service.get_all_subscriptions()
        started = 0
        for sub in subs:
            uid = sub.get("user_id")
            sess = sub.get("session_string", "")
            if not uid or not sess or not int(sub.get("active", 0)) or self._is_expired(sub):
                continue
            status = self.get_status(uid)
            # Yaroqsiz deb belgilangan va o'sha kod bilan qayta urinish befoyda (yangi kod kiritilishi kerak)
            if status.get("state") == "invalid" and status.get("fingerprint") == _session_fingerprint(sess):
                continue
            if status.get("state") == "stopped":
                continue  # egasi yoki admin qo'lda to'xtatgan
            if self.is_active(uid):
                continue
            logger.info("🔄 Mijoz agenti ishga tushirilmoqda: user_id=%s", uid)
            if await self.start_session(uid, sess):
                started += 1
            await asyncio.sleep(1.5)  # Telegram flood himoyasi
        logger.info("🚀 Jami %d ta mijoz agenti ishga tushdi", started)
        return started

    async def stop_all(self, mark_inactive: bool = False) -> None:
        """Barcha sessiyalarni to'xtatadi (shutdown / lease yo'qolganda). Holat 'stopped' deb yozilmaydi."""
        for uid in list(self._clients.keys()):
            await self.stop_session(uid, mark_inactive=mark_inactive)

    # ──────────────────────────────────────────────────────
    # INTERNAL: xatolar va qayta ulanish
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _describe_auth_error(e: Exception) -> str:
        name = type(e).__name__
        if "Duplicated" in name:
            return (
                "Telegram sessiyani bekor qildi: bir xil HSS kod bir vaqtda ikki joyda ishlatilgan (AUTH_KEY_DUPLICATED). "
                "Iltimos, qayta ulaning va bu kodni boshqa joyda ishlatmang."
            )
        if "Revoked" in name or "Unregistered" in name or "Expired" in name:
            return "Sessiya Telegram'dan chiqarilgan (Qurilmalar ro'yxatidan o'chirilgan yoki muddati tugagan). Qayta ulaning."
        if "Deactivated" in name:
            return "Telegram akkaunti o'chirilgan yoki bloklangan."
        return f"Sessiya yaroqsiz: {name}"

    async def _mark_invalid(self, user_id: int, reason: str) -> None:
        from services.memory_service import memory_service
        sub = memory_service.get_subscription(user_id) or {}
        memory_service.set_session_active(user_id, False)
        self._save_status(user_id, "invalid", reason, fingerprint=_session_fingerprint(sub.get("session_string", "")))
        self._log(user_id, f"⛔ {reason}")
        logger.warning("⛔ Mijoz sessiyasi yaroqsiz [user_id=%s]: %s", user_id, reason)
        try:
            from services.notify import notify_user
            await notify_user(
                user_id,
                "⚠️ <b>AI agentingiz to'xtadi</b>\n\n"
                f"{reason}\n\n"
                "Mini App → <b>🤖 Mening Agentim</b> bo'limidan qayta ulanishingiz mumkin.",
            )
        except Exception:
            pass

    async def _run_client(self, user_id: int, client: TelegramClient) -> None:
        """Clientni disconnect bo'lgunicha ushlab turadi; kutilmagan uzilishda qayta ulanadi."""
        fatal = False
        try:
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            return
        except FATAL_AUTH_ERRORS as e:
            fatal = True
            await self._mark_invalid(user_id, self._describe_auth_error(e))
        except Exception as e:
            logger.warning("Mijoz sessiyasi uzildi [user_id=%s]: %s", user_id, e)
        finally:
            if self._clients.get(user_id) is client:
                self._clients.pop(user_id, None)

        if fatal or user_id in self._stopping:
            return
        await self._schedule_reconnect(user_id)

    async def _schedule_reconnect(self, user_id: int) -> None:
        from services.instance_lease import instance_lease
        from services.memory_service import memory_service
        attempt = self._reconnect_attempts.get(user_id, 0) + 1
        self._reconnect_attempts[user_id] = attempt
        if attempt > 6:
            self._save_status(user_id, "error", "Bir necha bor qayta ulanib bo'lmadi. Mini App'dan qayta ishga tushiring.")
            memory_service.set_session_active(user_id, False)
            return
        delay = min(300, 5 * (2 ** (attempt - 1)))
        self._save_status(user_id, "reconnecting", f"Aloqa uzildi, {delay}s dan keyin qayta ulanadi (urinish {attempt}).")
        await asyncio.sleep(delay)
        if not instance_lease.is_holder or user_id in self._stopping or self.is_active(user_id):
            return
        sub = memory_service.get_subscription(user_id) or {}
        if not sub.get("active") or self._is_expired(sub):
            return
        await self.start_session(user_id, sub.get("session_string", ""))

    @staticmethod
    def _is_expired(sub: dict) -> bool:
        if sub.get("is_expired"):
            return True
        exp = str(sub.get("expires_at") or "")
        if not exp:
            return False
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=TASHKENT_TZ)
            return exp_dt < datetime.now(TASHKENT_TZ)
        except Exception:
            return False

    # ──────────────────────────────────────────────────────
    # INTERNAL: handlerlar
    # ──────────────────────────────────────────────────────
    def _register_handlers(self, client: TelegramClient, user_id: int) -> None:
        @client.on(events.NewMessage(incoming=True))
        async def _on_incoming(event):
            with tenant_scope(user_id):
                try:
                    await self._handle_incoming(user_id, client, event)
                except FATAL_AUTH_ERRORS:
                    raise
                except Exception as e:
                    logger.error("Mijoz handler xatolik [user_id=%s]: %s", user_id, e, exc_info=True)

        @client.on(events.NewMessage(outgoing=True))
        async def _on_outgoing(event):
            with tenant_scope(user_id):
                try:
                    await self._handle_outgoing(user_id, client, event)
                except Exception as e:
                    logger.error("Mijoz outgoing handler xatolik [user_id=%s]: %s", user_id, e, exc_info=True)

    def _tenant_setting(self, key: str, default: str) -> str:
        from services.memory_service import memory_service
        return (memory_service.get_setting(key, default) or default).strip().lower()

    async def _handle_outgoing(self, user_id: int, client: TelegramClient, event) -> None:
        """Akkaunt egasining o'z xabarlari: Saved Messages'dagi `ai ...` buyruqlari yoki chatga aralashuv."""
        chat_id = event.chat_id
        me_id = self._me.get(user_id, {}).get("id")
        key = (user_id, chat_id)

        # Agentning o'zi yuborgan xabar — e'tiborsiz
        if self._agent_sending.get(key) or event.id in self._agent_sent_ids.get(user_id, ()):
            return

        # 🛡 Telethon qayta ulanganda ba'zan bir xil xabarni ikkinchi marta yuborishi mumkin —
        # bunday holda egasining buyrug'i (masalan xabar yuborish) ikki marta bajarilib qolmasin.
        if is_duplicate_event("client.handle_outgoing", chat_id, event.id, scope=user_id):
            return

        text = (event.raw_text or "").strip()
        if chat_id == me_id:
            command = _extract_owner_command(text)
            if command:
                self._log(user_id, f"👤 Egasining buyrug'i: {command[:80]}")
                result = await self.run_owner_command(user_id, command)
                await self._send(user_id, client, chat_id, f"🤖 {result}")
            return

        # Egasining O'Z boshqaruv guruhi (Mini App'da biriktirgan): agent bitta akkauntda ishlasa,
        # egasining bu guruhga yozgan xabari OUTGOING hodisa sifatida keladi — shuning uchun
        # 'ai ...' buyrug'i bu yerda ham (Saved Messages'dagi kabi) tanilishi kerak.
        try:
            from services.memory_service import memory_service
            sub = memory_service.get_subscription(user_id)
        except Exception:
            sub = None

        # Guruhni "boshqaruv guruhi" sifatida ulash: egasi o'zi (bu guruhda, agent akkauntidan)
        # `ai ulash` deb yozsa, shu guruh darhol biriktiriladi. Bu — bot guruhga qo'shilganda
        # avtomatik bog'lashdan farqli, 100% ANIQ va XAVFSIZ usul: mijozning shaxsiy akkaunti
        # (agent) a'zo bo'lgan boshqa tasodifiy guruhlar hech qachon o'zi ulanib qolmaydi.
        command_for_link = _extract_owner_command(text)
        if sub and _is_link_group_command(command_for_link):
            if _is_same_group(chat_id, sub.get("group_id")):
                # 1 marta ulash yetarli: qayta "ulash" deyilsa, qayta ulamaymiz va
                # tanishuv savolnomasini boshidan boshlamaymiz — shunchaki xabar beramiz.
                await self._send(user_id, client, chat_id, "ℹ️ Bu guruh allaqachon sizning **boshqaruv guruhingiz** sifatida ulangan.")
                return
            memory_service.link_user_group(user_id, chat_id)
            self._log(user_id, f"📌 Boshqaruv guruhi biriktirildi: {chat_id}")
            await self._send(
                user_id, client, chat_id,
                "✅ Ushbu guruh sizning **boshqaruv guruhingiz** sifatida biriktirildi!\n"
                "Endi shu yerga oddiy yozgan har bir xabaringizga to'g'ridan-to'g'ri javob beraman "
                "(botni chaqirish yoki maxsus so'z aytish shart emas) va topshiriqlarni bajaraman.",
            )
            await self._start_onboarding(user_id, client, chat_id)
            return

        if sub and _is_same_group(chat_id, sub.get("group_id")):
            # Guruh birinchi ulanganda boshlangan tanishuv savolnomasi hali tugamagan bo'lsa,
            # bu xabar navbatdagi javob sifatida qabul qilinadi (oddiy AI suhbatiga aylanmaydi).
            onboarding_state = self._get_onboarding_state()
            if onboarding_state and _is_same_group(chat_id, onboarding_state.get("chat_id")):
                await self._handle_onboarding_answer(user_id, client, chat_id, text, onboarding_state)
                return

            # Boshqaruv guruhi = mentorning Vazifalar guruhi bilan bir xil tajriba: egasi
            # "ai " prefiksisiz, oddiy tabiiy tilda yozsa ham (masalan "Salom", "Alisherga
            # xabar yubor") to'liq AI Co-Pilot javob berishi kerak — prefiks talab qilinmaydi.
            command = command_for_link or text
            if command:
                self._log(user_id, f"👤 Egasi (boshqaruv guruhidan): {command[:80]}")
                result = await self.run_owner_command(user_id, command)
                await self._send(user_id, client, chat_id, result)
            return

        # Egasi o'zi chatga yozdi -> AI shu chatda jim turadi (inson ustuvor)
        pause = int(self._tenant_setting("owner_pause_seconds", str(DEFAULT_OWNER_PAUSE_SECONDS)) or DEFAULT_OWNER_PAUSE_SECONDS)
        self._owner_pause_until[key] = time.time() + max(0, pause)
        pending = self._pending.pop(key, None)
        if pending and not pending.done():
            pending.cancel()
        self._buffers.pop(key, None)

    async def _handle_incoming(self, user_id: int, client: TelegramClient, event) -> None:
        from services.memory_service import memory_service

        if is_duplicate_event("client.handle_incoming", event.chat_id, event.id, scope=user_id):
            return

        sub = memory_service.get_subscription(user_id)
        if not sub or not sub.get("active") or self._is_expired(sub):
            return

        # Kanallar (broadcast) — javob berilmaydi
        if event.is_channel and not event.is_group:
            return

        sender = await event.get_sender()
        if not sender:
            return
        sender_id = sender.id
        me_id = self._me.get(user_id, {}).get("id")
        if sender_id in (me_id, TELEGRAM_SERVICE_ID) or getattr(sender, "bot", False):
            return

        text = event.raw_text or ""
        chat_id = event.chat_id

        # Egasi o'zining shaxsiy akkauntidan agent akkauntiga buyruq yuborsa (agent alohida akkauntda bo'lsa)
        if event.is_private and sender_id == user_id and sender_id != me_id:
            command = _extract_owner_command(text)
            if command:
                self._log(user_id, f"👤 Egasining buyrug'i (shaxsiy akkauntdan): {command[:80]}")
                result = await self.run_owner_command(user_id, command)
                await self._send(user_id, client, chat_id, f"🤖 {result}", reply_to=event.id)
                return

        if memory_service.is_user_ignored(sender_id):
            return

        # Guruhni "boshqaruv guruhi" sifatida ulash (agent alohida akkauntda ishlagan holat):
        # egasi (haqiqiy o'zi, boshqa hech kim emas) shu guruhda `ai ulash` deb yozsa, biriktiriladi.
        if not event.is_private and sender_id == user_id:
            link_command = _extract_owner_command(text)
            if _is_link_group_command(link_command):
                if _is_same_group(chat_id, sub.get("group_id")):
                    # 1 marta ulash yetarli: qayta "ulash" deyilsa, qayta ulamaymiz va
                    # tanishuv savolnomasini boshidan boshlamaymiz — shunchaki xabar beramiz.
                    await self._send(user_id, client, chat_id, "ℹ️ Bu guruh allaqachon sizning **boshqaruv guruhingiz** sifatida ulangan.", reply_to=event.id)
                    return
                memory_service.link_user_group(user_id, chat_id)
                self._log(user_id, f"📌 Boshqaruv guruhi biriktirildi: {chat_id}")
                await self._send(
                    user_id, client, chat_id,
                    "✅ Ushbu guruh sizning **boshqaruv guruhingiz** sifatida biriktirildi!\n"
                    "Endi shu yerga oddiy yozgan har bir xabaringizga to'g'ridan-to'g'ri javob beraman "
                    "(botni chaqirish yoki maxsus so'z aytish shart emas) va topshiriqlarni bajaraman.",
                    reply_to=event.id,
                )
                await self._start_onboarding(user_id, client, chat_id)
                return

        # Mijozning O'Z (Mini App'da biriktirgan) boshqaruv guruhi — mentorning Vazifalar guruhi
        # bilan bir xil mantiqda ishlaydi: @mention shart emas, egasi shu yerdan `ai ...` buyrug'ini
        # ham to'g'ridan-to'g'ri berishi mumkin. Aks holda bu guruh ham oddiy mijozlar guruhi kabi
        # faqat @mention qilinganda javob berardi va egasi "yozsam javob bermayapti" deb qolardi.
        is_owner_group = not event.is_private and _is_same_group(chat_id, sub.get("group_id"))
        if is_owner_group and sender_id == user_id:
            # Guruh birinchi ulanganda boshlangan tanishuv savolnomasi hali tugamagan bo'lsa,
            # bu xabar navbatdagi javob sifatida qabul qilinadi.
            onboarding_state = self._get_onboarding_state()
            if onboarding_state and _is_same_group(chat_id, onboarding_state.get("chat_id")):
                await self._handle_onboarding_answer(user_id, client, chat_id, text, onboarding_state, reply_to=event.id)
                return

            # Boshqaruv guruhi = Vazifalar guruhi tajribasi: "ai " prefiksisiz oddiy
            # xabar ham to'liq AI Co-Pilot javobini olishi kerak.
            command = _extract_owner_command(text) or text
            if command:
                self._log(user_id, f"👤 Egasi (boshqaruv guruhidan): {command[:80]}")
                result = await self.run_owner_command(user_id, command)
                await self._send(user_id, client, chat_id, result, reply_to=event.id)
                return

        if event.is_private:
            if self._tenant_setting("auto_reply_enabled", "true") != "true":
                return
        elif not is_owner_group:
            group_mode = self._tenant_setting("group_reply_mode", "mention")
            if group_mode == "off":
                return
            if group_mode != "all" and not event.mentioned:
                return

        key = (user_id, chat_id)
        if self._owner_pause_until.get(key, 0) > time.time():
            return

        # Ovozli xabar -> matn
        if not text.strip():
            msg = event.message
            has_voice = bool(
                getattr(msg, "voice", False)
                or (msg.document and msg.file and (getattr(msg.file, "mime_type", "") or "").startswith("audio/"))
            )
            if has_voice:
                try:
                    from services.ai_service import ai_service
                    audio_bytes = await msg.download_media(bytes)
                    if audio_bytes:
                        transcribed = await ai_service.transcribe_audio(audio_bytes)
                        if transcribed:
                            text = f"[Ovozli xabar]: {transcribed.strip()}"
                            self._voice_chats.add((user_id, chat_id))
                except Exception as v_err:
                    logger.debug("Mijoz ovozli xabarini STT qilishda xatolik: %s", v_err)

        image_bytes = None
        if event.message.photo:
            try:
                image_bytes = await event.message.download_media(bytes)
                if image_bytes and len(image_bytes) > 6 * 1024 * 1024:
                    image_bytes = None
            except Exception:
                image_bytes = None

        if not text.strip() and not image_bytes:
            return

        self._buffers.setdefault(key, []).append(text.strip())
        prev = self._pending.pop(key, None)
        if prev and not prev.done():
            prev.cancel()
        try:
            delay = float(self._tenant_setting("debounce_seconds", str(DEFAULT_DEBOUNCE_SECONDS)))
        except ValueError:
            delay = DEFAULT_DEBOUNCE_SECONDS
        # Task tenant kontekstini meros qilib oladi (ContextVar)
        self._pending[key] = asyncio.create_task(
            self._reply_after_quiet(user_id, client, event, sender_id, image_bytes, max(0.0, min(delay, 30.0)))
        )

    async def _reply_after_quiet(self, user_id, client, event, sender_id, image_bytes, delay) -> None:
        key = (user_id, event.chat_id)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        parts = self._buffers.pop(key, [])
        self._pending.pop(key, None)
        combined = "\n".join(p for p in parts if p).strip()
        if not combined and not image_bytes:
            return

        # CRM: kim yozgani egasining shaxsiy bazasiga yoziladi (Mini App → Mening Agentim → Kim yozdi)
        try:
            from services.memory_service import memory_service
            sender = await event.get_sender()
            s_name = " ".join(x for x in (getattr(sender, "first_name", ""), getattr(sender, "last_name", "")) if x).strip()
            memory_service.record_lead(sender_id, s_name, getattr(sender, "username", "") or "", combined or "[rasm]")
        except Exception as crm_err:
            logger.debug("Lead yozishda ogohlantirish: %s", crm_err)
        if self._owner_pause_until.get(key, 0) > time.time():
            return

        from services.ai_service import ai_service
        try:
            async with client.action(event.chat_id, "typing"):
                answer = await ai_service.generate_reply(
                    chat_id=event.chat_id,
                    user_message=combined,
                    user_id=sender_id,
                    image_bytes=image_bytes,
                    is_admin_mode=False,
                )
        except Exception as e:
            logger.error("Mijoz agenti javob yaratishda xatolik [user_id=%s]: %s", user_id, e)
            return

        answer_text = str(answer or "").strip()
        if not answer_text:
            return
        # Kutish paytida egasi aralashgan bo'lsa — yubormaymiz
        if self._owner_pause_until.get(key, 0) > time.time():
            return
        await self._send(user_id, client, event.chat_id, answer_text, reply_to=None if event.is_private else event.id)
        self._log(user_id, f"💬 Javob berildi (chat {event.chat_id}): {combined[:60]}")

        # Ovozli xabarga ovozli javob (egasi sozlamasi bo'yicha)
        if key in self._voice_chats:
            self._voice_chats.discard(key)
            if self._tenant_setting("voice_reply_enabled", "true") == "true":
                await self._send_voice(user_id, client, event.chat_id, answer_text)

        # AI aniq javob bera olmadi -> egasiga xabar (u o'zi aralashishi uchun)
        if UNSURE_ANSWER_RE.search(answer_text) and self._tenant_setting("escalate_to_owner", "true") == "true":
            await self._escalate_to_owner(user_id, event, sender_id, combined)

    async def _send_voice(self, user_id: int, client: TelegramClient, chat_id: int, text: str) -> None:
        try:
            from services.tts_service import generate_voice_message
            path = await generate_voice_message(text, is_mentor=False)
            if not path:
                return
            key = (user_id, chat_id)
            self._agent_sending[key] = self._agent_sending.get(key, 0) + 1
            try:
                msg = await client.send_file(chat_id, str(path), voice_note=True)
                if msg:
                    self._agent_sent_ids.setdefault(user_id, deque(maxlen=200)).append(msg.id)
            finally:
                await asyncio.sleep(0.3)
                self._agent_sending[key] = max(0, self._agent_sending.get(key, 1) - 1)
                if not self._agent_sending[key]:
                    self._agent_sending.pop(key, None)
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Mijoz agenti ovozli javob yubora olmadi [%s]: %s", user_id, e)

    async def _escalate_to_owner(self, user_id: int, event, sender_id: int, question: str) -> None:
        key = (user_id, event.chat_id)
        now = time.time()
        if now - self._last_escalation.get(key, 0) < ESCALATION_COOLDOWN_SECONDS:
            return
        self._last_escalation[key] = now
        try:
            sender = await event.get_sender()
            name = " ".join(x for x in (getattr(sender, "first_name", ""), getattr(sender, "last_name", "")) if x).strip() or str(sender_id)
            username = getattr(sender, "username", "") or ""
        except Exception:
            name, username = str(sender_id), ""
        link = f"https://t.me/{username}" if username else f"tg://user?id={sender_id}"
        from html import escape
        from services.notify import notify_user
        await notify_user(
            user_id,
            "🙋 <b>Mijoz savoliga aniq javob kerak</b>\n\n"
            f"👤 <a href=\"{link}\">{escape(name)}</a>\n"
            f"💬 {escape(question[:600])}\n\n"
            "AI unga aniqlab javob berishini aytdi. Chatga o'zingiz yozsangiz, AI shu suhbatda jim turadi.\n"
            "💡 Javobni <b>Bilimlar</b> bo'limiga qo'shsangiz, keyingi safar AI o'zi javob beradi.",
        )
        self._log(user_id, f"🙋 Egasiga yuborildi: {question[:60]}")

    async def _send(self, user_id: int, client: TelegramClient, chat_id: int, text: str, reply_to: int | None = None) -> None:
        key = (user_id, chat_id)
        self._agent_sending[key] = self._agent_sending.get(key, 0) + 1
        try:
            msg = await client.send_message(chat_id, text[:4096], reply_to=reply_to)
            if msg:
                self._agent_sent_ids.setdefault(user_id, deque(maxlen=200)).append(msg.id)
        finally:
            await asyncio.sleep(0.3)
            left = self._agent_sending.get(key, 1) - 1
            if left <= 0:
                self._agent_sending.pop(key, None)
            else:
                self._agent_sending[key] = left

    # ──────────────────────────────────────────────────────
    # Boshqaruv guruhi birinchi ulanganda: tanishuv savolnomasi
    # ──────────────────────────────────────────────────────
    def _get_onboarding_state(self) -> dict | None:
        """Joriy tenant kontekstidagi tugallanmagan tanishuv holatini o'qiydi."""
        from services.memory_service import memory_service
        raw = memory_service.get_setting(_ONBOARDING_SETTING_KEY, "")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _clear_onboarding_state(self) -> None:
        from services.memory_service import memory_service
        memory_service.set_setting(_ONBOARDING_SETTING_KEY, "")

    async def _start_onboarding(self, user_id: int, client: TelegramClient, chat_id: int) -> None:
        """Guruh birinchi marta ulanganda tanishuv savolnomasini boshlaydi (1-savol)."""
        from services.memory_service import memory_service
        state = {"chat_id": chat_id, "step": 0, "answers": {}}
        memory_service.set_setting(_ONBOARDING_SETTING_KEY, json.dumps(state, ensure_ascii=False))
        _, first_q = ONBOARDING_QUESTIONS[0]
        await self._send(
            user_id, client, chat_id,
            "🧠 Sizni va biznesingizni tezroq bilib olishim uchun bir nechta qisqa savol beraman "
            f"(har birini alohida xabar qilib yuboring — jami {len(ONBOARDING_QUESTIONS)} ta savol):\n\n{first_q}",
        )

    async def _handle_onboarding_answer(
        self, user_id: int, client: TelegramClient, chat_id: int, text: str,
        state: dict, reply_to: int | None = None,
    ) -> None:
        """Tanishuv savolnomasidagi navbatdagi javobni qabul qiladi va keyingi savolga o'tadi."""
        from services.memory_service import memory_service
        step = int(state.get("step", 0))
        if step >= len(ONBOARDING_QUESTIONS):
            self._clear_onboarding_state()
            return

        key, _ = ONBOARDING_QUESTIONS[step]
        answer = (text or "").strip()
        is_last_optional = key == "extra"
        if not answer or (not is_last_optional and answer.lower().strip("., !") in _ONBOARDING_SKIP_WORDS):
            await self._send(
                user_id, client, chat_id,
                "🙏 Iltimos, shu savolga qisqacha bo'lsa ham javob bering — bu mijozlaringizga to'g'ri yordam berishim uchun kerak.",
                reply_to=reply_to,
            )
            return

        answers = state.setdefault("answers", {})
        if not (is_last_optional and answer.lower().strip("., !") in _ONBOARDING_SKIP_WORDS):
            answers[key] = answer
        step += 1
        state["step"] = step

        if step < len(ONBOARDING_QUESTIONS):
            memory_service.set_setting(_ONBOARDING_SETTING_KEY, json.dumps(state, ensure_ascii=False))
            _, next_q = ONBOARDING_QUESTIONS[step]
            await self._send(user_id, client, chat_id, next_q, reply_to=reply_to)
            return

        self._clear_onboarding_state()
        await self._send(user_id, client, chat_id, "⏳ Rahmat! Ma'lumotlarni tahlil qilib, xotiramga saqlayapman...", reply_to=reply_to)
        await self._finish_onboarding(user_id, client, chat_id, answers)

    async def _finish_onboarding(self, user_id: int, client: TelegramClient, chat_id: int, answers: dict) -> None:
        """To'plangan javoblarni AI orqali tartibli 'biznes qo'llanmasi'ga aylantirib saqlaydi."""
        from services.memory_service import memory_service

        biz_name = (answers.get("business_name") or "").strip() or "Mening Boshqaruvim"
        profession = (answers.get("profession") or "").strip()
        labels = {
            "business_name": "Biznes nomi", "profession": "Sohasi", "products": "Mahsulot/xizmatlar va narxlar",
            "hours_location": "Ish vaqti va manzil", "faq": "Mijozlar ko'p so'raydigan savollar",
            "tone": "Xohlagan muloqot ohangi", "extra": "Qo'shimcha qoidalar",
        }
        raw_blob = "\n".join(f"- {labels.get(k, k)}: {v}" for k, v in answers.items() if v)

        system_prompt_text = raw_blob
        try:
            from services.ai_service import ai_service
            pool = ai_service._frontline_clients if ai_service._frontline_clients else ai_service._groq_clients
            if pool:
                res = await pool[0].chat.completions.create(
                    model=config.groq_model or "openai/gpt-oss-120b",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Siz tadbirkorning xom javoblarini AI yordamchi uchun aniq, tartibli "
                                "'BIZNES QOIDALARI VA MA'LUMOTLARI' qo'llanmasiga aylantirasiz. Imlo/uslub "
                                "xatolarini to'g'irlang, takrorlarni olib tashlang, punktma-punkt tartibga soling. "
                                "Hech qanday yangi ma'lumot to'qib chiqarmang — faqat berilganini tozalab, tartibga soling. "
                                "Tadbirkor qaysi tilda yozgan bo'lsa, xuddi o'sha tilda javob bering."
                            ),
                        },
                        {"role": "user", "content": raw_blob},
                    ],
                    temperature=0.2,
                    max_tokens=700,
                )
                cleaned = (res.choices[0].message.content or "").strip()
                if cleaned:
                    system_prompt_text = cleaned
        except Exception as e:
            logger.warning("Onboarding xulosasini AI bilan tozalashda ogohlantirish [user_id=%s]: %s", user_id, e)

        memory_service.upsert_subscription(
            user_id=user_id, business_name=biz_name, profession=profession,
            system_prompt=system_prompt_text, days=0, is_edit=True,
        )

        tone = (answers.get("tone") or "").lower()
        persona = "friendly"
        if any(w in tone for w in ("rasmiy", "professional", "formal")):
            persona = "assistant"
        elif any(w in tone for w in ("mutaxassis", "ekspert", "texnik")):
            persona = "tech_lead"
        memory_service.set_setting(f"ai_persona_{user_id}", persona)

        self._log(user_id, "🎓 Tanishuv savolnomasi yakunlandi, biznes ma'lumotlari saqlandi")
        await self._send(
            user_id, client, chat_id,
            "✅ **Tayyor!** Endi biznesingiz haqida bilaman va mijozlaringizga shu asosda javob beraman.\n\n"
            f"📋 **O'rgangan ma'lumotlarim:**\n{system_prompt_text[:900]}\n\n"
            "Istalgan payt Mini App'dagi **Bilimlar** bo'limi yoki shu guruhga oddiy yozib "
            "(masalan: \"yangi qoida: ...\") bu ma'lumotlarni to'ldirishingiz mumkin.",
        )

    # ──────────────────────────────────────────────────────
    # Egasining buyruqlari (ReAct agent — Telegramni to'liq boshqarish)
    # ──────────────────────────────────────────────────────
    async def run_owner_command(self, user_id: int, command: str) -> str:
        """
        Akkaunt egasining buyrug'ini uning O'Z clienti orqali bajaradi (xabar yuborish, qidirish, ...).
        Chaqiruvchi tenant_scope(user_id) ichida bo'lishi shart emas — bu yerda o'rnatiladi.
        """
        client = self.get_client(user_id)
        if not client:
            return "Agent hozir ulanmagan. Avval Mini App orqali Telegram akkauntingizni ulang."
        with tenant_scope(user_id):
            from services.agent_runner import run_autonomous_agent_loop, TENANT_REACT_PROMPT, TENANT_ALLOWED_TOOLS
            from services.memory_service import memory_service
            sub = memory_service.get_subscription(user_id) or {}
            owner = sub.get("full_name") or sub.get("business_name") or self._me.get(user_id, {}).get("name") or "akkaunt egasi"
            chats_context = ""
            try:
                from services.telegram_agent_service import list_recent_chats
                recent = await list_recent_chats(client, limit=12)
                if recent:
                    chats_context = "Faol chatlar: " + ", ".join(f"{c['name']} ({c['type']})" for c in recent)
            except Exception:
                pass
            try:
                result = await asyncio.wait_for(
                    run_autonomous_agent_loop(
                        client,
                        user_prompt=command,
                        chats_context=chats_context,
                        system_prompt=TENANT_REACT_PROMPT.format(owner=owner),
                        allowed_tools=TENANT_ALLOWED_TOOLS,
                    ),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                result = None
                logger.warning("Egasining buyrug'i vaqt limitidan oshdi [user_id=%s]", user_id)
            except Exception as e:
                logger.error("Egasining buyrug'ini bajarishda xatolik [user_id=%s]: %s", user_id, e)
                result = None
        return (result or "Buyruqni bajarib bo'lmadi. Iltimos, aniqroq yozing (masalan: 'ai Alisherga ertaga uchrashuv borligini yoz').").strip()

    # ──────────────────────────────────────────────────────
    # Fon xizmatlari: eslatmalar va obuna muddati
    # ──────────────────────────────────────────────────────
    def _ensure_workers(self) -> None:
        if self._workers_started:
            return
        self._workers_started = True
        asyncio.create_task(self._tenant_reminder_loop())
        asyncio.create_task(self._expiry_watch_loop())

    async def _tenant_reminder_loop(self) -> None:
        """Har bir mijozning o'z eslatmalarini tekshirib, faqat o'sha mijozga yetkazadi."""
        from services.instance_lease import instance_lease
        from services.memory_service import memory_service, TENANTS_DIR
        from services.reminder_service import send_due_reminder_notification
        while True:
            await asyncio.sleep(25)
            if not instance_lease.is_holder or not TENANTS_DIR.exists():
                continue
            now_str = _now_str()
            for f in TENANTS_DIR.glob("tenant_*.db"):
                try:
                    tid = int(f.stem.split("_", 1)[1])
                except (IndexError, ValueError):
                    continue
                try:
                    with tenant_scope(tid):
                        for rem in memory_service.get_due_reminders(now_str):
                            await send_due_reminder_notification(
                                rem_id=rem["id"],
                                chat_id=rem["chat_id"],
                                task_text=rem["text"],
                                remind_at=rem["remind_at"],
                                client=self.get_client(tid),
                            )
                except Exception as e:
                    logger.warning("Tenant %s eslatmalarini tekshirishda ogohlantirish: %s", tid, e)

    async def _expiry_watch_loop(self) -> None:
        """Muddati tugagan/bekor qilingan obunalar agentini to'xtatadi, tugashidan oldin ogohlantiradi."""
        from services.instance_lease import instance_lease
        from services.memory_service import memory_service
        from services.notify import notify_user
        while True:
            await asyncio.sleep(600)
            if not instance_lease.is_holder:
                continue
            for uid in list(self._clients.keys()):
                try:
                    sub = memory_service.get_subscription(uid) or {}
                    if not sub.get("active") or self._is_expired(sub):
                        await self.stop_session(uid, mark_inactive=True)
                        self._save_status(uid, "expired", "Obuna muddati tugagan yoki to'xtatilgan.")
                        await notify_user(uid, "⏳ <b>Obunangiz muddati tugadi</b> — AI agentingiz to'xtatildi.\nUzaytirish uchun @mentor_cc ga murojaat qiling.")
                        continue
                    exp = str(sub.get("expires_at") or "")
                    if exp:
                        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=TASHKENT_TZ)
                        days_left = (exp_dt - datetime.now(TASHKENT_TZ)).days
                        if days_left in (3, 1):
                            flag = f"expiry_notice_{exp_dt.date()}_{days_left}"
                            with tenant_scope(uid):
                                if memory_service.get_setting(flag) is None:
                                    memory_service.set_setting(flag, "1")
                                    await notify_user(uid, f"⏳ Obunangiz tugashiga <b>{days_left} kun</b> qoldi ({exp}).\nUzaytirish uchun @mentor_cc ga yozing.")
                except Exception as e:
                    logger.debug("Obuna muddatini tekshirishda ogohlantirish [%s]: %s", uid, e)


# Global instansiya
client_session_manager = ClientSessionManager()
