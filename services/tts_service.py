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


def clean_text_for_speech(text: str, is_mentor: bool = True) -> str:
    """
    Dasturlash va assistent matnini JARVIS uslubidagi tabiiy jonli nutqqa aylantiradi:
    - Katta kod bloklarini ixcham qilib, chalg'itmaydigan holatga keltiradi.
    - Markdown belgilarini (**bold**, `code`, # sarlavhalar, havolalar) tozalaydi.
    - Haddan tashqari uzun matnlarni 15-20 soniyalik lo'nda nutqqa moslashtiradi.
    """
    if not text:
        return ""

    t = text.strip()

    # Eskalatsiya teglari bo'lsa tozalash
    t = re.sub(r"<<<ESCALATE>>>.*?<<<END_ESCALATE>>>", "", t, flags=re.DOTALL)

    # Action teglari (<<<ACTION:...>>>) bo'lsa tozalash
    t = re.sub(r"<<<ACTION:.*?>>>", "", t, flags=re.DOTALL)

    # Kod bloklarini aniqlash (``` ... ```)
    has_code_block = bool(re.search(r"```[\w]*\n(.*?)```", t, flags=re.DOTALL))
    if has_code_block:
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

    # Ro'yxat markerlari (•, -, 1., 2.)
    t = re.sub(r"^\s*[•\-\*]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)

    # Emojilarni tozalash (TTS ovozlar emojilarni xunuk o'qimasligi uchun)
    t = re.sub(r"[^\w\s\.,!\?':;\-\(\)]", " ", t)

    # Ortiqcha probellarni tozalash
    t = re.sub(r"\s+", " ", t).strip()

    # Agar matn juda uzun bo'lsa (20 soniyadan oshmasligi uchun eng muhim birinchi 3-4 jumla olinadi)
    sentences = re.split(r"(?<=[.!?])\s+", t)
    if len(t) > 350 and len(sentences) > 2:
        short_spoken = " ".join(sentences[:3])
        if is_mostly_russian(t):
            t = f"{short_spoken} Подробный ответ и детали привел в текстовом сообщении."
        else:
            t = f"{short_spoken} To'liq tafsilotlarni quyidagi matnda keltirdim, Ustoz."
    elif len(t) > 500:
        t = t[:490] + "..."

    return t


def is_mostly_russian(text: str) -> bool:
    """Matn asosan rus tilida ekanligini aniqlaydi."""
    cyrillic_chars = len(re.findall(r"[\u0400-\u04FF]", text))
    total_letters = len(re.findall(r"[a-zA-Z\u0400-\u04FF]", text))
    if total_letters > 0 and (cyrillic_chars / total_letters) > 0.4:
        ru_words = {"привет", "код", "ошибка", "как", "почему", "что", "это", "пожалуйста", "спасибо", "учитель", "здравствуйте"}
        lower_words = set(text.lower().split())
        if ru_words.intersection(lower_words):
            return True
    return False


async def generate_voice_message(text: str, is_mentor: bool = True) -> Path | None:
    """
    Matnni tabiiy, sokin va professional JARVIS nutqiga aylantiradi (.mp3).
    Muvaffaqiyatsiz bo'lsa None qaytaradi.
    """
    clean_text = clean_text_for_speech(text, is_mentor=is_mentor)
    if not clean_text or len(clean_text) < 2:
        return None

    voice = VOICE_RUSSIAN if is_mostly_russian(clean_text) else VOICE_UZBEK

    try:
        tmp_dir = Path(tempfile.gettempdir()) / "coddy_voice"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = tmp_dir / f"voice_{int(asyncio.get_event_loop().time() * 1000)}.mp3"

        # +5% tezlik - nutqni chaqqon, professional va samimiy qiladi
        communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate="+5%")
        await communicate.save(str(tmp_file))

        if tmp_file.exists() and tmp_file.stat().st_size > 0:
            logger.info("🎙 JARVIS Ovozli xabar muvaffaqiyatli sintezlandi: %s (Hajmi: %d bayt, Ovoz: %s)", tmp_file.name, tmp_file.stat().st_size, voice)
            return tmp_file
    except Exception as e:
        logger.error("JARVIS Ovoz sintezida xatolik: %s", e)

    return None
