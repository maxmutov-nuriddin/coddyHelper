"""
Telethon ulanish uzilib qayta ulanganda ("catch-up" / gap recovery) ba'zan bir xil xabarni
ikkinchi marta "yangi xabar" (NewMessage) hodisasi sifatida qayta yuborishi mumkin — bu esa
Render kabi "uxlab qoladigan" xostingda har qayta ishga tushishda kuzatiladi (mentor eslatma
yozgan payt yoki undan keyin uxlab qolsa, uyg'onganda o'sha xabar qayta "kelib", eslatma yoki
javob ikki marta yaratilib qoladi).

Bu modul har bir (handler, scope, chat_id, message_id) to'rtligini FAQAT BIR MARTA qayta
ishlashni kafolatlaydi. Xotira chegaralangan (eng ko'p _MAX_TRACKED ta), shuning uchun
cheksiz o'smaydi.

MUHIM (ilgari bo'lgan xatoning oldini olish uchun): `handler` HAR BIR chaqiruvchi uchun
NOYOB bo'lishi SHART. Telethon bir xil hodisa (masalan bitta chiquvchi xabar) uchun UNGA MOS
BARCHA `@client.on(...)` handlerlarini chaqiradi — faqat bittasini emas! Agar ikkita mustaqil
handler (masalan `handlers/commands.py` dagi va `handlers/auto_reply.py` dagi) bir xil
`handler` nomi (yoki umuman bermasdan standart qiymat) bilan shu funksiyani chaqirsa, BIRINCHISI
xabarni "ko'rilgan" deb belgilab qo'yadi va IKKINCHISI (garchi u butunlay boshqa ishni bajarishi
kerak bo'lsa ham) uni "takroriy" deb hisoblab, HECH NARSA QILMASDAN chiqib ketadi — aynan shu
sabab Vazifalar guruhi butunlay javob bermay qolgan edi.
"""

from collections import deque

_MAX_TRACKED = 8000
_seen_ids: set[tuple[str, int, int, int]] = set()
_seen_order: deque[tuple[str, int, int, int]] = deque()


def is_duplicate_event(handler: str, chat_id: int, msg_id: int, scope: int = 0) -> bool:
    """
    (handler, scope, chat_id, msg_id) to'rtligi avval ko'rilgan bo'lsa True qaytaradi
    (chaqiruvchi darhol to'xtashi kerak). Aks holda uni "ko'rilgan" deb belgilab, False qaytaradi.

    `handler` — shu tekshiruvni chaqirayotgan aniq funksiya/handlerning NOYOB nomi (masalan
    "auto_reply.on_mentor_message"). Bu majburiy: turli handlerlar bir xil fizik xabarni
    mustaqil ravishda (bir-biriga ta'sir qilmasdan) ko'rib chiqishi kerak, chunki Telethon
    bitta hodisaga mos BARCHA ro'yxatdan o'tgan handlerlarni chaqiradi, faqat bittasini emas.

    `scope` — qo'shimcha mustaqil nazorat maydoni (masalan mijoz agenti uchun owner user_id).
    Bir xil chat/xabar ID turli mijoz akkauntlari uchun mustaqil hisoblanishi kerak bo'lgan
    hollarda (bitta fizik guruhga bir nechta obunachi a'zo bo'lishi mumkin) ishlatiladi.
    """
    if not msg_id:
        return False
    key = (str(handler), int(scope or 0), int(chat_id or 0), int(msg_id))
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
