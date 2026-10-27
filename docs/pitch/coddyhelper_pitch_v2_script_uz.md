# CoddyHelper — Demo Day pitchi (v2)

Format: 3:00 pitch → 1:00 savol → 1:00 jury fikri. Slaydlar: `coddyhelper_pitch_v2.html`
(→ / probel — keyingi, N — izohlar, T — taymer, F — to‘liq ekran, PDF uchun — Chop etish).

## Raqamlar manbasi

`coddy_memory.db`, 12–25 sentabr 2026 (14 kun). Egasining o‘z chati (`chat_id = 8105823872`) hisobga olinmagan.

| Ko‘rsatkich | Qiymat | SQL mantig‘i |
|---|---|---|
| Kiruvchi xabarlar | 259 (~18/kun) | `role='user'` |
| Yordamchi javoblari | 239 | `role='model'` |
| Chatlar | 38 (31 shaxsiy + 7 guruh) | `distinct chat_id`, manfiy = guruh |
| Kod savollari va loyiha havolalari | ~60 | kalit so‘zlar bo‘yicha (python/html/css/xato/kod; netlify/figma/github/wix) |

Cheklovlar: bu lokal nusxa. Sahnaga chiqishdan oldin prod MongoDB bilan solishtiring. Javoblarning to‘g‘riligi o‘lchanmagan. Mijozlar soni ham tekshirilmagan: lokal bazada 1 ta obuna bor.

## So‘zma-so‘z matn (~390 so‘z, 3:00)

**0:00–0:30 · Muammo**
Men CoddyCamp’da mentorman. Sentabrda bir kunda Telegramimga shunday xabarlar keldi: «IndexError nima degani?», «HTML bilan CSS qanday ulanadi?», loyiha havolasi, «Assalomu alaykum, ustoz». Men esa o‘sha paytda boshqa guruhda dars o‘tyapman. Javob kechiksa, o‘quvchi uyga vazifada to‘xtab qoladi. Darsda telefonga qarasam, oldimdagi guruh to‘xtaydi. Bu meni qiynagan muammo, shuning uchun uni o‘zim uchun yecha boshladim.

**0:30–0:55 · Yechim va muqobillar**
Biz buni CoddyHelper bilan yechamiz. U sizning Telegram akkauntingizda ishlaydigan AI yordamchi. O‘quvchi botga emas, ustozning o‘ziga yozadi, javob esa siz kiritgan bilim asosida keladi. Qaror kerak bo‘lgan savolni yordamchi boshqaruv guruhingizga yuboradi. O‘zingiz yozsangiz, u jim turadi. Bugun bu ishni qo‘lda yoki Telegram Business shablonlari bilan qilish mumkin. Lekin shablon savolni tushunmaydi. Alohida botga esa o‘quvchilar baribir yozmaydi.

**0:55–1:15 · Dalil**
Bu g‘oya emas, ishlaydigan mahsulot. Men uni 14 kun o‘z akkauntimda ishlatdim. 38 ta chatdan 259 ta xabar keldi, kuniga taxminan 18 ta. Ulardan 239 tasiga yordamchi javob berdi, men qo‘lda yozmadim. Taxminan 60 tasi kod savoli va loyiha havolasi edi. Halol aytaman: javoblarning qanchasi to‘g‘ri bo‘lganini hali alohida tekshirmadim.

**1:15–1:35 · Metrikalar va gipotezalar**
Asosiy metrika — haftasiga ustoz tuzatmagan avtomatik javoblar soni. Jalb qilishda taklif qilingan mentorlardan nechtasi 7 kunda birinchi foydali javobni olishini o‘lchaymiz. Ushlab qolishda ikkinchi haftada ham foydalanayotganlarni sanaymiz. Savollar oqimi haqiqatan katta ekanini tekshirib bo‘ldik. Pilotda yana uchta narsani tekshiramiz: javoblarning kamida 90 foizi to‘g‘rimi, vaqt kamida 30 foiz tejaladimi va kamida ikki mentor pul to‘lab davom etadimi.

**1:35–1:50 · Biznes-model**
Model — oylik obuna. Mentor yoki o‘quv markazi egasi to‘laydi. Pro tarifi oyiga 99 ming so‘m, Ultra 179 ming. Mentor kuniga o‘nlab xabarni qo‘lda yozmaslik uchun to‘laydi. Bu narxga tayyorlikni pilot oxirida haqiqiy to‘lov bilan tekshiramiz.

