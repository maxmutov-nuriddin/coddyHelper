# 🧭 CoddyHelper — SESSION jurnali va ish rejasi

> **Har bir sessiya boshida:** shu faylni to'liq o'qing → "4. Reja" dagi birinchi bajarilmagan `[ ]` banddan davom eting → sessiya oxirida "6. Sessiyalar jurnali" ga yozing (deploydan oldin "5. Deploy eslatmalari"ni ham o'qing) va belgilarni yangilang.
>
> Belgilar: `[x]` bajarildi · `[~]` qisman / jarayonda · `[ ]` bajarilmagan · `⚠️` foydalanuvchi qarori kerak

---

## 0. Maqsad (foydalanuvchi so'zi bilan)

Loyihani **barcha obunachilar uchun o'rnatiladigan** qilish:
- har bir obunachining **o'z agenti** (o'z Telegram akkaunti / HSS session orqali ishlaydi);
- har birining **o'z ma'lumotlar bazasi** — boshqalarniki bilan **aralashmaydi**;
- **@mentor_cc (ID 8105823872)** — Super Admin, butun tizimning asosiy boshqaruv qismi.

---

## 1. Loyiha xaritasi (2026-09-26 holati, commit `5d3b24e`)

~37 000 qator. Python 3.14 + aiohttp + Telethon + aiogram, Groq/Gemini, SQLite + MongoDB Atlas, Render.com (free, 512 MB).

