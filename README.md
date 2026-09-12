# coddyHelper — Shaxsiy Telegram AI Yordamchisi (Userbot)

Ushbu loyiha sizning shaxsiy Telegram akkauntingiz nomidan kelgan xabarlarga avtomatik aqlli javob qaytarish, matnlarni tahlil qilish va istalgan chatda AI yordamidan foydalanish imkoniyatini beruvchi shaxsiy AI agentdir.

Loyiha **Telethon** (Telegram Client API) va **Google Gemini API** (`gemini-2.5-flash` / `gemini-1.5-flash`) asosida qurilgan.

---

## 📌 Asosiy Imkoniyatlar

- **Avto-javob (Auto-reply):** Shaxsiy yozishmalarda (DM/Lichka) kelgan savol va murojaatlarga tabiiy o'zbek tilida, aniq va muvozanatli javob qaytaradi.
- **Qo'lda boshqariladigan AI buyruqlar:** Istalgan chatda yoki guruhda `.ai <savolingiz>` orqali tezkor maslahat va yechim olish.
- **Xabarni tahlil qilish:** Biror xabarga reply qilib `.ai` deb yozsangiz, AI uni tahlil qilib, yechim beradi.
- **Kontekst xotirasi (Memory):** Har bir suhbatdosh bilan avvalgi xabarlarni eslab qoladi va mantiqiy davomiy suhbat olib boradi.
- **Moslashuvchan boshqaruv:** Avto-javobni istalgan daqiqada Telegram'ning o'zidan `.ai on` yoki `.ai off` orqali yoqish/o'chirish.
- **Spam va bot himoyasi:** Guruhlarni, kanallarni, botlarni va tezkor takroriy yozishmalarni (flood) avtomatik filtrlash.

---

## 🛠 O'rnatish va Sozlash

### 1. Virtual muhit yaratish va faollashtirish
Loyihaning asosiy papkasida terminalni oching:

```bash
cd /Applications/Project/coddyHelper
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 3. API kalitlarini olish

1. **Telegram API (`API_ID` va `API_HASH`):**
   - [my.telegram.org](https://my.telegram.org) saytiga kiring.
   - Telefon raqamingiz orqali tizimga kiring.
   - **"API development tools"** bo'limiga o'ting va yangi ilova yarating (masalan, `coddyHelper`).
   - Berilgan `api_id` va `api_hash` ni nusxalab oling.

2. **Google Gemini API kaliti:**
   - [Google AI Studio](https://aistudio.google.com/) saytiga kiring.
   - **"Get API key"** tugmasini bosing va bepul API kalit yarating.

### 4. `.env` faylini yaratish
`.env.example` faylidan nusxa olib `.env` faylini yarating:

```bash
cp .env.example .env
```

`.env` faylini ochib, olingan kalitlarni kiriting:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=a1b2c3d4e5f6...
TELEGRAM_PHONE=+998901234567

GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.5-flash
AUTO_REPLY_ENABLED=true
COMMAND_PREFIX=.
MEMORY_LIMIT=10
```

---

## 🚀 Ishga Tushirish

Loyihani ishga tushiring:
```bash
python main.py
```

> **Birinchi marta ishga tushirishda:**
> Telethon terminalda Telegram'ga kirish uchun tasdiqlash kodini (SMS yoki rasmiy Telegram akkauntingizga kelgan kod) va agar o'rnatilgan bo'lsa, Ikki bosqichli parolingizni (2FA) so'raydi.
> Kod kiritilgach, avtomatik `coddy_helper_session.session` fayli yaratiladi va keyingi safar kod so'ralmaydi.

---

## ⌨️ Shaxsiy Buyruqlar (Telegram orqali)

Istalgan chatda yoki **"Saved Messages" (Saqlangan xabarlar)** orqali quyidagi buyruqlarni yuborishingiz mumkin:

| Buyruq | Tavsifi |
| :--- | :--- |
| `.ai <matn>` | AI dan tezkor javob olish (xabaringiz avtomatik AI javobiga aylanadi) |
| *Reply* + `.ai` | Belgilangan xabarga tahlil yoki javob yaratish |
| `.ai on` | Shaxsiy xabarlarga avto-javob rejimini yoqish |
| `.ai off` | Avto-javob rejimini to'xtatish (faqat qo'lda buyruqlar ishlaydi) |
| `.status` | Tizim holati, AI modeli va faol chatlar statistikasini ko'rish |
| `.clear` | Ushbu chatdagi so'nggi xotirani tozalash |
| `.help` | Barcha buyruqlar ro'yxatini chiqarish |

---

## 🔒 Xavfsizlik Eslatmasi

- `.session` va `.env` fayllaringizni hech kimga bermang va GitHub yoki boshqa ommaviy platformalarga yuklamang.
- Ushbu dastur shaxsiy foydalanish uchun mo'ljallangan bo'lib, Telegram akkauntingiz xavfsizligini ta'minlash uchun Telegram cheklovlari (Flood limit) va spam-filtrlarga amal qiladi.
