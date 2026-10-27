# CoddyHelper — Demo Day pitchi (v2)

Format: 3:00 pitch → 1:00 savol → 1:00 jury fikri. Slaydlar: `coddyhelper_pitch_v2.html`
(→ / probel — keyingi, N — izohlar, F — to‘liq ekran, PDF uchun — Chop etish).

## Raqamlar manbasi

`coddy_memory.db`, 12–25 sentabr 2026 (14 kun). Egasining o‘z chati (`chat_id = 8105823872`) hisobga olinmagan.

| Ko‘rsatkich | Qiymat | SQL mantig‘i |
|---|---|---|
| Kiruvchi xabarlar | 259 (~18/kun) | `role='user'` |
| Yordamchi javoblari | 239 | `role='model'` |
| Chatlar | 38 (31 shaxsiy + 7 guruh) | `distinct chat_id`, manfiy = guruh |
| Kod savollari va loyiha havolalari | ~60 | kalit so‘zlar bo‘yicha (python/html/css/xato/kod; netlify/figma/github/wix) |

Cheklovlar: bu lokal nusxa. Sahnaga chiqishdan oldin prod MongoDB bilan solishtiring. Javoblarning to‘g‘riligi o‘lchanmagan. Mijozlar soni ham tekshirilmagan: lokal bazada 1 ta obuna bor.

## So‘zma-so‘z matn (~400 so‘z)

**Muammo**
Men CoddyCamp’da mentorman. Sentabrda bir kuni Telegramimga ketma-ket yozishdi: «IndexError nima degani?», «HTML bilan CSS qanday ulanadi?», loyiha linki, «Assalomu alaykum, ustoz». Men esa o‘sha payt boshqa guruhda dars o‘tyapman. Javob bermasam — bola uy vazifasida qotib qoladi. Telefonga qarasam — oldimdagi guruh kutib o‘tiradi. Shu narsa meni qiynadi, shuning uchun o‘zimga yordamchi yasadim.

**Yechim va muqobillar**
Uning nomi — CoddyHelper. Bu Telegramimda o‘tirgan AI yordamchi. O‘quvchi hech qanday botga emas, to‘g‘ri menga yozadi. Javobni esa yordamchi men kiritgan ma’lumotdan olib yozadi. Bilmagan savolni menga tashlaydi. O‘zim chatga yozsam — jim bo‘ladi. Albatta, qo‘lda yozsa ham bo‘ladi, Telegram Business’ning tayyor javoblari ham bor. Lekin tayyor javob savolni tushunmaydi. Alohida botga esa bolalar baribir yozmaydi — ustozga yozadi.

**Dalil**
Bu shunchaki g‘oya emas — ishlab turibdi. 14 kun o‘z akkauntimda sinab ko‘rdim. 38 ta chatdan 259 ta xabar keldi, kuniga 18 tacha. 239 tasiga yordamchi javob berdi — men bitta harf ham yozmadim. 60 tachasi kod savoli va loyiha linklari. To‘g‘risini aytsam: javoblarning qanchasi to‘g‘ri bo‘lganini hali bittalab tekshirib chiqmadim.

**Metrikalar va gipotezalar**
Men uchun eng muhim raqam — haftasiga men tuzatmagan javoblar soni. Yangi mentor kelsa, 7 kun ichida birinchi foydali javobni oldimi — shuni qarayman. Ikkinchi haftada ham ishlatyaptimi — shuni ham. Savol ko‘p kelishini o‘zimda ko‘rdim. Endi pilotda uchta narsani tekshiraman: javoblarning kamida 90 foizi to‘g‘rimi, vaqt kamida 30 foiz tejaldimi va kamida ikkita mentor pul to‘lab qoladimi.

**Biznes-model**
Pul oylik obunadan keladi. Mentor yoki o‘quv markazi to‘laydi. Pro — oyiga 99 ming so‘m, Ultra — 179 ming. Nega to‘laydi? Kuniga o‘nlab xabarga o‘zi o‘tirib javob yozmasligi uchun. Shu narxga rozi bo‘lishadimi — pilot oxirida gap bilan emas, pul so‘rab tekshiraman.

**Demo**
Hozir ko‘rsataman. *[Sinov akkauntidan yozing: «HTML bilan CSS qanday ulanadi?»]* Mana, javob mening nomimdan keldi, telefonimni ushlamadim. *[Ikkinchi xabar: «Ertangi dars bo‘ladimi?»]* Buni yordamchi bilmaydi va o‘zidan to‘qib chiqarmaydi — savol boshqaruv guruhimga tushdi. *[Guruhni ko‘rsating.]* Oddiy savol yopildi, mening qarorim kerak bo‘lgani esa menga keldi.

