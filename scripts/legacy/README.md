# Legacy skriptlar

Bu papkadagi fayllar loyiha rivojlanishi davomida **bir martalik** ishlatilgan patch/migratsiya skriptlari
(masalan `web_app.py` yoki `memory_service.py` ga kod qo'shish, MongoDB ma'lumotlarini to'ldirish),
shuningdek eskirgan/almashtirilgan implementatsiyalar.

- Ishlab chiqarishda (Render) hech biri import qilinmaydi va ishga tushirilmaydi.
- Ular eski kod holatiga mo'ljallangan — **qayta ishga tushirmang**, joriy fayllarni buzishi mumkin.
- `bot_py_old_standalone_DEPRECATED.py` — loyihaning ILK bosqichidagi mustaqil aiogram bot prototipi.
  Hozirgi ishlab chiqarish bot xizmati **`services/bot_service.py`** da (main.py orqali ishga tushadi).
  ⚠️ Bu faylni ishga tushirmang — u xuddi shu `BOT_TOKEN` bilan ulanib, Telegram'ning `getUpdates`
  konfliktiga (ikkita bot bir tokendan foydalansa) sabab bo'ladi.
- Tarix va ma'lumot uchun saqlab qo'yilgan.
