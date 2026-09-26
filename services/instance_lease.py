"""
Instance Lease — mijoz Telegram sessiyalarini bir vaqtning o'zida faqat BITTA server yuritishini kafolatlaydi.

Muammo: mijozning StringSession (HSS) kodi ikki joyda (masalan Render va mentor kompyuterida)
bir vaqtda ulansa, Telegram `AUTH_KEY_DUPLICATED` xatosini beradi va sessiyani butunlay bekor qiladi —
mijoz o'z akkauntidan "chiqarib yuboriladi". Bu lease MongoDB orqali serverlar o'rtasida kelishuvni ta'minlaydi.

CLIENT_SESSIONS_MODE muhit o'zgaruvchisi:
  auto  (standart) — MongoDB lease orqali avtomatik (bir vaqtda faqat bitta server)
  off              — bu serverda mijoz sessiyalari umuman ishga tushirilmaydi (lokal dev uchun tavsiya)
  force            — lease'siz majburan ishga tushirish (faqat bitta server ishlayotganiga ishonchingiz komil bo'lsa)
"""

import asyncio
import logging
import os
import socket
import uuid

logger = logging.getLogger(__name__)

LEASE_NAME = "client_sessions"
LEASE_TTL_SECONDS = 90
RENEW_INTERVAL_SECONDS = 30


class InstanceLease:
    def __init__(self):
        self.holder_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        from config import _clean_env_value
        self.mode = (_clean_env_value(os.getenv("CLIENT_SESSIONS_MODE", "auto")) or "auto").strip().lower()
        self.is_holder = False
        self._task: asyncio.Task | None = None
        self._on_acquired = None
        self._on_lost = None

    def status(self) -> dict:
        info = {"mode": self.mode, "holder_id": self.holder_id, "is_holder": self.is_holder}
        try:
            from services.mongo_memory_service import mongo_memory_service
            doc = mongo_memory_service.get_lease_holder(LEASE_NAME)
            if doc:
                info["current_holder"] = doc.get("holder")
        except Exception:
            pass
        return info

    def _try_acquire(self) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "force":
            return True
        from services.mongo_memory_service import mongo_memory_service
        if not mongo_memory_service.is_core_connected():
            # MongoDB yo'q — avvalgi (bitta server) xatti-harakati saqlanadi
            return True
        return mongo_memory_service.acquire_lease(LEASE_NAME, self.holder_id, LEASE_TTL_SECONDS)

    def start(self, on_acquired, on_lost) -> None:
        """Lease uchun fon siklini ishga tushiradi. on_acquired/on_lost — async callbacklar."""
        self._on_acquired = on_acquired
        self._on_lost = on_lost
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        if self.mode == "off":
            logger.info("🔒 CLIENT_SESSIONS_MODE=off — bu serverda mijoz sessiyalari ishga tushirilmaydi.")
            return
        logger.info("🔑 Instance lease sikli boshlandi (mode=%s, id=%s)", self.mode, self.holder_id)
        announced_wait = False
        while True:
            try:
                got = await asyncio.to_thread(self._try_acquire)
                if got and not self.is_holder:
                    self.is_holder = True
                    announced_wait = False
                    logger.info("✅ Mijoz sessiyalari lease'i olindi — sessiyalar shu serverda ishga tushiriladi.")
                    if self._on_acquired:
                        await self._on_acquired()
                elif not got and self.is_holder:
                    self.is_holder = False
                    logger.warning("⚠️ Lease boshqa serverga o'tdi — mijoz sessiyalari to'xtatilmoqda (dublikatning oldini olish).")
                    if self._on_lost:
                        await self._on_lost()
                elif not got and not announced_wait:
                    announced_wait = True
                    logger.info("⏳ Mijoz sessiyalari boshqa serverda ishlamoqda — bu server kutadi.")
            except Exception as e:
                logger.warning("Lease siklida ogohlantirish: %s", e)
            await asyncio.sleep(RENEW_INTERVAL_SECONDS)

    async def release(self) -> None:
        """Server to'xtashida lease'ni bo'shatadi (yangi server darhol egallashi uchun)."""
        if self._task and not self._task.done():
            self._task.cancel()
        if self.is_holder and self.mode == "auto":
            try:
                from services.mongo_memory_service import mongo_memory_service
                await asyncio.to_thread(mongo_memory_service.release_lease, LEASE_NAME, self.holder_id)
            except Exception:
                pass
        self.is_holder = False


instance_lease = InstanceLease()