| Fayl | Qatorlar | Vazifasi |
|---|---|---|
| `main.py` | 346 | Kirish nuqtasi: web server, Telethon (mentor akkaunti), workerlar (eslatma 25s, backup 1 soat, tong brifingi, avtonom miya, keep-alive), bot, mijoz sessiyalarini ishga tushirish |
| `config.py` | 311 | `.env` → `Config`; `is_mentor`, Vazifalar guruhi (-5388159517) aniqlash |
| `web_app.py` | 2076 | Mini App backend: token auth, ~60 ta `/api/*` endpoint |
| `templates/admin_app.html` | 6420 | Mini App UI (tablar: dashboard, agent, clients, dossiers, knowledge, reminders, security, students) |
| `handlers/auto_reply.py` | 3366 | Mentor akkauntidagi kiruvchi xabarlar (Miya 1: quiet window, firewall, guruh filtri, eskalatsiya, Vazifalar guruhi) |
| `handlers/commands.py` | 1201 | Mentorning chiquvchi buyruqlari (`.ai`, `ai stop/start` ...) |
| `services/ai_service.py` | 3806 | Miya 3: Groq multi-key kaskad + Gemini, `generate_reply`, `_build_system_prompt` (mijoz personasi shu yerda), STT |
| `services/memory_service.py` | 4143 | SQLite qatlami (19 jadval) + obunalar (`user_subscriptions`) |
| `services/mongo_memory_service.py` | 1870 | MongoDB Atlas sinxron + `restore_to_sqlite` |
| `services/client_session_manager.py` | 242 | **Mijoz agentlari**: har obunachi uchun alohida Telethon client (HSS) |
| `services/bot_service.py` | 827 | aiogram bot @coddyassistanstbot: `/start`, `/grant`, `/revoke`, `/clients`, guruhga qo'shilganda onboarding + pin, backup |
| `services/profile_intelligence_service.py` | 1027 | Miya 5: dosye skaneri (GetCommonChats, yosh/rol taxmini) |
| `services/autonomous_brain_service.py` | 860 | Miya 5: avtonom sikl (leksikon, xatolar refleksiyasi, precomputed javoblar) |
| `services/telegram_agent_service.py` | 4367 | Agent amallari (xabar yuborish, qidirish, bot bilan ishlash, davomat) |
| `services/agent_runner.py`, `agent_tools.py` | 236+652 | ReAct agent sikli (Mini App AI chat) |
| `services/obsidian_brain_service.py` | 562 | `brain_vault/` .md fayllari bilan sinxron (gitignore'da) |
| boshqalar | — | reminder, morning, briefing, tts, speaker, mac_control, search, web_inspector, code_linter, code_sandbox, location, wellbeing |
| `scripts/` | — | Bir martalik patch/migratsiya skriptlari (ishlab chiqarishda ishlatilmaydi) |
| `tests/test_multi_user_subscription.py` | 254 | Obuna/token testlari |

**SQLite jadvallari:** messages, learned_memory, precomputed_answers (1602), user_dossiers (281), students (216), reminders, settings, mentor_lexicon, self_mistakes, saved_locations, daily_plans, ignored_users, user_quotas, active_inquiries, student_weaknesses, pedagogical_outcomes, high_yield_pedagogy, bot_interaction_patterns, user_subscriptions.

**Mongo kolleksiyalari:** `system_core.*` (user_subscriptions, global_settings, security_blacklist), `brain_frontline.*`, `brain_cognitive.*`, `brain_knowledge.precomputed_answers`, `brain_mentor.*`.

---

## 2. Multi-tenant arxitekturasi (Sessiya 2 dan keyingi holat)

```
                 ┌──────────── Super Admin (@mentor_cc, tenant 0) ────────────┐
                 │ coddy_memory.db + MongoDB asosiy kolleksiyalari (o'zgarmagan) │
                 └──────────────────────────────────────────────────────────────┘
 Mijoz A (tenant A)                     Mijoz B (tenant B)
 tenants/tenant_A.db  ──snapshot──►  MongoDB system_core.tenant_snapshots  ◄──snapshot── tenants/tenant_B.db
 O'z Telegram akkaunti (HSS)             O'z Telegram akkaunti (HSS)
```

| Qatlam | Fayl | Vazifa |
|---|---|---|
| Tenant konteksti | `services/tenant_context.py` | `ContextVar` — har so'rov/xabar qaysi tenant bazasida ishlashini belgilaydi (standart 0 = mentor, hech narsa buzilmaydi) |
| Baza marshruti | `services/memory_service.py` | `_get_connection()` tenant bo'yicha faylni tanlaydi; obunalar/tokenlar (`_core_op`, `admintoken_`, `tenant_status_`) doimo asosiy bazada |
| Bulut saqlash | `services/tenant_store.py` | Tenant bazasi o'zgarsa 45 soniyada MongoDB'ga gzip snapshot; restartda avtomatik tiklash |
| Mongo gating | `services/mongo_memory_service.py` | Tenant kontekstida `is_connected()` = False → mijoz ma'lumoti mentor kolleksiyalariga aralashmaydi |
| Lease | `services/instance_lease.py` | Mijoz sessiyalarini faqat BITTA server yuritadi (AUTH_KEY_DUPLICATED oldini oladi). `CLIENT_SESSIONS_MODE=auto/off/force` |
| Mijoz agenti | `services/client_session_manager.py` | connect+auth tekshiruvi, xato turlari, qayta ulanish, egasi buyruqlari (`ai ...`), begonalarga xavfsiz javob, debounce, egasi aralashsa jim turish, eslatmalar, obuna muddati nazorati |
| Login | `services/tg_login_service.py` | Mini App'da telefon → kod → 2FA orqali HSS avtomatik yaratish |
| Shifrlash | `services/secret_box.py` | HSS kodlari `enc:v1:` Fernet bilan shifrlanadi (eski ochiq qiymatlar ham ishlaydi) |
| Web himoya | `web_app.py` | Telegram initData HMAC tekshiruvi, `api_tenant_guard` middleware, Super Admin'ga xos endpointlar ro'yxati |

---

## 3. Topilgan muammolar va holati

### 🔴 Xavfsizlik
- [x] #1 `/api/auth` imzosiz `user`/`username` ga ishonardi → endi faqat imzolangan Telegram initData yoki yaroqli token
- [x] #2 Qattiq yozilgan `MASTER_ADMIN_TOKEN` (+ frontend fallback + lock ekran tugmasi) → olib tashlandi, faqat ixtiyoriy env
- [x] #3 Guruhga pin qilingan tugmalarda token → endi `t.me/bot?start=panel` (tokensiz); Vazifalar guruhiga havola yozilmaydi
- [x] #4 Mijoz tokeni bilan DB yuklab olish / mentor agentini ishlatish → middleware + `SUPER_ADMIN_ONLY_*`
- [ ] #5 ⚠️ MongoDB login/paroli `config.py` da — **foydalanuvchi Atlas parolini almashtirib, Render'ga `MONGODB_URI` qo'yishi kerak**, keyin default olib tashlanadi (hozir olib tashlansa, Render'da saqlash to'xtaydi)
- [x] #6 HSS kodlari shifrlanadi, API javoblarida qaytmaydi (`has_session` beriladi)
- [x] Yangi: `/app?token=` orqali reflected XSS → token belgilar filtri
- [x] Yangi: Telegram xizmat xabarlari (777000, login kodlar) agent tomonidan hech qachon ishlanmaydi

### 🔴 Mijoz agenti
- [x] #7 `ai_res.text` → mijoz agentlari umuman javob bermasdi
- [x] #8/#9 Persona tenant egasidan olinadi; tenant'da admin rejimi yo'q; CoddyCamp FAQ/"Nuriddin akaga yetkazdim"/Sokratik critic tenant'da o'chiq
- [x] #10 Tarix, kesh, rate-limit — tenant bo'yicha ajratilgan
- [x] #11 Filtrlar, `get_me` kesh, auto-reply/guruh rejimi, debounce, egasi aralashuvi
- [x] #12 Muddat nazorati: to'xtatish + 3 va 1 kun oldin ogohlantirish
- [x] Yangi: `client.start()` yaroqsiz sessiyada `input()` bilan butun serverni qotirardi → connect + is_user_authorized
- [x] Yangi: **"support ishlasa boshqalar chiqib ketadi"** — sabab: bir xil HSS ikki serverda (Render + lokal) bir vaqtda ulanib AUTH_KEY_DUPLICATED → lease bilan hal qilindi

### 🟠 "Saqlandi, lekin yo'qolib qoldi" sabablari
- [x] Mijoz bilimlari faqat SQLite'ga yozilardi → Render restartda o'chardi (endi tenant snapshot)
- [x] Mijoz qo'shgan eslatma `creator_id=mentor` bilan saqlanib, mijoz ro'yxatida ko'rinmasdi
- [x] Mijoz auto-reply toggle'i global `config` ni o'zgartirib, **mentor agentini ham o'chirardi**
- [x] HSS saqlash/start/stop tugmalari `Authorization` headersiz → doim 403
- [x] `get_setting` default qiymatni keshlardi
- [x] `precomputed_answers.owner_id` ustuni toza bazada yaratilmasdi → keshga yozish jim xato
- [x] `update_student`, lokatsiya/reja o'chirish, tarixni tozalash Mongo'ga yozilmasdi → restartdan keyin qaytib kelardi
- [x] `merge_database` (Telegram backup) mijoz bilimlarini `user_id` siz mentorga ko'chirardi va yangi tahrirlarni eski qiymat bilan bosardi
- [x] `migrate_from_sqlite` eskirgan lokal obuna/o'quvchi ma'lumotini bulutdagi yangisi ustidan yozardi (`$setOnInsert`)
- [x] Mijozning persona/format sozlamasi saqlanardi, lekin promptga qo'llanmasdi

### 🟠 Bot (Sessiya 3 da topilgan)
- [x] Obunachining bot orqali eslatmalari mentor bazasiga tushardi; `/bekor <ID>` bilan mentorning eslatmasini o'chira olardi → bot middleware'da `tenant_scope`
- [x] Botdagi `ai ...` ham `res.text` xatosi bilan ishlamasdi

### 🟡 Texnik qarz
- [x] `config.py` `Any` importi
- [x] Testlar endi vaqtinchalik bazada, Mongo o'chiq (`tests/_isolated_env.py`)
- [x] README yangilandi
- [x] `scripts/` → `scripts/legacy/` (README bilan)
- [~] Xotira: `MAX_CLIENT_SESSIONS` limiti (standart 12) + `/api/system/lease` da xotira ko'rsatkichi. Jonli yuklama sinovi hali qilinmagan
- [ ] Obunachi mentorning asosiy akkauntiga (support) yozganda mentor agenti javob beradi — kerak bo'lsa alohida "support" persona

---

## 4. Reja (bosqichma-bosqich)

### Bosqich A — Xavfsizlik
- [x] A1. initData HMAC-SHA256
- [x] A2. MASTER token olib tashlandi (ixtiyoriy `MASTER_ADMIN_TOKEN` env)
- [x] A3. Guruh tugmalari tokensiz
- [x] A4. `api_tenant_guard` + Super Admin ro'yxati
- [ ] A5. ⚠️ MongoDB parolini almashtirish (foydalanuvchi) → `MONGODB_URI` env → `config.py` default'ni olib tashlash
- [x] A6. HSS shifrlash (`SESSION_ENCRYPTION_KEY`)

### Bosqich B — Mijoz agenti
- [x] B1–B5 (bajarildi, §3 ga qarang)

### Bosqich C — Izolyatsiya
- [x] C0. Qaror: har mijozga alohida SQLite fayl + bulut snapshot (tavsiya etilgan variant b)
- [x] C1–C5

### Bosqich D — Har mijozga o'z "miyalari"
- [x] D1. AI aniq bilmasa ("aniqlab xabar beraman") — egasiga bot orqali savol va chat havolasi (10 daqiqada 1 marta, sozlanadi)
- [x] D2. Eslatmalar tenant bo'yicha, faqat egasiga (bot DM → zaxira: Saved Messages)
- [~] D3. Mijozlar uchun yengil CRM ("Kim yozdi": ism, username, xabarlar soni, oxirgi xabar). To'liq profil razvedkasi/avtonom miya mijozlarga ataylab yoqilmadi: har mijoz uchun katta AI token sarfi va Telegram flood xavfi — kelajakda pullik opsiya sifatida
- [x] D4. Mentor-only servislar Super Admin'da qoldi

### Bosqich E — Onboarding va biznes
- [x] E1. Mini App'da telefon + kod + 2FA orqali ulanish
- [x] E2. `/grant @username` (mentor clienti orqali ID aniqlanadi)
- [~] E3. Telegram Stars: `/buy` → invoice → to'lov → obuna avtomatik (idempotent). `SUBSCRIPTION_STARS_PRICE` env bilan yoqiladi (standart o'chiq). ⚠️ Narxni siz belgilaysiz. Click/Payme — merchant hisobi kerak, qilinmagan
- [x] E4. Ovozli xabarga ovozli javob (edge-tts, sozlanadi) + CRM ro'yxati
- [x] E5. Mijozlar tabida "🔍 Agent" — holat, akkaunt, xato, faoliyat jurnali, start/stop; server lease va xotira qatori

