"""
services/mac_control_service.py
Mac OS va tizim darajasida boshqaruv xizmati (JARVIS Mac Hands).
AppleScript, Shortcuts CLI, open, pmset va tizim parametrlarini asinxron boshqaradi.
"""

import os
import re
import sys
import shutil
import asyncio
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class MacControlService:
    def __init__(self):
        self._platform = sys.platform
        self._is_mac = sys.platform == "darwin"
        self._is_windows = sys.platform.startswith("win")
        self._lock = asyncio.Lock()

    def is_mac(self) -> bool:
        return self._is_mac

    # -----------------------------------------------------------
    # 1. Tizim Statusi va Diagnostika (Battery, CPU, RAM, Volume)
    # -----------------------------------------------------------
    async def get_system_status(self) -> dict[str, Any]:
        """Mac (yoki boshqa OS) tizim holati metrikalarini qaytaradi."""
        status = {
            "platform": self._platform,
            "is_mac": self._is_mac,
            "battery_pct": None,
            "battery_state": "unknown",
            "cpu_pct": 0.0,
            "cpu_cores": os.cpu_count() or 1,
            "ram_total_gb": 0.0,
            "volume": 50,
            "muted": False,
        }

        # CPU hisoblash
        try:
            load1, _, _ = os.getloadavg()
            status["cpu_pct"] = round((load1 / status["cpu_cores"]) * 100, 1)
        except Exception:
            status["cpu_pct"] = 15.0

        # RAM hisoblash (Mac da sysctl orqali)
        if self._is_mac:
            try:
                out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2)
                mem_bytes = int(out.decode().strip())
                status["ram_total_gb"] = round(mem_bytes / (1024**3), 1)
            except Exception:
                status["ram_total_gb"] = 16.0

        # Batareya holati
        if self._is_mac and shutil.which("pmset"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pmset", "-g", "batt",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
                text = stdout.decode("utf-8", errors="ignore")
                
                pct_match = re.search(r"(\d+)%", text)
                if pct_match:
                    status["battery_pct"] = int(pct_match.group(1))

                if "AC Power" in text or "charging" in text.lower():
                    status["battery_state"] = "charging"
                elif "charged" in text.lower():
                    status["battery_state"] = "full"
                elif "discharging" in text.lower():
                    status["battery_state"] = "discharging"
            except Exception as e:
                logger.debug("Batareya statusini olishda ogohlantirish: %s", e)

        # Ovoz holati
        if self._is_mac and shutil.which("osascript"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", "output volume of (get volume settings)",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
                v_text = stdout.decode().strip()
                if v_text.isdigit():
                    status["volume"] = int(v_text)

                proc_mute = await asyncio.create_subprocess_exec(
                    "osascript", "-e", "output muted of (get volume settings)",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                m_out, _ = await asyncio.wait_for(proc_mute.communicate(), timeout=3)
                status["muted"] = "true" in m_out.decode().lower()
            except Exception as e:
                logger.debug("Ovoz darajasini olishda ogohlantirish: %s", e)

        return status

    # -----------------------------------------------------------
    # 2. Ovozni Sozlash (Volume Control)
    # -----------------------------------------------------------
    async def set_volume(self, level: int | str) -> tuple[bool, str]:
        """
        Mac ovozini sozlaydi (0-100, mute, unmute, max).
        """
        if not self._is_mac:
            return False, "Ovoz boshqaruvi faqat Mac OS tizimida qo'llab-quvvatlanadi."

        async with self._lock:
            try:
                cmd_str = str(level).strip().lower()
                if cmd_str in ("mute", "jim", "ochir", "0"):
                    script = "set volume output muted true"
                    msg = "Mac ovozi o'chirildi (Mute) 🔇"
                elif cmd_str in ("unmute", "yoq", "eshittir"):
                    script = "set volume output muted false"
                    msg = "Mac ovozi yoqildi (Unmute) 🔊"
                elif cmd_str in ("max", "maks", "100"):
                    script = "set volume output volume 100\nset volume output muted false"
                    msg = "Mac ovozi 100% (Maksimal) ga o'rnatildi 🔊"
                elif cmd_str in ("min", "5", "10"):
                    script = "set volume output volume 15\nset volume output muted false"
                    msg = "Mac ovozi 15% (Past) ga o'rnatildi 🔉"
                else:
                    clean_digits = re.sub(r"[^\d]", "", cmd_str)
                    val = int(clean_digits) if clean_digits else 50
                    val = max(0, min(100, val))
                    script = f"set volume output volume {val}\nset volume output muted false"
                    msg = f"Mac ovozi {val}% ga o'rnatildi 🔉"

                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
                if proc.returncode == 0:
                    return True, msg
                return False, f"AppleScript xatosi: {stderr.decode()}"
            except Exception as e:
                logger.error("Ovozni o'rnatishda xatolik: %s", e)
                return False, str(e)

    # -----------------------------------------------------------
    # 3. Ekranni Qulflash (Lock Screen)
    # -----------------------------------------------------------
    async def lock_screen(self) -> tuple[bool, str]:
        """Mac ekranini darhol qulflaydi / uyqu rejimiga o'tkazadi."""
        if not self._is_mac:
            return False, "Ekranni qulflash faqat Mac OS tizimida qo'llab-quvvatlanadi."

        try:
            proc = await asyncio.create_subprocess_exec(
                "pmset", "displaysleepnow",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=3)
            return True, "🔒 Mac ekrani muvaffaqiyatli qulflandi va uyqu rejimiga o'tkazildi."
        except Exception as e:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", 'tell application "System Events" to sleep',
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return True, "🔒 Mac uyqu rejimiga o'tkazildi."
            except Exception as fb_e:
                logger.error("Ekranni qulflashda xatolik: %s", fb_e)
                return False, f"Xatolik: {e}"

    # -----------------------------------------------------------
    # 4. Dastur va Havolalarni Ochish (Open App / URL)
    # -----------------------------------------------------------
    async def open_app_or_url(self, target: str) -> tuple[bool, str]:
        """
        Ilova (Chrome, Telegram, Code) yoki veb-havolani ochadi.
        """
        clean_target = target.strip()
        if not clean_target:
            return False, "Ochish uchun dastur nomi yoki havola kiritilmadi."

        if any(c in clean_target for c in [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n"]):
            return False, "Xavfsizlik qoidasi: Maxsus belgilar kiritish taqiqlangan."

        try:
            if clean_target.startswith("http://") or clean_target.startswith("https://"):
                proc = await asyncio.create_subprocess_exec(
                    "open", clean_target,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=5)
                return True, f"🌐 Sayt ochildi: `{clean_target}`"

            app_map = {
                "chrome": "Google Chrome",
                "google chrome": "Google Chrome",
                "tg": "Telegram",
                "telegram": "Telegram",
                "code": "Visual Studio Code",
                "vscode": "Visual Studio Code",
                "safari": "Safari",
                "music": "Music",
                "spotify": "Spotify",
                "notes": "Notes",
                "finder": "Finder",
                "terminal": "Terminal",
                "iterm": "iTerm",
            }
            app_name = app_map.get(clean_target.lower(), clean_target)

            if self._is_mac:
                proc = await asyncio.create_subprocess_exec(
                    "open", "-a", app_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
                if proc.returncode == 0:
                    return True, f"🚀 **{app_name}** dasturi Mac'da ochildi!"
                return False, f"Dasturni ochib bo'lmadi: {stderr.decode()[:100]}"
            else:
                return False, f"Hozirgi operatsion tizimda dasturlarni ochish qo'llab-quvvatlanmaydi."
        except Exception as e:
            logger.error("Dastur ochishda xatolik: %s", e)
            return False, str(e)

    # -----------------------------------------------------------
    # 5. Apple Shortcuts (Tezkor Buyruqlar) Boshqaruvi
    # -----------------------------------------------------------
    async def get_available_shortcuts(self) -> list[str]:
        """Mac OS dagi mavjud Shortcuts ssenariylarini ro'yxatini qaytaradi."""
        if not self._is_mac or not shutil.which("shortcuts"):
            return []

        try:
            proc = await asyncio.create_subprocess_exec(
                "shortcuts", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4)
            lines = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
            return lines
        except Exception as e:
            logger.debug("Shortcuts ro'yxatini olishda xatolik: %s", e)
            return []

    async def run_shortcut(self, shortcut_name: str) -> tuple[bool, str]:
        """Mac Shortcuts ilovasidagi ssenariyni ishga tushiradi."""
        name = shortcut_name.strip()
        if not name:
            return False, "Shortcut nomi kiritilmadi."

        if not self._is_mac or not shutil.which("shortcuts"):
            return False, "Apple Shortcuts xizmati faqat macOS Monterey va undan yuqori tizimlarda mavjud."

        try:
            proc = await asyncio.create_subprocess_exec(
                "shortcuts", "run", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                res = stdout.decode().strip()
                out_msg = f"⚡ **{name}** buyrug'i muvaffaqiyatli bajarildi!"
                if res:
                    out_msg += f"\nNatija: `{res[:150]}`"
                return True, out_msg
            return False, f"Shortcut bajarishda xatolik: {stderr.decode()[:120]}"
        except asyncio.TimeoutError:
            return False, f"**{name}** bajarilishi 15 soniyadan oshib ketdi."
        except Exception as e:
            logger.error("Shortcut bajarishda xatolik: %s", e)
            return False, str(e)

    # -----------------------------------------------------------
    # 6. Mac Bildirishnomalari (Desktop Notifications)
    # -----------------------------------------------------------
    async def send_notification(self, title: str, message: str) -> bool:
        """Mac ekranida mahalliy bildirishnoma (banner) chiqaradi."""
        if not self._is_mac:
            return False

        try:
            clean_title = title.replace('"', '\\"')
            clean_msg = message.replace('"', '\\"')
            script = f'display notification "{clean_msg}" with title "{clean_title}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=3)
            return True
        except Exception as e:
            logger.debug("Notification chiqarishda xatolik: %s", e)
            return False


mac_control_service = MacControlService()