**CTA**
Shu yerda Telegramdan savol ko‘p oladigan mentorlar bor. Menga beshtangiz kerak: ikki hafta, tekin. Siz 10 daqiqada ulaysiz va eng ko‘p so‘raladigan beshta savolingizni berasiz. Men har hafta hisobot tashlab turaman: nechta savol yopildi, nechtasi sizga keldi, nechtasi xato bo‘ldi. Ikki haftadan keyin foydasi bo‘lsa — Pro’ga o‘tasiz, bo‘lmasa — o‘chirib qo‘yasiz. Bugun Telegramimga «pilot» deb yozing.

## Demo tayyorgarligi

1. Ikkinchi telefon yoki sinov akkaunti mentor akkauntiga yozishi kerak (egasining o‘z chatidan emas).
2. Bilimlar bazasida ertangi dars jadvali **bo‘lmasin**, aks holda eskalatsiya ishlamaydi.
3. Avtomatik javob yoqilgan va boshqaruv guruhi ulangan bo‘lsin. Demo chatiga 5 daqiqa ichida o‘zingiz yozmang: pauza ishlab qoladi.
4. Sahnadan oldin bu yo‘lni 3 marta bajaring. Javob vaqtini va har ikki natijani yozib oling.
5. Zaxira: shu yo‘lning 40 soniyalik ekran videosi. Javob 10 soniyada kelmasa, darhol videoga o‘ting.

## Savol-javob (formula: bilaman → hali bilmayman → qanday tekshiraman)

**Muammo haqiqiy ekanini qayerdan bilasiz?**
— 14 kunda o‘z akkauntimga 259 ta xabar keldi, hammasi bazada yozilgan. Boshqa mentorlarda ham shundaymi — hali bilmayman. Pilotdagi 5 mentorda shuni o‘lchayman.

**AI noto‘g‘ri javob bersa-chi?**
— Yordamchi faqat siz kiritgan ma’lumotdan javob beradi, bilmaganini sizga tashlaydi. O‘zingiz yozsangiz, to‘xtaydi. Umuman xato qilmaydi demayman. Shuning uchun pilotda har bir javobni mentor ko‘rib chiqadi, nechtasi xato bo‘lganini hisobotda ochiq yozaman.

**Nega ChatGPT yoki oddiy bot emas?**
— ChatGPT’dan javobni baribir o‘zingiz ko‘chirib yuborasiz. Botga esa bolalar yozmaydi — ustozga yozadi. CoddyHelper aynan o‘quvchi yozgan chatning o‘zida javob beradi.

**Akkauntim xavfsizmi? Telegram bloklamaydimi?**
— Ulanish Telegram’ning rasmiy API’si orqali ishlaydi, sessiya kodi shifrlangan, har bir odamning bazasi alohida. Lekin «hech qachon bloklamaydi» deb kafolat berolmayman. Shuning uchun pilotni kichkina qilib boshlayapman.

**Daromad bormi?**
— Hozircha daromad yo‘q. Tariflar tayyor turibdi. Pilot oxirida pullik davom ettirishni taklif qilaman: 5 mentordan kamida 2 tasi to‘lasa, demak ish bor.

## Oldingi versiya (PDF) bilan farqi

| Urok 6 talabi | PDF | v2 |
|---|---|---|
| Real epizod | To‘qilgan sahna («kurs narxi qancha?») | Akkauntga kelgan haqiqiy xabarlar |
| Nima uchun sizni qiziqtiradi | Yo‘q | O‘zim mentorman, o‘zim uchun yasadim |
| Muammo ko‘lami | «O‘lchanmagan» | 14 kunda 259 xabar, 38 chat |
| Muqobillar | Faqat «qo‘lda yozish» | Qo‘lda, Telegram Business, alohida bot |
| Metrikalar: qiymat, davr, manba | Faqat ta’riflar | Bor qiymatlar + pilotdagi o‘lchov |
| Tekshirilgan va tekshiriladigan gipoteza | Ajratilmagan | Ikki ustun, aniq mezonlar bilan |
| Demo | Sxematik javob namunasi | Jonli yo‘l: javob + eskalatsiya, zaxirasi bilan |
| CTA | «Pilot deb yozing» | Taklif shartlari: siz / men / 2 haftadan keyin |