### Bosqich F — Sifat
- [x] F1. Izolyatsiya/xavfsizlik/handler testlari (42 ta, hammasi o'tadi)
- [x] F2. `Any` importi
- [x] F3. README
- [x] F4. `scripts/legacy/`
- [~] F5. Limit va monitoring qo'shildi; jonli yuklama sinovi deploydan keyin

---

## 5. Deploy bo'yicha MUHIM eslatmalar (Sessiya 2 o'zgarishlaridan keyin)

1. **Render env'ga qo'shing:** `SESSION_ENCRYPTION_KEY` (uzun tasodifiy satr; lokal `.env` da ham AYNAN shu qiymat). O'rnatilmasa kalit `api_hash+bot_token` dan hosil qilinadi.
2. **Lokal kompyuterda** `.env` ga `CLIENT_SESSIONS_MODE=off` qo'yish tavsiya etiladi — mentor lokal ishga tushirsa ham mijoz sessiyalariga tegmaydi (lease ham himoya qiladi, bu qo'shimcha kafolat).
3. Avval AUTH_KEY_DUPLICATED sabab bekor bo'lgan mijoz sessiyalari endi ishlamaydi → mijozlar Mini App → **🤖 Mening Agentim** orqali qayta ulanadi (raqam + kod).
4. Mentor: eski `?token=mentor_cc_master_...` havolalari endi ishlamaydi. Botda `/start` bosing (yangi tugma) yoki panelni bot menyusidan oching — Telegram initData orqali avtomatik kiradi.
5. `pip install -r requirements.txt` (`cryptography` qo'shildi).
6. Ixtiyoriy: `SUBSCRIPTION_STARS_PRICE` (masalan 500) — botda `/buy` orqali onlayn obuna; `MAX_CLIENT_SESSIONS`.

---

## 6. Sessiyalar jurnali

### Sessiya 1 — 2026-09-26
- **Bajarildi:** Loyiha to'liq o'rganildi. `SESSION.md` yaratildi. Kodga o'zgartirish kiritilmadi.
- **Topildi:** 21 ta muammo (auth bypass, mijoz tokeni bilan DB yuklab olish, `ai_res.text`, tenant personasi).

### Sessiya 2 — 2026-09-26
- **So'rov:** aralashmalar va buglarni tuzatish; har foydalanuvchiga HSS orqali o'z agenti va Telegramini to'liq boshqarish; begonalar uchun xavfsizlik; web app qulayligi; "saqlanmay qolish" va "support ishlasa boshqalar chiqib ketishi" muammolari; ishlayotgan narsani buzmaslik.
- **Bajarildi:** §2 arxitekturasi va §3 dagi barcha `[x]` bandlar. Yangi fayllar: `tenant_context`, `tenant_store`, `instance_lease`, `secret_box`, `notify`, `tg_login_service`, testlar. Mini App'ga "🤖 Mening Agentim" kartasi (ulanish, start/stop, sozlamalar, buyruq, biznes profili, faoliyat jurnali), Super Admin mijozlar ro'yxatida agent holati/xatosi.
- **Tekshirildi:** 40 ta unit/integratsion test (izolyatsiya, auth, middleware, handler xulqi), JS sintaksisi, barcha modullar importi, snapshot tiklash va lease simulyatsiyasi. Jonli Telegram/Render'da sinalmagan (kodlar, 2FA, haqiqiy HSS).
- **Qolgan:** A5 (Mongo parol), D1/D3, E2–E5, F3–F5.
- **Keyingi qadam:** deploy (§5) → jonli sinov: 1 ta test mijoz bilan ulanish, begona akkauntdan yozish, egasi `ai ...` buyrug'i, Render restartdan keyin ma'lumot saqlanishi.

### Sessiya 3 — 2026-09-26
- **So'rov:** qolgan rejani tugatish va push qilish.
- **Bajarildi:** bot middleware'da tenant izolyatsiyasi (eslatma aralashishi va `/bekor` orqali mentor eslatmasini o'chirish tuzatildi, `res.text` bug), `/grant @username`, Telegram Stars obuna (env bilan), AI bilmasa egasiga xabar, ovozli javob, mijoz CRM ("Kim yozdi"), support "🔍 Agent" inspektori va server holati, sessiyalar limiti, README, `scripts/legacy/`, `.env.example`.
- **Tekshirildi:** 42 test, JS sintaksisi, importlar, diff'da maxfiy ma'lumot yo'q.
- **Qolgan (foydalanuvchi qarori/harakati):** A5 Mongo parolini almashtirish; E3 Stars narxi / Click-Payme; D3 to'liq profil razvedkasi mijozlar uchun; jonli sinov (§5).

