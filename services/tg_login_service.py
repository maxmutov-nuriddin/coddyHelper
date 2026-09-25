"""
Mini App orqali Telegram akkauntga xavfsiz ulanish (telefon -> kod -> 2FA parol) va
HSS (StringSession) ni avtomatik yaratish. Mijoz sessiya kodini qo'lda nusxalab o'tirmaydi.

Xavfsizlik:
  • Har bir owner uchun faqat bitta faol login jarayoni; 10 daqiqada eskiradi.
  • Kod yuborish tezligi cheklangan (60 soniyada 1 marta).
  • Parol va kod hech qayerda saqlanmaydi, loglarga yozilmaydi.
"""

import asyncio
import logging
import time

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from config import config

logger = logging.getLogger(__name__)

LOGIN_TTL_SECONDS = 600
SEND_CODE_COOLDOWN = 60


class TgLoginService:
    def __init__(self):
        self._pending: dict[int, dict] = {}
        self._lock = asyncio.Lock()

    async def _cleanup(self) -> None:
        now = time.time()
        for owner_id, st in list(self._pending.items()):
            if now - st["created"] > LOGIN_TTL_SECONDS:
                await self._discard(owner_id)

    async def _discard(self, owner_id: int) -> None:
        st = self._pending.pop(owner_id, None)
        if st and st.get("client"):
            try:
                await st["client"].disconnect()
            except Exception:
                pass

    async def send_code(self, owner_id: int, phone: str) -> dict:
        phone = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
        if not phone.startswith("+"):
            phone = "+" + phone
        if len(phone) < 9:
            return {"ok": False, "error": "Telefon raqamni to'liq kiriting (masalan: +998901234567)."}

        async with self._lock:
            await self._cleanup()
            prev = self._pending.get(owner_id)
            if prev and time.time() - prev.get("code_sent_at", 0) < SEND_CODE_COOLDOWN:
                wait = int(SEND_CODE_COOLDOWN - (time.time() - prev["code_sent_at"]))
                return {"ok": False, "error": f"Kod yaqinda yuborildi. {wait} soniyadan so'ng qayta urinib ko'ring."}
            await self._discard(owner_id)

            client = TelegramClient(
                StringSession(),
                config.api_id,
                config.api_hash,
                device_model="Agent Assistent",
                system_version="Executive AI Co-Pilot",
                app_version="coddyHelper Client 2.0",
                lang_code="uz",
                system_lang_code="uz",
            )
            try:
                await client.connect()
                sent = await client.send_code_request(phone)
            except errors.PhoneNumberInvalidError:
                await client.disconnect()
                return {"ok": False, "error": "Telefon raqam noto'g'ri."}
            except errors.PhoneNumberBannedError:
                await client.disconnect()
                return {"ok": False, "error": "Bu raqam Telegram tomonidan bloklangan."}
            except errors.FloodWaitError as e:
                await client.disconnect()
                return {"ok": False, "error": f"Telegram cheklovi: {e.seconds} soniyadan so'ng urinib ko'ring."}
            except Exception as e:
                await client.disconnect()
                logger.warning("Login kod yuborishda xatolik [owner=%s]: %s", owner_id, e)
                return {"ok": False, "error": f"Kod yuborib bo'lmadi: {e}"}

            self._pending[owner_id] = {
                "client": client,
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "created": time.time(),
                "code_sent_at": time.time(),
                "stage": "code",
            }
            return {"ok": True, "stage": "code", "message": "Tasdiqlash kodi Telegram ilovangizga yuborildi."}

    async def submit_code(self, owner_id: int, code: str) -> dict:
        st = self._pending.get(owner_id)
        if not st or st.get("stage") != "code":
            return {"ok": False, "error": "Avval telefon raqamni kiriting."}
        code = "".join(ch for ch in (code or "") if ch.isdigit())
        if not code:
            return {"ok": False, "error": "Kodni kiriting."}
        client: TelegramClient = st["client"]
        try:
            await client.sign_in(phone=st["phone"], code=code, phone_code_hash=st["phone_code_hash"])
        except errors.SessionPasswordNeededError:
            st["stage"] = "password"
            return {"ok": True, "stage": "password", "message": "Akkauntda ikki bosqichli himoya (2FA) bor. Parolni kiriting."}
        except errors.PhoneCodeInvalidError:
            return {"ok": False, "error": "Kod noto'g'ri. Qayta tekshirib kiriting."}
        except errors.PhoneCodeExpiredError:
            await self._discard(owner_id)
            return {"ok": False, "error": "Kod muddati tugagan. Qaytadan kod so'rang."}
        except Exception as e:
            logger.warning("Login kodini tasdiqlashda xatolik [owner=%s]: %s", owner_id, e)
            return {"ok": False, "error": f"Kirishda xatolik: {e}"}
        return await self._finish(owner_id)

    async def submit_password(self, owner_id: int, password: str) -> dict:
        st = self._pending.get(owner_id)
        if not st or st.get("stage") != "password":
            return {"ok": False, "error": "Parol bosqichi faol emas."}
        if not password:
            return {"ok": False, "error": "Parolni kiriting."}
        client: TelegramClient = st["client"]
        try:
            await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            return {"ok": False, "error": "Parol noto'g'ri."}
        except Exception as e:
            logger.warning("2FA parolni tasdiqlashda xatolik [owner=%s]: %s", owner_id, e)
            return {"ok": False, "error": f"Kirishda xatolik: {e}"}
        return await self._finish(owner_id)

    async def cancel(self, owner_id: int) -> None:
        await self._discard(owner_id)

    async def _finish(self, owner_id: int) -> dict:
        st = self._pending.get(owner_id)
        client: TelegramClient = st["client"]
        try:
            me = await client.get_me()
            session_string = client.session.save()
        finally:
            # Vaqtinchalik ulanishni yopamiz — agent shu kod bilan alohida (bitta) ulanish ochadi
            self._pending.pop(owner_id, None)
            try:
                await client.disconnect()
            except Exception:
                pass

        from services.memory_service import memory_service
        from services.client_session_manager import client_session_manager
        memory_service.save_session_string(owner_id, session_string)
        started = await client_session_manager.start_session(owner_id, session_string)
        status = client_session_manager.get_status(owner_id)
        return {
            "ok": True,
            "stage": "done",
            "started": started,
            "account": {"id": me.id, "username": me.username or "", "name": me.first_name or ""},
            "agent": status,
            "message": "✅ Telegram akkauntingiz ulandi!" + ("" if started else " Agent tez orada ishga tushadi."),
        }


tg_login_service = TgLoginService()
