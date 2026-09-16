"""
services/speaker_service.py
Mac OS mahalliy karnaylari (speakers) orqali JARVIS ovozini yangratish xizmati.
afplay audio pleyeri orqali asinxron, fonda va xalaqit bermasdan ishlaydi.
"""

import os
import sys
import asyncio
import logging
import shutil
from pathlib import Path
from services.tts_service import generate_voice_message

logger = logging.getLogger(__name__)


class SpeakerService:
    def __init__(self):
        self._is_mac = sys.platform == "darwin"
        self._is_windows = sys.platform.startswith("win")
        self._player_bin = shutil.which("afplay") or shutil.which("ffplay")
        self._powershell_bin = (shutil.which("powershell") or shutil.which("pwsh")) if self._is_windows else None
        self._current_process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        """Karnay orqali ovoz chiqarish imkoniyati mavjudligini tekshiradi (Mac, Windows, Linux)."""
        return bool(self._player_bin or self._is_mac or (self._is_windows and self._powershell_bin))

    async def play_audio_file(self, file_path: Path | str) -> bool:
        """
        Audio faylni (.mp3, .wav, .ogg) kompyuter karnayidan asinxron yangratadi.
        Mac (afplay), Windows (PowerShell/WMPlayer) va Linux (ffplay) ni qo'llab-quvvatlaydi.
        """
        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            logger.warning("Speaker: Audio fayl topilmadi yoki bo'sh: %s", path)
            return False

        async with self._lock:
            try:
                # Agar avvalgi ovoz yangrayotgan bo'lsa, uni to'xtatish
                if self._current_process and self._current_process.returncode is None:
                    try:
                        self._current_process.terminate()
                    except Exception:
                        pass

                if self._is_mac and shutil.which("afplay"):
                    cmd = ["afplay", str(path)]
                elif self._is_windows and self._powershell_bin:
                    # Windows PowerShell orqali standart WMP COM bilan MP3 yangratish
                    resolved_path = str(path.resolve()).replace("'", "''")
                    ps_script = (
                        f"$wmp = New-Object -ComObject WMPlayer.OCX; "
                        f"$wmp.URL = '{resolved_path}'; "
                        f"while ($wmp.playState -ne 1) {{ Start-Sleep -Milliseconds 150 }}"
                    )
                    cmd = [self._powershell_bin, "-NoProfile", "-NonInteractive", "-Command", ps_script]
                elif shutil.which("ffplay"):
                    cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
                else:
                    logger.warning("Speaker: Mos audio pleyer (afplay/powershell/ffplay) topilmadi.")
                    return False

                self._current_process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await self._current_process.wait()
                return True
            except Exception as e:
                logger.error("Speaker: Audio ijrosida xatolik: %s", e)
                return False

    async def speak_text(self, text: str, is_mentor: bool = True) -> bool:
        """
        Matnni Edge-TTS orqali sintez qilib, darhol karnaydan o'zbekcha/ruscha ovozda gapiradi.
        """
        if not text or not text.strip():
            return False

        try:
            voice_path = await generate_voice_message(text, is_mentor=is_mentor)
            if not voice_path or not voice_path.exists():
                # Fallback to macOS native 'say' command if Edge-TTS is offline
                if self._is_mac and shutil.which("say"):
                    logger.info("Speaker: Native Mac 'say' fallback ishlatilmoqda.")
                    proc = await asyncio.create_subprocess_exec(
                        "say", text[:200],
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    return True
                elif self._is_windows and self._powershell_bin:
                    logger.info("Speaker: Windows SAPI.SpVoice fallback ishlatilmoqda.")
                    clean_text = text[:200].replace("'", "''")
                    ps_speak = f"(New-Object -ComObject SAPI.SpVoice).Speak('{clean_text}')"
                    proc = await asyncio.create_subprocess_exec(
                        self._powershell_bin, "-NoProfile", "-NonInteractive", "-Command", ps_speak,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    return True
                return False

            success = await self.play_audio_file(voice_path)
            # Ijrodan so'ng vaqtinchalik faylni o'chirish
            try:
                voice_path.unlink(missing_ok=True)
            except Exception:
                pass
            return success
        except Exception as e:
            logger.error("Speaker: speak_text da xatolik: %s", e)
            return False

    def stop(self) -> None:
        """Joriy yangrayotgan ovozni to'xtatish."""
        if self._current_process and self._current_process.returncode is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass


speaker_service = SpeakerService()