**1:50–2:40 · Demo**
Hozir bitta yo‘lni ko‘rsataman. *[Sinov akkauntidan yozing: «HTML bilan CSS qanday ulanadi?»]* Ko‘ryapsizmi, javob mening nomimdan keldi, telefonimga tegmadim. *[Ikkinchi xabar: «Ertangi dars bo‘ladimi?»]* Yordamchi buni bilmaydi va javobni o‘ylab topmaydi: savol boshqaruv guruhimga keldi. *[Guruhni ko‘rsating.]* Oddiy savol hal bo‘ldi, qaror kerak bo‘lgani esa menga yetdi.

**2:40–3:00 · CTA**
Shu xonada Telegramdan savol oladigan mentorlar bor. Menga beshtangiz kerak: ikki hafta, bepul. Siz 10 daqiqada ulaysiz va eng ko‘p keladigan beshta savolingizni berasiz. Men har hafta hisobot beraman: nechta savol hal bo‘ldi, nechtasi sizga yetdi, nechtasi xato bo‘ldi. Ikki haftadan keyin foyda bo‘lsa, Pro’ga o‘tasiz, bo‘lmasa o‘chirasiz. Bugun menga Telegramda «pilot» deb yozing.

## Demo tayyorgarligi

1. Ikkinchi telefon yoki sinov akkaunti mentor akkauntiga yozishi kerak (egasining o‘z chatidan emas).
2. Bilimlar bazasida ertangi dars jadvali **bo‘lmasin**, aks holda eskalatsiya ishlamaydi.
3. Avtomatik javob yoqilgan va boshqaruv guruhi ulangan bo‘lsin. Demo chatiga 5 daqiqa ichida o‘zingiz yozmang: pauza ishlab qoladi.
4. Sahnadan oldin bu yo‘lni 3 marta bajaring. Javob vaqtini va har ikki natijani yozib oling.
5. Zaxira: shu yo‘lning 40 soniyalik ekran videosi. Javob 10 soniyada kelmasa, darhol videoga o‘ting.

## Savol-javob (formula: bilamiz → bilmaymiz → qanday tekshiramiz)

**Muammo haqiqiy ekanini qayerdan bilasiz?**
— 14 kunda o‘z akkauntimga 259 ta xabar keldi, bu bazada qayd etilgan. Boshqa mentorlarda ham shundaymi, hali bilmaymiz. Pilotdagi 5 mentorda buni o‘lchaymiz.

**AI noto‘g‘ri javob bersa-chi?**
— Yordamchi faqat kiritilgan bilim doirasida javob beradi va bilmaganini ustozga yuboradi. Siz yozsangiz, to‘xtaydi. Xato umuman bo‘lmaydi deb aytmayman. Shuning uchun pilotda har bir javobni mentor tekshiradi va xatolar ulushini hisobotga kiritamiz.

**Nega ChatGPT yoki oddiy bot emas?**
— ChatGPT’dan javobni baribir mentorning o‘zi ko‘chirib yuboradi. Botga esa o‘quvchilar yozmaydi, ular ustozga yozadi. CoddyHelper aynan o‘quvchi yozgan chatda javob beradi.

**Akkauntim xavfsizmi? Telegram bloklamaydimi?**
— Ulanish Telegram’ning rasmiy API’si orqali ishlaydi, sessiya kodi shifrlanadi, har bir mijozning bazasi alohida. Bloklanish xavfi nolga teng, deb kafolat bera olmayman. Shu sababli pilot kichik hajmda o‘tadi.

**Daromad bormi?**
— Hozircha tasdiqlangan daromad yo‘q. Tariflar mahsulotda sozlangan. Pilot oxirida pullik davom ettirishni taklif qilamiz: 5 mentordan kamida 2 tasi to‘lasa, buni signal deb hisoblaymiz.

## Oldingi versiya (PDF) bilan farqi

| Urok 6 talabi | PDF | v2 |
|---|---|---|
| Real epizod | To‘qilgan sahna («kurs narxi qancha?») | Akkauntga kelgan haqiqiy xabarlar |
| Nima uchun sizni qiziqtiradi | Yo‘q | Muallifning o‘zi mentor |
| Muammo ko‘lami | «O‘lchanmagan» | 14 kunda 259 xabar, 38 chat |
| Muqobillar | Faqat «qo‘lda yozish» | Qo‘lda, Telegram Business, alohida bot |
| Metrikalar: qiymat, davr, manba | Faqat ta’riflar | Bor qiymatlar + pilotdagi o‘lchov |
| Tekshirilgan va tekshiriladigan gipoteza | Ajratilmagan | Ikki ustun, aniq mezonlar bilan |
| Demo | Sxematik javob namunasi | Jonli yo‘l: javob + eskalatsiya, zaxirasi bilan |
| CTA | «Pilot deb yozing» | Taklif shartlari: siz / men / 2 haftadan keyin |
