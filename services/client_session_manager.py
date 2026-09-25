"""
Har bir mijoz (obunachi) uchun alohida Telethon session boshqaruvi.
Har bir mijoz o'z Telegram akkauntidan agent ishlaydi.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from config import config

if TYPE_CHECKING:
    from services.memory_service import SQLiteMemoryService

logger = logging.getLogger(__name__)


class ClientSessionManager:
    """
    Har bir mijozning Telethon sessionini boshqaradi.
    - start_session(user_id, session_string) → client yaratib, handlerlarni ro'yxatga oladi
    - stop_session(user_id) → clientni to'xtatadi
    - Startup'da barcha saqlangan sessionlarni avtomatik ishga tushiradi
    """

    def __init__(self):
        # {user_id: TelegramClient}
        self._clients: dict[int, TelegramClient] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    # ──────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────

    async def start_session(self, user_id: int, session_string: str) -> bool:
        """
        Mijozning string session kodidan Telethon client yaratadi va ishga tushiradi.
        Agar oldindan ishlab turgan session bo'lsa, avval to'xtatiladi.
        """
        if not session_string or not session_string.strip():
            logger.warning("start_session: user_id=%s — session_string bo'sh", user_id)
            return False

        # Eski sessionni to'xtatish
        await self.stop_session(user_id)

        try:
            client = TelegramClient(
                session=StringSession(session_string.strip()),
                api_id=config.api_id,
                api_hash=config.api_hash,
                device_model="Agent Assistent",
                system_version="Executive AI Co-Pilot",
                app_version="coddyHelper Client 2.0",
                lang_code="uz",
                system_lang_code="uz",
            )

            # Handlerlarni ro'yxatga olish (asosiy agentdagi kabi)
            self._register_handlers(client, user_id)

            await client.start()
            me = await client.get_me()
            logger.info(
                "✅ Mijoz sessiyasi ishga tushdi: user_id=%s, telegram_id=%s, username=@%s",
                user_id, me.id if me else "?", me.username if me else "?"
            )

            self._clients[user_id] = client

            # DB ga session_active=1 yozish
            from services.memory_service import memory_service
            memory_service.set_session_active(user_id, True)

            # Fonda disconnect bo'lgunicha ishlaydi
            task = asyncio.create_task(self._run_client(user_id, client))
            self._tasks[user_id] = task

            return True

        except Exception as e:
            logger.error("❌ Mijoz sessiyasini ishga tushirishda xatolik [user_id=%s]: %s", user_id, e)
            from services.memory_service import memory_service
            memory_service.set_session_active(user_id, False)
            return False

    async def stop_session(self, user_id: int) -> bool:
        """Mijoz sessionini to'xtatadi."""
        stopped = False

        task = self._tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            stopped = True

        client = self._clients.pop(user_id, None)
        if client:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.debug("Client disconnect xatolik [%s]: %s", user_id, e)
            stopped = True

        if stopped:
            logger.info("🛑 Mijoz sessiyasi to'xtatildi: user_id=%s", user_id)
            from services.memory_service import memory_service
            memory_service.set_session_active(user_id, False)

        return stopped

    def get_client(self, user_id: int) -> TelegramClient | None:
        """Faol Telethon clientni qaytaradi."""
        return self._clients.get(user_id)

    def is_active(self, user_id: int) -> bool:
        """Sessiya ishlamoqdami?"""
        client = self._clients.get(user_id)
        return client is not None and client.is_connected()

    def active_sessions(self) -> list[int]:
        """Hozir faol bo'lgan barcha mijoz user_id larini qaytaradi."""
        return [uid for uid, c in self._clients.items() if c.is_connected()]

    async def start_all_saved_sessions(self) -> int:
        """
        DB dagi barcha active mijozlarning saqlangan sessionlarini ishga tushiradi.
        main.py startup'da chaqiriladi.
        """
        from services.memory_service import memory_service
        subs = memory_service.get_all_subscriptions()
        started = 0
        for sub in subs:
            uid = sub.get("user_id")
            sess = sub.get("session_string", "")
            active = int(sub.get("active", 0))
            if uid and sess and active:
                logger.info("🔄 Mijoz session ishga tushirilmoqda: user_id=%s", uid)
                ok = await self.start_session(uid, sess)
                if ok:
                    started += 1
        logger.info("🚀 Jami %d ta mijoz session ishga tushdi", started)
        return started

    async def stop_all(self):
        """Barcha sessionlarni to'xtatadi (shutdown uchun)."""
        for uid in list(self._clients.keys()):
            await self.stop_session(uid)

    # ──────────────────────────────────────────────────────
    # INTERNAL
    # ──────────────────────────────────────────────────────

    def _register_handlers(self, client: TelegramClient, user_id: int):
        """Mijoz clientiga asosiy auto-reply handlerini bog'laydi."""
        from services.ai_service import ai_service
        from services.memory_service import memory_service

        @client.on(events.NewMessage(incoming=True))
        async def _on_message(event):
            """Mijoz akkauntiga kelgan xabarga AI javob beradi."""
            try:
                # Faqat shaxsiy xabarlar va guruhlar
                chat_id = event.chat_id
                sender = await event.get_sender()
                if not sender:
                    return

                sender_id = sender.id

                # O'z xabarlariga javob bermasin
                me = await client.get_me()
                if me and sender_id == me.id:
                    return

                # Faqat sub uchun guruh yoki shaxsiy chat
                sub = memory_service.get_subscription(user_id)
                if not sub or not sub.get("active"):
                    return

                # Config'dagi auto_reply kabi ishlaydi
                text = event.raw_text or ""
                if not text.strip():
                    return

                logger.debug(
                    "📩 [Client %s] chat=%s sender=%s: %s",
                    user_id, chat_id, sender_id, text[:80]
                )

                # AI javob generatsiyasi
                reply = await ai_service.generate_reply(
                    message=text,
                    chat_id=chat_id,
                    user_id=sender_id,
                    client=client,
                )
                if reply:
                    await event.reply(reply)

            except Exception as e:
                logger.error("Client handler xatolik [user_id=%s]: %s", user_id, e)

    async def _run_client(self, user_id: int, client: TelegramClient):
        """Clientni disconnect bo'lgunicha ushlab turadi."""
        try:
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Mijoz sessiya uzildi [user_id=%s]: %s", user_id, e)
        finally:
            self._clients.pop(user_id, None)
            from services.memory_service import memory_service
            memory_service.set_session_active(user_id, False)
            logger.info("🔌 Mijoz sessiya yakunlandi: user_id=%s", user_id)


# Global instansiya
client_session_manager = ClientSessionManager()
