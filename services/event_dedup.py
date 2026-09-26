"""
Telethon ulanish uzilib qayta ulanganda ("catch-up" / gap recovery) ba'zan bir xil xabarni
ikkinchi marta "yangi xabar" (NewMessage) hodisasi sifatida qayta yuborishi mumkin — bu esa
Render kabi "uxlab qoladigan" xostingda har qayta ishga tushishda kuzatiladi (mentor eslatma
yozgan payt yoki undan keyin uxlab qolsa, uyg'onganda o'sha xabar qayta "kelib", eslatma yoki
javob ikki marta yaratilib qoladi).

Bu modul har bir (chat_id, message_id) juftligini FAQAT BIR MARTA qayta ishlashni kafolatlaydi.
Xotira chegaralangan (eng ko'p _MAX_TRACKED ta), shuning uchun cheksiz o'smaydi.
"""

from collections import deque

_MAX_TRACKED = 4000
_seen_ids: set[tuple[int, int, int]] = set()
_seen_order: deque[tuple[int, int, int]] = deque()


def is_duplicate_event(chat_id: int, msg_id: int, scope: int = 0) -> bool:
    """
    (scope, chat_id, msg_id) juftligi avval ko'rilgan bo'lsa True qaytaradi (chaqiruvchi darhol
    to'xtashi kerak). Aks holda uni "ko'rilgan" deb belgilab, False qaytaradi.

    `scope` — mustaqil hisoblanadigan nazorat maydoni (masalan mijoz agenti uchun owner user_id).
    Bir xil chat/xabar ID turli mijoz akkauntlari uchun mustaqil hisoblanishi kerak bo'lgan
    hollarda (bitta fizik guruhga bir nechta obunachi a'zo bo'lishi mumkin) ishlatiladi.
    """
    if not msg_id:
        return False
    key = (int(scope or 0), int(chat_id or 0), int(msg_id))
    if key in _seen_ids:
        return True
    _seen_ids.add(key)
    _seen_order.append(key)
    while len(_seen_order) > _MAX_TRACKED:
        old = _seen_order.popleft()
        _seen_ids.discard(old)
    return False


def reset() -> None:
    """Xotiradagi holatni tozalaydi (asosan testlar uchun — global holat testlar orasida sizmasligi kerak)."""
    _seen_ids.clear()
    _seen_order.clear()
