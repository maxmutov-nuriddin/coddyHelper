"""
Edge-TTS orqali ovozli xabarlar yaratish xizmati (Voice-to-Voice AI).
CoddyCamp mentori nomidan tabiiy o'zbekcha ovoz (uz-UZ-SardorNeural) sintezi.
"""

import asyncio
import logging
import re
import tempfile
from pathlib import Path
import edge_tts

logger = logging.getLogger(__name__)

VOICE_UZBEK = "uz-UZ-SardorNeural"
VOICE_RUSSIAN = "ru-RU-DmitryNeural"


def clean_text_for_speech(text: str) -> str:
    """
    Dasturlash matnini audio uchun tozalaydi:
    - Katta kod bloklarini ixcham qilib, o'qilishi qulay holatga keltiradi.
    - Markdown belgilarini (**bold**, `code`, # sarlavhalar, havolalar) tozalaydi.
    """
    if not text:
        return ""

    t = text.strip()

    # Eskalatsiya teglari bo'lsa tozalash
    t = re.sub(r"<<<ESCALATE>>>.*?<<<END_ESCALATE>>>", "", t, flags=re.DOTALL)

    # Kod bloklarini aniqlash (``` ... ```)
    has_code_block = bool(re.search(r"```[\w]*\n(.*?)```", t, flags=re.DOTALL))
    if has_code_block:
        # Kod bloklarini audio matnida oddiy tushuntirish bilan almashtiramiz
        t = re.sub(r"```[\w]*\n(.*?)```", "To'liq kodni quyidagi matnli xabarda yozib qoldirdim.", t, flags=re.DOTALL)

    # Inline kod belgilarini tozalash (`code`)
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Markdown formatlash belgilarini olib tashlash
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)  # Bold
    t = re.sub(r"\*([^*]+)\*", r"\1", t)      # Italic
    t = re.sub(r"__([^_]+)__", r"\1", t)      # Underline
    t = re.sub(r"#+\s*", "", t)               # Headers
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)  # Markdown links [text](url)
    t = re.sub(r"https?://\S+", "", t)        # URLs

    # Emojilarni tozalash (ba'zi TTS dvigatellari emojilarni xunuk o'qiydi)
    t = re.sub(r"[^\w\s\.,!\?':;\-\(\)]", " ", t)

    # Ortiqcha probellarni tozalash
    t = re.sub(r"\s+", " ", t).strip()

    # Juda uzun bo'lib ketmasligi uchun (maksimal 1000 belgi ovozda)
    if len(t) > 1000:
        t = t[:995] + "..."

    return t


def is_mostly_russian(text: str) -> bool:
    """Matn asosan rus tilida ekanligini aniqlaydi."""
    cyrillic_chars = len(re.findall(r"[\u0400-\u04FF]", text))
    total_letters = len(re.findall(r"[a-zA-Z\u0400-\u04FF]", text))
    if total_letters > 0 and (cyrillic_chars / total_letters) > 0.4:
        # Ruscha so'zlarni tekshirish
        ru_words = {"привет", "код", "ошибка", "как", "почему", "что", "это", "пожалуйста", "спасибо"}
        lower_words = set(text.lower().split())
        if ru_words.intersection(lower_words):
            return True
    return False


async def generate_voice_message(text: str) -> Path | None:
    """
    Matnni tabiiy ovozga aylantiradi va audio fayl (.mp3) yo'lini qaytaradi.
    Muvaffaqiyatsiz bo'lsa None qaytaradi.
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text or len(clean_text) < 2:
        return None

    voice = VOICE_RUSSIAN if is_mostly_russian(clean_text) else VOICE_UZBEK

    try:
        tmp_dir = Path(tempfile.gettempdir()) / "coddy_voice"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = tmp_dir / f"voice_{int(asyncio.get_event_loop().time() * 1000)}.mp3"

        communicate = edge_tts.Communicate(text=clean_text, voice=voice)
        await communicate.save(str(tmp_file))

        if tmp_file.exists() and tmp_file.stat().st_size > 0:
            logger.info("Edge-TTS ovozli xabar muvaffaqiyatli yaratildi: %s (Hajmi: %d bayt, Ovoz: %s)", tmp_file.name, tmp_file.stat().st_size, voice)
            return tmp_file
    except Exception as e:
        logger.error("Edge-TTS ovoz yaratishda xatolik: %s", e)

    return None
