# CoddyHelper — Multi-Tenant AI Agent Platformasi (Telegram)

CoddyHelper — Telegram'da **haqiqiy akkaunt (userbot)** nomidan ishlaydigan AI agent va obunachilar uchun
SaaS platforma. Har bir obunachi **o'z Telegram akkaunti** orqali ishlaydigan **shaxsiy agent** va
**boshqalar bilan aralashmaydigan shaxsiy baza** oladi. **@mentor_cc** — Super Admin: tizim egasi,
support va o'zi ham foydalanuvchi.

---

## Arxitektura

```
Telegram Mini App (templates/admin_app.html)
        │  initData (HMAC imzo) / shaxsiy token
        ▼
aiohttp web server (web_app.py) ── api_tenant_guard middleware ──► tenant_scope(user_id)
        │
        ├─ Super Admin (tenant 0) ── coddy_memory.db + MongoDB asosiy kolleksiyalari
        │     └─ mentor Telethon clienti (handlers/*), bot (@coddyassistanstbot), avtonom miya
        │
        └─ Obunachi (tenant N) ──── tenants/tenant_N.db ──(45s)──► MongoDB tenant_snapshots
              └─ o'z Telethon clienti (services/client_session_manager.py)
```

| Modul | Vazifasi |
|---|---|
| `services/tenant_context.py` | Joriy tenant (ContextVar). Standart 0 = Super Admin |
| `services/memory_service.py` | SQLite qatlami; tenant bo'yicha fayl tanlaydi; obuna/token — doimo asosiy bazada |
| `services/tenant_store.py` | Tenant bazalarini MongoDB'ga snapshot qilish va restartda tiklash |
| `services/instance_lease.py` | Mijoz sessiyalarini bir vaqtda faqat bitta server yuritadi (AUTH_KEY_DUPLICATED himoyasi) |
| `services/client_session_manager.py` | Mijoz agentlari: ulanish, xatolar, egasi buyruqlari, begonalarga javob, CRM, eslatmalar |
| `services/tg_login_service.py` | Mini App'da telefon → kod → 2FA orqali ulanish |
| `services/secret_box.py` | HSS (StringSession) kodlarini shifrlash |
| `services/ai_service.py` | Groq multi-key kaskad + Gemini, persona/prompt (tenantga mos) |
| `services/agent_runner.py` | ReAct agent (Telegramni boshqarish vositalari) |
| `services/bot_service.py` | Bot: /start, /grant, /revoke, /clients, /buy (Telegram Stars) |

---

## Obunachi uchun qanday ishlaydi

1. Super Admin obuna beradi: botda `/grant <user_id yoki @username> <kun> [biznes nomi]`
   (yoki `SUBSCRIPTION_STARS_PRICE` yoqilgan bo'lsa, obunachi `/buy` orqali o'zi sotib oladi).
2. Obunachi botda `/start` → **Boshqaruv** tugmasi → Mini App.
3. **🤖 Mening Agentim** → telefon raqam → Telegram kodi → (2FA parol) → agent ishga tushadi.
4. **Bilimlar** bo'limiga narxlar, qoidalar, ish vaqti kiritiladi; **Biznes profili**da AI yo'riqnomasi.

**Agent xulqi:**
- Begonalar yozsa — biznes doirasida javob beradi (buyruq bajarmaydi, kontakt/shaxsiy ma'lumot bermaydi).
- Guruhlarda standart holatda faqat murojaat qilinganda javob beradi.
- Egasi chatga o'zi yozsa — AI shu chatda jim turadi (sozlanadi).
- AI aniq bilmasa — egasiga bot orqali xabar beradi.
- Ovozli xabarni tushunadi va ovozli javob beradi (sozlanadi).
- Kim yozgani **👥 Kim yozdi** ro'yxatida (CRM).

**Egasi agentni boshqaradi:** o'z *Saqlangan xabarlar*iga `ai <buyruq>` yozadi (yoki Mini App orqali):
`ai Alisherga ertaga 10:00 da uchrashuv borligini yoz`, `ai oxirgi yozganlarni ko'rsat` va h.k.

---

## O'rnatish

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # qiymatlarni to'ldiring
python main.py
```

### Muhim muhit o'zgaruvchilari

| O'zgaruvchi | Izoh |
|---|---|
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_STRING_SESSION` | Super Admin akkaunti |
| `BOT_TOKEN`, `BOT_USERNAME`, `MENTOR_USER_ID` | Bot va Super Admin |
| `GROQ_*_KEYS`, `GEMINI_API_KEY` | AI provayderlar |
| `MONGODB_URI`, `MONGODB_DB_NAME` | Bulut xotira (restartda ma'lumot tiklash uchun **shart**) |
| `SESSION_ENCRYPTION_KEY` | HSS kodlarni shifrlash. Barcha serverlarda **bir xil** bo'lsin |
| `CLIENT_SESSIONS_MODE` | `auto` (standart) / `off` (lokal ishlab chiqish uchun tavsiya) / `force` |
| `MAX_CLIENT_SESSIONS` | Bir serverdagi agentlar limiti (standart 12; Render free ≈ 512 MB) |
| `SUBSCRIPTION_STARS_PRICE`, `SUBSCRIPTION_DAYS` | Telegram Stars orqali obuna (0 = o'chiq) |
| `MASTER_ADMIN_TOKEN` | Ixtiyoriy favqulodda token (bo'sh = o'chiq) |

> ⚠️ Lokal kompyuterda ishga tushirganda `CLIENT_SESSIONS_MODE=off` qo'ying: bir xil HSS kodi ikki joyda
> ulansa Telegram sessiyani bekor qiladi va mijoz akkauntidan chiqib ketadi (lease buni ham oldini oladi).

---

## Xavfsizlik

- Mini App'ga kirish faqat **imzolangan Telegram initData** yoki shaxsiy muddatli token orqali.
- Guruhga pin qilinadigan tugmalarda token yo'q (bot shaxsiy chatiga yo'naltiradi).
- Mijoz tokeni bilan Super Admin endpointlari (backup, restart, mac, broadcast, dosyelar...) yopiq.
- HSS kodlari shifrlangan va API javoblarida qaytarilmaydi.
- Telegram xizmat xabarlari (777000, login kodlari) agent tomonidan hech qachon ishlanmaydi.
- `.env`, `*.session`, `*.db`, `tenants/`, `brain_vault/` — gitga yuklanmaydi.

---

## Testlar

```bash
python -m unittest tests.test_tenant_isolation tests.test_client_agent_handler tests.test_multi_user_subscription
```

Testlar vaqtinchalik bazada, MongoDB o'chiq holda ishlaydi (`tests/_isolated_env.py`) — haqiqiy ma'lumotlarga tegmaydi.

Ish rejasi va sessiyalar jurnali: [`SESSION.md`](SESSION.md).