### Sessiya 4 — 2026-09-26
- **So'rov:** (1) mijoz app'ni ochganda avval admin navbar/ma'lumotlari chaqnab, keyin o'zinikiga o'tishi; (2) profil razvedkasi aniqligini 40% dan ≥90% ga ko'tarish.
- **Bajarildi:**
  - **Navbar bug:** super-admin tablari (dosyeler, o'quvchilar, xavfsizlik) endi standart holatda yashirin; header neytral ("Yuklanmoqda..."); auth+rol aniqlangunicha butun kontentni yopib turuvchi **boot overlay** qo'shildi (8s zaxira timeout). Mijozga endi admin ko'rinishi umuman chaqnamaydi.
  - **Profiler aniqligi:** signal yig'ish kuchaytirildi (40 shaxsiy + 30 guruh xabari, faqat shaxs o'z matnlari alohida; til aniqlash uz/ru/en); yosh regexi tuzatildi (noaniq 2-xonali "yil" olib tashlandi — endi faqat ochiq yosh e'loni, to'liq tug'ilgan yil yoki username-suffiks); rol belgilari KUCHLI/O'RTA/ZAIF darajali; AI endi **JSON + har maydon uchun ishonch foizi** qaytaradi va noaniqda "Aniq emas" deydi (taxmin qilmaydi); dosye kartasida 🟢/🟡/🔴 ishonch badge'lari va "N ta xabar asosida" izohi.
- **Tekshirildi:** 42 test, JS, kompilyatsiya; parse/render birlik sinovi.
- **Eslatma:** ishonch endi kalibrlangan — kam signalli shaxslar past foiz bilan "Aniq emas" deb belgilanadi (avval xato yuqori ishonch bilan chiqardi). Yuqori foizlar (🟢 80%+) faqat mustaqil signallar mos kelganda beriladi.

### Sessiya 5 — 2026-09-26
- **So'rov:** Support (Vazifalar/Boshqaruv) guruhiga bot Admin Panel tugmasini yuborib **pin** qilsin — ustoz shu yerdan appga kirgandek kira olsin.
- **Bajarildi:** `ensure_vazifalar_panel_pinned()` — bot startupda (8s dan keyin) Vazifalar guruhiga panel tugmasini yuboradi va pin qiladi. Idempotent: `vazifalar_panel_msg_id` sozlamasi + guruhning joriy pinned xabari tekshiriladi, allaqachon pin bo'lsa qayta yubormaydi (restartda spam yo'q); yangi yuborilsa eskisi o'chiriladi. Tugma `t.me/bot?start=panel` orqali botni ochadi → mentor "Admin Panelni Ochish" WebApp tugmasini bosib appga kiradi (initData imzosi bilan super admin sifatida). Guruhdagi begona a'zo bossa — ruxsat berilmaydi.
- **Eslatma:** bot Vazifalar guruhida a'zo/admin bo'lishi va xabar/pin huquqi bo'lishi kerak. Guruh inline tugmalarida WebApp tugmasi Telegram tomonidan ruxsat etilmagani uchun bot orqali o'tiladi (1 qo'shimcha teg). Bir tegishli to'g'ridan-to'g'ri kirish uchun mentor bot menyusidagi "📱 Admin Panel" tugmasidan ham foydalanishi mumkin.
- **Tekshirildi:** kompilyatsiya, import. Jonli guruhda pin qilish deploydan keyin ko'riladi.

### Sessiya 6 — 2026-09-26
- **So'rov:** (1) rasmda ko'rsatilgan "yozganlarimni noto'g'ri tushunib qoladi" — mentor Vazifalar guruhida "Barcha joylashuvlar lokatsiyasini ber" va "Ish ni lokatsiyaisni ber" deganda lokatsiya topilmadi xatosi; (2) Profil razvedkasi hali ham noto'g'ri (40%); (3) "Mijozlar qismi doyim renderda tozalanib ketmoqda"; (4) "eslatmalarda har renderda eslatma qoshilib qolmoqda".
- **Bajarildi:**
  1. **Lokatsiya tushunish** (`location_memory_service.py`, `memory_service.py`): "barcha/hammasi/barchasi" endi bitta joy nomi sifatida emas, **ro'yxat so'rovi** (`ALL_LOCATIONS_SENTINEL`) sifatida aniqlanadi — barcha saqlangan joylashuvlar (xarita pinlari + ro'yxat) qaytariladi. Ajratilgan nomdan imlo/qo'shimcha so'zlar ("ni", "uni") tozalanadi ("Ish ni" → "ish"). `get_saved_location` endi 3-bosqichli qidiruv: aniq moslik → ikki tomonlama ichma-ich moslik → `difflib` orqali imlo xatosiga chidamli (fuzzy) moslik ("ishh"→"Ish", "uyi"→"Uy").
  2. **Profil razvedkasi ishonchi**: AI JSON orqali qaytargan ishonch foizi endi **kod darajasida "yerga bog'lanadi"** (`_signal_ceiling`) — signal yo'q bo'lsa (KUCHLI/O'RTA/ZAIF belgisi topilmasa) AI qanchalik yuqori ishonch da'vo qilmasin, natija majburan "Aniq emas" + past foizga tushiriladi; signal kuchli bo'lsa yuqori ishonch saqlanadi. Bu AI'ning haddan tashqari o'ziga ishongan (lekin noto'g'ri) xulosalarini to'g'ridan-to'g'ri kamaytiradi — avvalgi tuzatish (JSON+prompt) faqat AI'ga "iltimos aniq bo'l" derdi, bu esa buni koddan MAJBURLAYDI.
  3. **"Mijozlar tozalanib ketishi" ildizi topildi**: foydalanuvchi Render'ga `MONGODB_URI` va `TELEGRAM_STRING_SESSION` ni tashqi tirnoqlar bilan (`MONGODB_URI="mongodb+srv://..."`) kiritgan bo'lishi mumkin — Render panели buni SHU KO'RINISHIDA (tirnoqlari bilan) saqlaydi, natijada `MongoClient` yaroqsiz manzil deb ulanmaydi va HECH NARSA bulutga saqlanmaydi → har restart (Render free = doimiy diskisiz) hammasini tozalaydi. `config.py` ga `_clean_env_value`/`_env` qo'shildi — barcha muhit o'zgaruvchilari endi tashqi tirnoqlardan avtomatik tozalanadi (log ogohlantirish bilan).
  4. **Eslatma dublikatsiyasi**: ikki qatlamli himoya qo'shildi — (a) `services/event_dedup.py`: Telethon qayta ulanganda ("catch-up") bir xil xabar ikkinchi marta "yangi xabar" sifatida kelishining oldini oluvchi global (chat_id, msg_id[, owner scope]) tekshiruvi, `handle_vazifalar_chat`/`on_mentor_message`/`handle_incoming_message` (auto_reply.py), `handle_user_command`/`handle_incoming_panel_command` (commands.py), mijoz agenti `_handle_incoming`/`_handle_outgoing` (client_session_manager.py) ga ulandi; (b) `add_reminder()` da DB darajasida: bir xil (chat, matn, vaqt) uchun hali yuborilmagan eslatma mavjud bo'lsa, ikkinchisi yaratilmaydi.
  5. **Yon-effekt sifatida topilgan xavfsizlik bugi tuzatildi**: `upsert_subscription` (masalan admin panelda mijoz nomini tahrirlashda) mijozning DESHIFRLANGAN (ochiq) HSS kodini qaytadan Mongo'ga yozib yuborardi (shifrlashni bekor qilib) — endi faqat kerakli maydonlar, qayta shifrlab yuboriladi.
- **Tekshirildi:** 60 ta test (yangi 18 tasi shu sessiyada qo'shildi: lokatsiya tushunish/fuzzy, ishonch kalibrlash, eslatma dedup, config tirnoq tozalash, event dedup), to'liq kompilyatsiya, JS sintaksis, import zanjiri.
- **Foydalanuvchidan kerak:** Render'dagi `MONGODB_URI` va `TELEGRAM_STRING_SESSION` qiymatlarini TIRNOQSIZ kiritilganini tekshiring (`mongodb+srv://...` — boshida/oxirida `"` bo'lmasin). Kod endi buni avtomatik tuzatadi, lekin asl sabab shu bo'lgan bo'lsa, muammoni butunlay bartaraf etish uchun Render panelida ham to'g'irlash tavsiya etiladi. Deploydan keyin: (a) bir necha lokatsiya so'rovini sinab ko'ring; (b) "♻️ Qayta tekshirish" bilan dosye ishonch foizlarini kuzating; (c) bir necha kun kuzatib, mijozlar/eslatmalar ro'yxati restartdan keyin ham saqlanib qolayotganini tasdiqlang.

### Sessiya 7 — 2026-09-26
- **So'rov:** kritik regressiya — "admin guruhlarni qoshdim ammo shu guruhga yozsam javob bermyopti, supportnikida ham boshqalarnikida ham vazifalar guruhim javob bermyopti va boshqa mijozlar ozini agenti blan boglanadigan guruhida ham javob yoq".
- **Topildi va tuzatildi (2 ta muammo):**
  1. **KRITIK REGRESSIYA (Sessiya 6 dan)**: `on_mentor_message` va `handle_incoming_message` `handle_vazifalar_chat(event)`ni chaqirishdan OLDIN `is_duplicate_event()` tekshiruvini bajarardi (kalitni "ko'rilgan" deb belgilab). `handle_vazifalar_chat` ICHIDA xuddi shu tekshiruv YANA bir marta bajarilardi — bu ikkinchi tekshiruv har doim `True` qaytarib, funksiya HECH NARSA qilmasdan darhol chiqib ketardi. Natija: mentorning Vazifalar guruhidagi HAR BIR xabari e'tiborsiz qoldirilardi. Tuzatish: ichki (ikkinchi) tekshiruv olib tashlandi — chaqiruvchilar allaqachon tekshiradi. Bu bug qaytmasligi uchun regressiya himoya testi qo'shildi (`handle_vazifalar_chat` manbasida `is_duplicate_event` yo'qligini tekshiradi).
  2. **Mijozning o'z boshqaruv guruhi oddiy mijozlar guruhi kabi ishlar edi**: Mini App'da biriktirilgan (`link_user_group`) shaxsiy boshqaruv guruhi standart "faqat @mention qilinganda javob berish" (`group_reply_mode=mention`) qoidasiga bo'ysunardi va `.eslatma`/`ai ...` buyruqlarini tanimasdi — mentorning Vazifalar guruhidan farqli o'laroq. Endi bu guruh **mentorning Vazifalar guruhi bilan bir xil mantiqda** ishlaydi: @mention shart emas (har doim javob beradi), va egasi u yerdan ham (Saved Messages'dagi kabi) `ai ...` orqali to'g'ridan-to'g'ri agentga buyruq bera oladi — ham bitta akkauntli (outgoing), ham alohida agent-akkauntli (incoming) sozlamalarda. Bog'liq bo'lmagan boshqa (mijozlar/customer) guruhlariga ta'sir qilmaydi.
- **Tekshirildi:** 65 ta test (5 tasi yangi: owner-group mention-gate bypass, owner-group buyruq — outgoing va incoming, boshqaruv guruhida oddiy gap AI'ni jim qilmasligi, bog'liq bo'lmagan guruhga ta'sir qilmasligi, + regressiya himoya testi), to'liq kompilyatsiya, import zanjiri.
- **Sabab tahlili:** ikkalasi ham Sessiya 6'dagi yangi xususiyatlarning ehtiyotsizligi — birinchisi aniq kodlash xatosi (bir xil tekshiruv ikki marta chaqiruv zanjirida), ikkinchisi loyihalash bo'shlig'i (yangi `group_reply_mode` standart qiymati mavjud "Vazifalar" konsepsiyasiga mos kelmasligi).

### Sessiya 8 — 2026-09-26
- **So'rov:** Sessiya 7 tuzatishidan keyin ham "haliham javob yo'q na vazifalar guruhida na boshqalarni agent blan muloqot guruhida".
- **Haqiqiy ildiz topildi (Sessiya 6/7 dagi dedup xususiyatining o'zida yashiringan 2-chi bug):** `services/event_dedup.py` global (chat_id, msg_id) ro'yxatidan **barcha** handlerlar birgalikda foydalanardi. Ammo Telethon bitta hodisaga mos **BARCHA** ro'yxatdan o'tgan handlerlarni chaqiradi (faqat bittasini emas)! Mentorning HAR bir chiquvchi xabari uchun ham `handlers/commands.py:handle_user_command`, ham `handlers/auto_reply.py:on_mentor_message` ishga tushadi (ikkalasi ham `events.NewMessage(outgoing=True)` uchun ro'yxatdan o'tgan). `register_command_handlers` birinchi chaqirilgani sababli, `handle_user_command` doim BIRINCHI ishlaydi va xabarni "ko'rilgan" deb umumiy ro'yxatga yozib qo'yadi; keyin `on_mentor_message` (aynan Vazifalar javobini beruvchi zanjir) o'zining tekshiruvida buni "takroriy" deb topib, HECH NARSA qilmasdan chiqib ketaveradi — Sessiya 7'dagi tuzatishdan keyin ham shu sabab javob kelmagan.
- **Tuzatish:** `is_duplicate_event()` endi majburiy `handler: str` parametrini talab qiladi — har bir mustaqil handler o'zining NOYOB nomi bilan chaqiradi, shuning uchun bitta handlerning tekshiruvi boshqasiga ta'sir qilmaydi. 6 ta chaqiruv joyi (`commands.handle_user_command`, `commands.handle_incoming_panel_command`, `auto_reply.on_mentor_message`, `auto_reply.handle_incoming_message`, `client.handle_outgoing`, `client.handle_incoming`) barchasi endi mustaqil.
- **Mijozlar guruhi bo'yicha:** `client_session_manager.py`da faqat 1 ta incoming va 1 ta outgoing handler bor (bunday kesishish yo'q edi) — Sessiya 7'dagi "boshqaruv guruhi @mention'siz ishlasin" tuzatishi kod darajasida to'g'ri ko'rinadi. Agar hali ham ishlamasa, ehtimoliy sabablar: (a) mijozning shaxsiy agent akkaunti guruhga umuman a'zo emas, (b) Mini App'da guruh ID noto'g'ri/eski formatda saqlangan, (c) mijoz agenti "ishlamayapti" holatida. Foydalanuvchidan Mini App'dagi "🤖 Mening Agentim" holatini va guruh ID sini tekshirish so'raldi.
- **Tekshirildi:** 66 ta test (2 tasi yangi: `test_different_handlers_are_independent` — aynan shu bug klassini ushlaydigan regressiya testi), to'liq kompilyatsiya, import zanjiri.

### Sessiya 9 — 2026-09-26
- **So'rov:** Vazifalar guruhi endi ishlayapti (Sessiya 8 tuzatildi), ammo "boshqalarda guruh ulandi ammo javob yoq telegramga ulangan agent nega" — mijozlarning guruhi.
- **Haqiqiy ildiz (kod bugi emas, arxitektura/UX bo'shlig'i):** Mijoz odatda @coddyassistanstbot (aiogram bot) ni guruhga admin qilib qo'shadi → bot buni avtomatik aniqlab, `group_id`ni obunaga biriktiradi ("guruh ulandi" deb ko'rinadi). AMMO xabarlarga AI javobini beradigan narsa — mijozning O'Z shaxsiy Telegram akkaunti (Mini App orqali telefon+kod bilan ulangan "agent") — bu botdan BUTUNLAY BOSHQA Telegram hisobi! Agar mijozning shaxsiy (ulangan) akkaunti o'sha guruhga a'zo bo'lmasa, uning `client_session_manager.py` Telethon sessiyasi bu guruhdan HECH QANDAY xabar ko'rmaydi — shuning uchun "guruh ulandi" holatida ham javob kelmaydi.
- **Nega avtomatik ulash (bot qo'shilganda) qilinmadi/qilib bo'lmaydi:** Agentning o'zi (mijozning shaxsiy akkaunti) biror guruhga QO'SHILGANDA avtomatik ulashni ko'rib chiqdim, lekin bu XAVFLI: mijozning shaxsiy akkaunti allaqachon o'nlab shaxsiy/oilaviy/tasodifiy guruhlarga a'zo bo'lishi mumkin — ularning BIRORTASINI ham "boshqaruv guruhi" deb avtomatik belgilab qo'yish noto'g'ri (maxfiylik va kutilmagan xatti-harakat xavfi).
- **Tuzatish (xavfsiz, aniq, foydalanuvchi tomonidan boshqariladigan):** Yangi buyruq — mijoz o'zining ULANGAN shaxsiy akkaunti bilan istalgan guruhda (bitta akkauntli sozlamada — outgoing, yoki agent alohida akkauntda bo'lsa — incoming) `ai ulash` (yoki "guruhni ulash", "biriktir" va sh.k.) deb yozsa, O'SHA ANIQ guruh darhol "boshqaruv guruhi" sifatida biriktiriladi va @mention'siz ishlay boshlaydi. Bu 100% xavfsiz (faqat egasining o'zi, faqat aniq shu guruhda, faqat ongli buyruq bilan) va bir martalik sozlash.
- **Xabarlar yangilandi:** bot `/start` ko'rsatmasi, bot guruhga qo'shilganda chiqadigan xabar, va Mini App'dagi "Boshqaruv guruhi" widgeti + "🤖 Mening Agentim" karti — barchasi endi `ai ulash` usulini asosiy va tavsiya etiladigan yo'l sifatida ko'rsatadi, "botni qo'shish yetarli" degan noto'g'ri taassurotni bermaydi.
- **Tekshirildi:** 68 ta test (2 tasi yangi: `ai ulash` orqali ulash ishlashi + tasodifiy guruh a'zoligi o'zi ulanib qolmasligi), kompilyatsiya, JS, import zanjiri.
- **Foydalanuvchiga ko'rsatma:** mijozga ayting — Mini App'da "🤖 Mening Agentim" orqali akkauntini ulasin, o'sha AKKAUNT bilan (bot bilan emas) o'z guruhiga kirsin va guruhda `ai ulash` deb yozsin.

### Sessiya 10 — 2026-09-26
- **So'rov:** rasmda tasdiqlangan — `ai ulash` ULASH ISHLADI ("✅ Ushbu guruh sizning boshqaruv guruhingiz..."), lekin shundan keyin oddiy "Salom" deb yozganda javob kelmadi. Foydalanuvchi kutgan narsa: "har bir odamning guruhi bo'ladi — agent bilan gaplashadigan, boshqaradigan, vazifa beradigan" — ya'ni mentorning Vazifalar guruhi tajribasi.
- **Topildi:** boshqaruv guruhida faqat `ai <buyruq>` (prefiksli) xabarlar `run_owner_command`ga yuborilardi; prefikssiz oddiy gap ("Salom") uchun ATAYLAB hech narsa qilinmasdi (izoh: "AI'ni jim holatga o'tkazmaymiz" — lekin javob ham berilmasdi). Bu Vazifalar guruhidan farq qilardi: u yerda mentorning HAR QANDAY xabari (prefikssiz) to'liq AI Co-Pilot javobini oladi.
- **Tuzatildi:** boshqaruv guruhida endi ham `_handle_outgoing`, ham `_handle_incoming` — prefiks bo'lmasa xabarning O'ZINI (`command_for_link or text`) to'g'ridan-to'g'ri `run_owner_command`ga yuboradi. Natija: mijozning boshqaruv guruhi endi mentorning Vazifalar guruhi bilan 100% bir xil tajriba — istalgan tabiiy xabar to'liq AI/agent javobini oladi, alohida buyruq sintaksisi shart emas.
- **Qo'shimcha:** foydalanuvchi ulash tasdiq xabaridagi "@mention" so'zini tushunmagani sababli ("@mention kim?"), barcha foydalanuvchiga ko'rinadigan matnlardan (tasdiq xabari, bot onboarding, Mini App) texnik "@mention" atamasi olib tashlandi, oddiy tilga o'girildi ("botni chaqirmasdan ham javob beradi").
- **Tekshirildi:** 69 ta test (2 tasi yangi: prefikssiz xabar to'liq javob olishi — outgoing va incoming yo'llarida), kompilyatsiya, JS, import zanjiri.

### Sessiya 11 — 2026-09-26
- **So'rov:** guruh ulanganda ("ai ulash") agent shu odamni bilib olish uchun savollar berishi kerak (tanishuv/onboarding), va "ai ulash" faqat 1 marta ishlashi, qayta qilinsa "allaqachon ulangan" deyishi kerak.
- **Bajarildi:**
  1. **Tanishuv savolnomasi (`ONBOARDING_QUESTIONS`, 7 ta savol):** guruh birinchi marta ulanganda agent ketma-ket so'raydi — biznes nomi, sohasi, mahsulot/xizmatlar va narxlar, ish vaqti/manzil, mijozlar ko'p so'raydigan savollar, xohlagan muloqot ohangi, qo'shimcha qoidalar (ixtiyoriy). Har bir javob navbat bilan qabul qilinadi (`_handle_onboarding_answer`), holat tenant-scoped `onboarding_state` sozlamasida saqlanadi (restartga chidamli — tenant bazasi bilan birga saqlanadi).
  2. **Yakuniy sintez (`_finish_onboarding`):** barcha javoblar AI orqali (imlo/uslub xatolari tuzatilib, tartibli) bitta "BIZNES QOIDALARI VA MA'LUMOTLARI" qo'llanmasiga aylantiriladi va `upsert_subscription(system_prompt=..., business_name=..., profession=..., is_edit=True)` orqali saqlanadi — shu bilan `_build_system_prompt` uni darhol ishlata boshlaydi. Ohang javobidan (`tone`) `ai_persona_<uid>` ham avtomatik moslanadi.
  3. **`ai ulash` endi idempotent:** agar guruh ALLAQACHON o'sha mijozning boshqaruv guruhi bo'lsa, qayta "ulash" deyilganda faqat "ℹ️ Bu guruh allaqachon... ulangan" deb javob beradi — qayta ulanmaydi va savolnoma qayta boshlanmaydi. Ham `_handle_outgoing` (bitta akkauntli), ham `_handle_incoming` (alohida agent akkaunti) yo'llarida.
  4. Onboarding jarayoni davomida BEGONA odam yozsa (savolnoma tugamagan bo'lsa ham), bu oddiy AI javobi sifatida ko'rib chiqiladi — faqat egasining o'zi bergan javoblari savolnoma uchun hisoblanadi.
- **Tekshirildi:** 71 ta test (3 tasi yangi: to'liq savolnoma oqimi va ma'lumot saqlanishi, begona odam onboarding javobi sifatida hisoblanmasligi, qayta "ulash" idempotentligi), kompilyatsiya, JS, import zanjiri. Testlarda AI sintez bosqichi tarmoqqa chiqmasligi uchun Groq pool bo'sh qilib mock qilindi (deterministik, tezkor test).

### Sessiya 12 — 2026-09-26
- **So'rov:** (1) onboarding javoblaridan kelib chiqib AI to'g'ri javob berishi va shu asosda BOSHQALARNING (mijozlarning) so'rovlariga chegara qo'yishi kerakmi — tasdiqlash/kuchaytirish so'raldi; (2) "aniqlab xabar beraman" degan javobdan keyin xabar egasining boshqaruv guruhiga tushmayapti — tushishi kerak.
- **Topilgan bo'shliqlar va tuzatildi:**
  1. **Mavzu chegaralari onboardingdan avtomatik qo'yilmasdi**: `_build_system_prompt`dagi "XIZMAT KO'RSATISH MAVZULARI VA QAT'IY CHEGARALARI" bloki faqat mijoz Mini App'da qo'lda `curriculum_topics` kiritgan bo'lsa ishga tushardi; tanishuv savolnomasi bu maydonni umuman to'ldirmasdi. Endi `_finish_onboarding` "mahsulot/xizmatlar" javobidan (AI orqali, yoki AI mavjud bo'lmasa oddiy bo'lish bilan taxminiy) mavzular ro'yxatini chiqarib, `set_curriculum_topics()` orqali avtomatik saqlaydi — shu bilan chegara qoidasi darhol faollashadi.
  2. **Zaxira chegara qoidasi**: `curriculum_topics` bo'sh bo'lib qolsa ham (masalan AI mavzu chiqara olmasa), lekin `custom_prompt` (biznes qoidalari) mavjud bo'lsa, endi umumiy "Faqat yuqoridagi biznes yo'riqnomasi va sohangizga bevosita aloqador savollarga javob bering..." qoidasi qo'shiladi — hech qachon chegarasiz qolmaydi.
  3. **Eskalatsiya endi boshqaruv guruhiga ham yetadi**: `_escalate_to_owner` avval FAQAT bot orqali shaxsiy DM yuborardi (`notify_user`) — agar mijoz botning shaxsiy chatini ochmagan/ko'rmagan bo'lsa, bu ko'rinmay qolardi va "yetkazdim" degan AI da'vosi amalda hech qayerga tushmagandek tuyulardi. Endi eng avvalo mijozning ULANGAN boshqaruv guruhiga (agar bo'lsa) AI o'zining Telethon clienti orqali to'g'ridan-to'g'ri yozadi (xuddi mentorning Vazifalar guruhidagi eskalatsiya kabi); guruh ulanmagan bo'lsagina, zaxira sifatida bot DM ga o'tadi.
- **Tekshirildi:** 73 ta test (2 tasi yangi: mavzular chiqarilishi + chegara qoidasi promptda paydo bo'lishi, eskalatsiya guruhga yozilishi va DM zaxirasi shart emasligi), to'liq kompilyatsiya, JS, import zanjiri. Test izolyatsiyasidagi eski bug ham tuzatildi (`asyncSetUp` endi har test boshida `group_id`ni aniq tozalaydi — oldingi testda ulangan guruh keyingisiga "sizib o'tmasligi" uchun).

### Sessiya 13 — 2026-09-26 — To'liq loyiha auditi
- **So'rov:** "loyihani toliq korib chiq va bardakligini tekshir ... menga ayt logikalarni buzib qoyma ehtiyotkor bol" — to'liq audit, faqat aniq/xavfsiz narsalarni tuzatish, qolganini xabar qilish.
- **Auditda topilgan va DARHOL tuzatilgan (haqiqiy, tasdiqlangan buglar):**
  1. **🔴 KRITIK — jonli mijozga ta'sir qilishi mumkin edi**: onboarding savolnomasi (Sessiya 11) egasi javob berishni to'xtatib qo'ysa (masalan chalg'ib ketsa) **ABADIY "osilib qolar edi"** — hech qanday muddat yoki bekor qilish buyrug'i yo'q edi, shuning uchun HAR BIR keyingi xabar (hatto haqiqiy mijoz savoli bo'lsa ham) noto'g'ri ravishda savolnoma javobi deb talqin qilinaverardi. Buni jonli bazadan tekshirganda, mavjud yagona haqiqiy mijoz yozuvida `business_name` bo'sh ekanligi aniqlandi — bu aynan shu holatga tushib qolgan bo'lishi mumkinligini ko'rsatadi. **Tuzatildi**: (a) 30 daqiqa javobsizlikdan keyin holat avtomatik bekor bo'ladi; (b) egasi istalgan payt "bekor qil"/"to'xtat"/"stop" deb yozib chiqib keta oladi.
  2. **Env o'zgaruvchilarida tirnoq-tozalash nomukammal edi**: Sessiya 9 da `MONGODB_URI`/`TELEGRAM_STRING_SESSION` uchun `_clean_env_value()` qo'shilgan edi, lekin keyingi sessiyalarda qo'shilgan `SUBSCRIPTION_STARS_PRICE`, `SUBSCRIPTION_DAYS`, `MAX_CLIENT_SESSIONS` (bular `int()` ga o'tkazilgani uchun tirnoqli qiymat butun dasturni ISHGA TUSHMASDAN QULATIB YUBORISHI mumkin edi!), `CLIENT_SESSIONS_MODE`, `SESSION_ENCRYPTION_KEY` (tirnoq o'zgarsa shifrlash kaliti "sezilmasdan" o'zgarib, eski sessiyalar ochilmay qolardi), `MASTER_ADMIN_TOKEN` — bularning hech biri bu himoyadan foydalanmasdi. **Tuzatildi**: barchasi endi `_clean_env_value()` orqali o'tadi (funksional o'zgarish yo'q, faqat tirnoqli holatni to'g'rilaydi). Ushbu tuzatish davomida o'zim yo'l qo'ygan xato (`web_app.py`da `config._clean_env_value` — `config` bu yerda MODUL emas, `Config` obyekti, shuning uchun `AttributeError` bilan qulagan bo'lardi) darhol import-test orqali topilib, to'g'irlandi.
- **Tekshirildi:** 75 ta test (2 tasi yangi: onboarding bekor qilish va muddati tugashi), to'liq kompilyatsiya, JS, import zanjiri, va har bir tuzatilgan env-o'qish nuqtasi tirnoqli qiymat bilan qo'lda funksional sinovdan o'tkazildi.
- **Auditda topilgan, LEKIN TUZATILMAGAN (foydalanuvchiga xabar qilindi, qaror kutilmoqda):**
  - Repo tuzukligi: `bot.py` (ROOT) — `services/bot_service.py`dan MUSTAQIL, ESKI/O'LIK aiogram bot nusxasi (hech yerda import qilinmaydi, lekin tasodifan `python bot.py` ishga tushirilsa, xuddi shu `BOT_TOKEN` bilan Telegram API konfliktiga (`getUpdates` conflict) sabab bo'lishi mumkin).
  - 13 ta diagramma-generatsiya fayli repo ildizida (`*mermaid*`, `*miya_sxemasi*`, `generate_flowchart_image.py`, `render_toliq_miya_sxemasi.py` va h.k.) — dastur ishlashiga aloqasi yo'q, faqat vizual sxema yaratish uchun bir martalik skriptlar/natijalar.
  - `coddy_session.session` — ishlatilmaydigan, orqada qolgan sessiya fayli (`config.session_name = "coddy_helper_session"`dan farqli nom).
  - `database.db` (0 bayt, o'lik) va `parent_prompt.md` (`PARENT_SYSTEM_PROMPT` rejalashtirilgan, lekin hech qachon `prompts.py`ga qo'shilmagan — hozirgi `SYSTEM_PROMPT` ichida ota-onalar bilan muloqot qoidalari allaqachon bor, shuning uchun bu fayl ehtimol eskirgan).
  - Bazada (`settings` jadvali) 124 ta `admintoken_` yozuvi to'plangan — muddati o'tgan tokenlar hech qachon o'chirilmaydi (funksional xato emas, lekin vaqt o'tishi bilan cheksiz o'sadigan chiqindi; tozalash worker qo'shish mumkin).
  - Bazada eski (2026-09-12 sanali, Sessiya 6-8 dagi dedup tuzatishlaridan OLDINGI) takrorlangan eslatmalar bor, jumladan **hali ham "yuborilmagan" (`is_sent=0`) va muddati allaqachon o'tgan "Katta imtihon" (2026-09-25 15:00) eslatmasi 2 nusxada** — bular keyingi safar reminder worker ishga tushganda mentorga IKKI MARTA yuborilishi mumkin. Ma'lumot o'chirish/o'zgartirish bo'lgani uchun avval tasdiqlash so'raldi, hech narsa o'chirilmadi.

### Sessiya 14 — 2026-09-26 — Audit topilmalarini tuzatish
- **So'rov:** "to'g'irlab ber" — oldingi auditda ro'yxat qilingan barcha "bardaklik" narsalarni tuzatish.
- **Bajarildi (barchasi xavfsiz, ma'lumot yo'qotmasdan):**
  1. **`bot.py`** (ildizdagi eski, mustaqil bot nusxasi) → `scripts/legacy/bot_py_old_standalone_DEPRECATED.py` ga ko'chirildi, aniq ogohlantirish yozildi (ishga tushirilmasin — BOT_TOKEN konflikti).
  2. **13 ta diagramma fayli** (mermaid/miya_sxemasi/generate_flowchart va h.k.) → yangi **`diagrams/`** papkaga ko'chirildi, `diagrams/README.md` qo'shildi.
  3. **`parent_prompt.md`** (amalga oshirilmagan qoralama) → **`docs/parent_prompt_DRAFT_not_implemented.md`**ga ko'chirildi, izoh bilan (`docs/README.md`).
  4. **`coddy_session.session`** (ishlatilmaydigan) va **`database.db`** (0 bayt) — mahalliy, gitignore qilingan, hech yerda ishlatilmagan fayllar sifatida tasdiqlangach o'chirildi.
  5. **Eskirgan admin-tokenlarni tozalash mexanizmi qo'shildi**: `memory_service.delete_setting`/`delete_settings_by_prefix` (yangi), `web_app.verify_admin_token` endi muddati o'tgan tokenni topganda darhol o'chiradi, `web_app.cleanup_expired_tokens()` esa server har ishga tushganda (`setup_web_app_routes`) butun bazani bir marta tozalaydi. Joriy bazada sinovdan o'tkazildi: 124 tadan **29 tasi muddati o'tgan** ekan — tozalandi, 95 tasi hali amal qiladi.
  6. **Bazadagi takrorlangan eslatmalar tozalandi** (faqat `is_sent=1` deb belgilandi, o'chirilmadi — qaytarib bo'ladi): jami 22 ta ortiqcha nusxa (asosan Sep 14 sinov "uyg'otish" eslatmalari + "Katta imtihon" ikkinchi nusxasi). Amaliyotdan oldin `/tmp/coddy_memory_backup_before_cleanup.db` ga zaxira olindi va tozalashdan keyin `diff` orqali BOSHQA hech qanday ma'lumot o'zgarmaganligi (faqat `is_sent` ustuni) tasdiqlandi.
- **Tekshirildi:** to'liq kompilyatsiya, JS, import zanjiri, 75 ta test (barchasi o'tdi, fayllarni ko'chirish hech narsani buzmadi), token tozalash funksiyasi va eslatma deduplikatsiyasi jonli bazada qo'lda tasdiqlandi.

### Sessiya 15 — 2026-09-26
- **So'rov:** "chatga kimdir yozsa agent menga yetqazib berdim deyapti ammo admin gruhiga jonaymyopti" — AI "yetkazdim" deydi, lekin haqiqatda boshqaruv guruhiga hech narsa yuborilmaydi.
- **Ildiz sababi topildi:** Sessiya 12'da qo'shilgan guruhga-eskalatsiya funksiyasi to'g'ri ishlagan, lekin uni CHAQIRISH mexanizmi ishonchsiz edi — `UNSURE_ANSWER_RE` faqat juda tor, qat'iy iboralarni ("aniqlab ... xabar beraman") tanirdi. AI (LLM sifatida) har safar boshqacha so'z bilan gapiradi ("egamga yetkazdim", "ma'muriyatga xabar berdim" va h.k.) — bu iboralarning aksariyati regex bilan MUTLAQO mos kelmaydi, shuning uchun eskalatsiya funksiyasi umuman CHAQIRILMAGAN, garchi guruhga yozish kodi to'g'ri bo'lsa ham. Bundan tashqari, mentor tizimida (`prompts.py`) allaqachon ISHONCHLI, tuzilmali `<<<ESCALATE>>>...<<<END_ESCALATE>>>` belgi mexanizmi bor edi (`ai_service.py`da qayta ishlanadi, `AIResult.escalation` orqali qaytariladi) — lekin (a) mijoz (tenant) persona prompti bu belgini ISHLATISHNI umuman o'rgatmagan, va (b) `client_session_manager.py` `AIResult.escalation` atributini umuman O'QIMAGAN (faqat matnni `str()`ga aylantirib, regex bilan tekshirgan).
- **Tuzatildi:** (1) Mijoz (tenant) system promptiga mentor bilan bir xil ishonchli `<<<ESCALATE>>>` belgi ko'rsatmasi qo'shildi ("aniq javob berolmasangiz, javobingiz oxiriga MUTLAQO shu belgini qo'shing"); (2) `client_session_manager.py` endi avval `AIResult.escalation` atributini (ishonchli, tuzilmali signal) tekshiradi, faqat u bo'lmasa eski regex'ga zaxira sifatida murojaat qiladi. Bu AI qanday so'z bilan "yetkazdim" desa ham ishonchli ishlaydi.
- **Tekshirildi:** 76 ta test (1 tasi yangi — aynan eski regex USHLAMAYDIGAN so'z bilan ham eskalatsiya guruhga to'g'ri yetishini, va aniq "Savol: ..." matnini tasdiqlaydi), to'liq kompilyatsiya, JS, import zanjiri.
