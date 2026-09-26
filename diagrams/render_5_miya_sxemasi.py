#!/usr/bin/env python3
"""
render_5_miya_sxemasi.py
Generates the crystal-clear, high-resolution schematic visual diagram of
CoddyHelper's full 5-Brain Cognitive Architecture.
"""

from PIL import Image, ImageDraw, ImageFont
import math
import os
import shutil

WIDTH = 1800
HEIGHT = 3500
BG_COLOR = (7, 11, 20)  # Deep obsidian dark slate #070b14

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

try:
    font_main_title = ImageFont.truetype(FONT_BOLD_PATH, 34)
    font_subtitle = ImageFont.truetype(FONT_PATH, 16)
    font_stage_title = ImageFont.truetype(FONT_BOLD_PATH, 20)
    font_node_bold = ImageFont.truetype(FONT_BOLD_PATH, 15)
    font_node = ImageFont.truetype(FONT_PATH, 13)
    font_node_sm = ImageFont.truetype(FONT_PATH, 11)
    font_badge = ImageFont.truetype(FONT_BOLD_PATH, 12)
    font_edge = ImageFont.truetype(FONT_BOLD_PATH, 13)
except Exception:
    font_main_title = font_subtitle = font_stage_title = font_node_bold = font_node = font_node_sm = font_badge = font_edge = ImageFont.load_default()

img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG_COLOR, 255))
draw = ImageDraw.Draw(img)

# Background subtle grid pattern
grid_color = (20, 27, 45, 120)
for x in range(0, WIDTH, 50):
    draw.line([(x, 0), (x, HEIGHT)], fill=grid_color, width=1)
for y in range(0, HEIGHT, 50):
    draw.line([(0, y), (WIDTH, y)], fill=grid_color, width=1)

def draw_card(box, fill, border, radius=14, width=2):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=border, width=width)

def draw_diamond(cx, cy, w, h, fill, border, width=2):
    pts = [
        (cx, cy - h // 2),
        (cx + w // 2, cy),
        (cx, cy + h // 2),
        (cx - w // 2, cy),
    ]
    draw.polygon(pts, fill=fill, outline=border)
    if width > 1:
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            draw.line([p1, p2], fill=border, width=width)

def draw_text_centered(cx, cy, lines, fonts, colors, line_spacing=4):
    total_h = 0
    line_metrics = []
    for line, font in zip(lines, fonts):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_metrics.append((w, h))
        total_h += h
    total_h += (len(lines) - 1) * line_spacing

    cur_y = cy - total_h // 2
    for line, font, color, (w, h) in zip(lines, fonts, colors, line_metrics):
        draw.text((cx - w // 2, cur_y), line, font=font, fill=color)
        cur_y += h + line_spacing

def draw_arrow(p1, p2, color=(56, 189, 248), width=2, arrow_len=10, label=None, label_side="right"):
    x1, y1 = p1
    x2, y2 = p2
    draw.line([p1, p2], fill=color, width=width)

    angle = math.atan2(y2 - y1, x2 - x1)
    a1 = angle + math.pi * 5 / 6
    a2 = angle - math.pi * 5 / 6
    tip1 = (x2 + arrow_len * math.cos(a1), y2 + arrow_len * math.sin(a1))
    tip2 = (x2 + arrow_len * math.cos(a2), y2 + arrow_len * math.sin(a2))
    draw.polygon([p2, tip1, tip2], fill=color)

    if label:
        mx = (x1 + x2) // 2
        my = (y1 + y2) // 2
        bbox = draw.textbbox((0, 0), label, font=font_edge)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        offset_x = 14 if label_side == "right" else -(lw + 14)
        draw.rounded_rectangle([mx + offset_x - 6, my - lh // 2 - 4, mx + offset_x + lw + 6, my + lh // 2 + 4], radius=6, fill=(15, 23, 42, 220), outline=color, width=1)
        draw.text((mx + offset_x, my - lh // 2 - 2), label, font=font_edge, fill=color)

# =========================================================================
# HEADER: MAIN TITLE
# =========================================================================
header_box = (60, 40, WIDTH - 60, 160)
draw_card(header_box, fill=(15, 23, 42, 230), border=(56, 189, 248), radius=16, width=2)
draw_text_centered(WIDTH // 2, 85, [
    "🧠 CODDYHELPER — TO'LIQ KOGNITIV MIYA ARXITEKTURASI",
    "5 Ta Mustaqil Miya Klasteri • Kognitiv Shaxs Razvedkasi • Multi-Tenant B2B SaaS"
], [font_main_title, font_subtitle], [(56, 189, 248), (148, 163, 184)])

badge_box = (WIDTH // 2 - 380, 125, WIDTH // 2 + 380, 150)
draw.rounded_rectangle(badge_box, radius=12, fill=(30, 41, 59))
draw_text_centered(WIDTH // 2, 137, [
    "⚡ 0.4s Tezlik  |  🛡️ Prompt Firewall  |  👥 Umumiy Guruhlar & Rol Detektori  |  🍃 Dual MongoDB+SQLite"
], [font_badge], [(52, 211, 153)])

# =========================================================================
# BOSQICH 1: KIRUVCHI SIGNALLAR & MIYA 1 (ESHITUVCHI & XAVFSIZLIK QALQONI)
# =========================================================================
s1_box = (60, 190, WIDTH - 60, 680)
draw_card(s1_box, fill=(15, 23, 42, 160), border=(56, 189, 248), radius=16, width=2)
draw.text((s1_box[0] + 25, s1_box[1] + 18), "1. SIGNALLAR QABULI & 🧠 MIYA 1: FRONTLINE LISTENER VA XAVFSIZLIK QALQONI", font=font_stage_title, fill=(56, 189, 248))

# Sub-nodes
in_tg = (120, 260, 480, 390)
draw_card(in_tg, fill=(24, 30, 56), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(300, 325, [
    "📱 TELEGRAM MTPROTO (TELETHON)",
    "• Shaxsiy xabarlar (DM / Lichka)",
    "• Monitoringdagi guruh chatlari",
    "• Matn, Audio/Ovoz, Rasmlar, Fayllar",
    "• Userbot rejimida xuddi insondek kirish"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(56, 189, 248), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

firewall_box = (540, 260, 920, 390)
draw_card(firewall_box, fill=(40, 20, 30), border=(239, 68, 68), radius=14, width=2)
draw_text_centered(730, 325, [
    "🛡️ PROMPT INJECTION FIREWALL",
    "• Tizim qoidalarini so'rashni bloklash",
    "• 'Ignore all instructions' hujumidan himoya",
    "• Haqorat va nojo'ya so'rovlarni filtrlash",
    "• Buzg'unchilarni avto-bloklash (Blacklist)"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(248, 113, 113), (255, 255, 255), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

whisper_box = (980, 260, 1340, 390)
draw_card(whisper_box, fill=(20, 35, 45), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(1160, 325, [
    "🎙️ WHISPER OVOZNI TANISH (STT)",
    "• Ovozli xabarlarni (.ogg) qabul qilish",
    "• O'zbek tili leksikasida aniq transkripsiya",
    "• Audio matnini umumiy buferga qo'shish",
    "• 1 soniyada matnga aylantirib tahlil qilish"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(52, 211, 153), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

debounce_box = (1400, 260, 1720, 390)
draw_card(debounce_box, fill=(35, 28, 55), border=(168, 85, 247), radius=14, width=2)
draw_text_centered(1560, 325, [
    "⏱️ QUIET WINDOW & DEBOUNCE",
    "• 5–8 soniya dinamik kutish oynasi",
    "• Bo'lib-bo'lib yozilgan xabarlarni yig'ish",
    "• Bitta yaxlit paketga birlashtirish",
    "• Bot bir vaqtda 5 ta javob yozishini oldini olish"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(216, 180, 254), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

# Arrow flows inside stage 1
draw_arrow((480, 325), (540, 325), color=(56, 189, 248))
draw_arrow((920, 325), (980, 325), color=(52, 211, 153), label="Xavfsiz")
draw_arrow((1340, 325), (1400, 325), color=(168, 85, 247))

# Decision in Stage 1: Guruhmi yoki Lichkami?
d_chat = (900, 520)
draw_diamond(d_chat[0], d_chat[1], 440, 80, fill=(30, 41, 59), border=(251, 191, 36), width=2)
draw_text_centered(d_chat[0], d_chat[1], [
    "Guruh chatmi yoki Shaxsiy lichkami?",
    "Smart Smart-Filter & Reply Context"
], [font_node_bold, font_node_sm], [(255, 255, 255), (251, 191, 36)])

draw_arrow((1560, 390), (1050, 480), color=(56, 189, 248))

# Group filter cards
grp_rules = (200, 580, 680, 650)
draw_card(grp_rules, fill=(24, 30, 56), border=(251, 191, 36), radius=12, width=1)
draw_text_centered(440, 615, [
    "👥 Guruhda: Botga reply / Chaqirilgandagina javob berish",
    "O'zaro o'quvchilar suhbatida jim turish"
], [font_node_bold, font_node_sm], [(251, 191, 36), (203, 213, 225)])

dm_rules = (1120, 580, 1600, 650)
draw_card(dm_rules, fill=(24, 30, 56), border=(52, 211, 153), radius=12, width=1)
draw_text_centered(1360, 615, [
    "👤 Shaxsiy chatda: Barcha xabarlarga 100% javob qaytarish",
    "Suhbatdosh shaxsini tahlil qilishga yo'naltirish"
], [font_node_bold, font_node_sm], [(52, 211, 153), (203, 213, 225)])

draw_arrow((680, 520), (440, 580), color=(251, 191, 36), label="Guruh", label_side="left")
draw_arrow((1120, 520), (1360, 580), color=(52, 211, 153), label="Shaxsiy chat", label_side="right")

# =========================================================================
# BOSQICH 2: 🧠 MIYA 2 (BILIMLAR BAZASI) & 🧠 MIYA 5 (PROFIL RAZVEDKASI)
# =========================================================================
s2_box = (60, 715, WIDTH - 60, 1380)
draw_card(s2_box, fill=(15, 23, 42, 160), border=(168, 85, 247), radius=16, width=2)
draw.text((s2_box[0] + 25, s2_box[1] + 18), "2. KOGNITIV KONTEKST: 🧠 MIYA 2 (BILIMLAR & RAG) + 🧠 MIYA 5 (PROFIL RAZVEDKASI & KESH)", font=font_stage_title, fill=(168, 85, 247))

# MIYA 5: PROFIL RAZVEDKASI (SOL TOMON)
m5_box = (100, 785, 880, 1140)
draw_card(m5_box, fill=(25, 20, 48), border=(168, 85, 247), radius=14, width=2)
draw_text_centered(490, 960, [
    "🕵️‍♂️ 🧠 MIYA 5: YASHIRIN PROFIL RAZVEDKASI (INTELLIGENCE DOSSIER)",
    "--------------------------------------------------------------------------------------------------------",
    "• 👥 Guruh A'zolarini Skanerlash: Monitoringdagi har bir guruhdan 200 tagacha a'zo navbatga olinadi",
    "• 🔗 Umumiy Guruhlar Detektori: GetCommonChatsRequest orqali umumiy guruhlar aniqlanadi",
    "• 🎯 Ijtimoiy Rol Tahlili: Ota-onami? O'quvchimi? Mijoz yoki Tadbirkormi?",
    "• 🔍 Yosh Oralig'i Taxmini: Ism/username'dagi yillar, leksika va kanallardan maksimal aniq aniqlash",
    "• 📸 Rasmlar & Stories: Foydalanuvchining barcha ochiq fotosuratlari va bog'langan kanallari tahlili",
    "• ♻️ Avto-Takroran Tekshiruv: Har 3 kunda eski dosyelarni fonda yangilab borish mexanizmi"
], [font_node_bold, font_node_sm, font_node, font_node, font_node, font_node, font_node, font_node],
[(216, 180, 254), (100, 116, 139), (255, 255, 255), (203, 213, 225), (52, 211, 153), (251, 191, 36), (56, 189, 248), (244, 114, 182)])

# MIYA 2: BILIMLAR BAZASI & RAG (O'NG TOMON)
m2_box = (920, 785, 1700, 1140)
draw_card(m2_box, fill=(20, 30, 50), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(1310, 960, [
    "📚 🧠 MIYA 2: BILIMLAR BAZASI, MAVZULAR CHEGARASI & OBSIDIAN RAG",
    "--------------------------------------------------------------------------------------------------------",
    "• 🎯 Mavzular Chegarasi (Curriculum Scope): Masalan faqat JS/Python bo'yicha javob (chalg'imaslik)",
    "• 🏢 Biznes Qoidalari & Shaxsiy Faktlar: Narxlar, xizmat shartlari, o'quv tartib-qoidalari",
    "• 📝 Obsidian Vault (.md fayllar): Mentor tomonidan yozilgan saboqlar avtomatik ulanadi",
    "• 💡 O'rganilgan Darslar (Dynamic Insights): Har bir suhbatdan olingan xulosalar bazasi",
    "• 🛡️ Leksikon & Xatoliklar Banki: O'quvchilar eng ko'p qiladigan 3 ta xatolik bo'yicha yo'naltirish",
    "• 🧩 Multi-Tenant Ajratish: Har bir obunachi mijoz uchun faqat uning o'z bilimlari yuklanadi"
], [font_node_bold, font_node_sm, font_node, font_node, font_node, font_node, font_node, font_node],
[(56, 189, 248), (100, 116, 139), (255, 255, 255), (203, 213, 225), (52, 211, 153), (251, 191, 36), (216, 180, 254), (244, 114, 182)])

# Precomputed Answers Decision in Stage 2
d_cache = (900, 1260)
draw_diamond(d_cache[0], d_cache[1], 480, 90, fill=(30, 41, 59), border=(52, 211, 153), width=2)
draw_text_centered(d_cache[0], d_cache[1], [
    "⚡ 🧠 MIYA 5: Yechimlar Keshida Bormi?",
    "1,600+ Oldindan hisoblangan tayyor yechimlar"
], [font_node_bold, font_node_sm], [(52, 211, 153), (255, 255, 255)])

draw_arrow((490, 1140), (700, 1220), color=(168, 85, 247))
draw_arrow((1310, 1140), (1100, 1220), color=(56, 189, 248))

# Fast cache hit output
cache_hit_box = (150, 1220, 600, 1300)
draw_card(cache_hit_box, fill=(16, 185, 129, 30), border=(52, 211, 153), radius=12, width=2)
draw_text_centered(375, 1260, [
    "⚡ 0.05s TEZKOR KESH JAVOBI",
    "API chaqirilmaydi • 100% bepul va lahzalik"
], [font_node_bold, font_node_sm], [(52, 211, 153), (203, 213, 225)])

draw_arrow((660, 1260), (600, 1260), color=(52, 211, 153), label="Ha (Keshda bor)", label_side="left")

# =========================================================================
# BOSQICH 3: 🧠 MIYA 3 (MULTI-KEY NEYRO-KLASTER ROUTER)
# =========================================================================
s3_box = (60, 1420, WIDTH - 60, 2060)
draw_card(s3_box, fill=(15, 23, 42, 160), border=(236, 72, 153), radius=16, width=2)
draw.text((s3_box[0] + 25, s3_box[1] + 18), "3. GENERATSIYA: 🧠 MIYA 3: MULTI-KEY NEYRO-KLASTER ROUTER (GROQ CLUSTER & GEMINI MULTIMODAL)", font=font_stage_title, fill=(236, 72, 153))

draw_arrow((900, 1305), (900, 1470), color=(236, 72, 153), label="Yo'q (Yangi savol)", label_side="right")

# Persona & Mode Selector
persona_box = (400, 1470, 1400, 1540)
draw_card(persona_box, fill=(25, 25, 50), border=(236, 72, 153), radius=12, width=2)
draw_text_centered(900, 1505, [
    "🎭 SHAXSIYLASHTIRILGAN MULOQOT REJIMI VA FORMATI",
    "Super Admin: Sokratik / Tech Lead | Mijozlar: Batafsil / Qisqa va lo'nda / Bosqichma-bosqich"
], [font_node_bold, font_node_sm], [(244, 114, 182), (255, 255, 255)])

# Model Cards
m_groq = (120, 1600, 880, 1920)
draw_card(m_groq, fill=(20, 30, 55), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(500, 1760, [
    "🚀 GROQ MULTI-KEY KLASTER (ASOSIY DVIGATEL)",
    "Model: Llama-3.3 70B Versatile (Meta AI)",
    "-------------------------------------------------------------------------------------",
    "• ⚡ Tezlik: ~0.4–0.8 soniya (dunyo bo'yicha eng tezkor inferensiya)",
    "• 🔄 Multi-Key Key-Rotation: 48+ ta mustaqil Groq API kalitlari",
    "• 🛡️ 8,000 TPM limitlaridan himoya (Avtomatik kalit almashtirish)",
    "• 🧠 Mantiqiy fikrlash, o'zbek tilini chuqur tushunish, kod sintaksisi",
    "• 🎯 Sokratik metodika bo'yicha o'quvchini yechimga o'zi yetishiga yo'naltirish"
], [font_node_bold, font_node, font_node_sm, font_node, font_node, font_node, font_node, font_node],
[(56, 189, 248), (255, 255, 255), (100, 116, 139), (52, 211, 153), (203, 213, 225), (251, 191, 36), (203, 213, 225), (216, 180, 254)])

m_gemini = (920, 1600, 1680, 1920)
draw_card(m_gemini, fill=(25, 25, 55), border=(99, 102, 241), radius=14, width=2)
draw_text_centered(1300, 1760, [
    "🖼️ GOOGLE GEMINI 2.5 FLASH / MULTIMODAL (ZAXIRA)",
    "Model: gemini-2.5-flash (Google DeepMind)",
    "-------------------------------------------------------------------------------------",
    "• 📸 Rasmlar & Skrinshotlar: Kod xatolarini rasmdan OCR orqali o'qish",
    "• 📑 Katta Hujjatlar: PDF, DOCX, IPYNB fayllarini to'liq o'qib tahlil qilish",
    "• 🛡️ Temir Zaxira (Iron Fallback): Groq 100% band bo'lsa darhol ulanish",
    "• 🌐 Ulkan Kontekst: 1,000,000+ token kontekst oynasi",
    "• ⚡ Uzluksiz 24/7 ishonchlilik (Nol xatolik kafolati)"
], [font_node_bold, font_node, font_node_sm, font_node, font_node, font_node, font_node, font_node],
[(165, 180, 252), (255, 255, 255), (100, 116, 139), (52, 211, 153), (203, 213, 225), (248, 113, 113), (251, 191, 36), (56, 189, 248)])

draw_arrow((650, 1540), (500, 1600), color=(56, 189, 248), label="Matnli savol", label_side="left")
draw_arrow((1150, 1540), (1300, 1600), color=(99, 102, 241), label="Rasm / Fallback", label_side="right")

# Cascade Failover Bar
cf_bar = (300, 1960, 1500, 2025)
draw_card(cf_bar, fill=(30, 20, 40), border=(236, 72, 153), radius=10, width=1)
draw_text_centered(900, 1992, [
    "🔗 ZERO-DOWNTIME FAILOVER: Groq Klasteri ➔ Rate Limit (429) bo'lsa ➔ Gemini Flash Zaxirasiga 0.1 soniyada avto-o'tish!"
], [font_node_bold], [(244, 114, 182)])

# =========================================================================
# BOSQICH 4: 🧠 MIYA 4 (INSON NAZORATI, ESKALATSIYA & VAZIFALAR GURUHI)
# =========================================================================
s4_box = (60, 2100, WIDTH - 60, 2680)
draw_card(s4_box, fill=(15, 23, 42, 160), border=(52, 211, 153), radius=16, width=2)
draw.text((s4_box[0] + 25, s4_box[1] + 18), "4. GIBRID ONGLILIK: 🧠 MIYA 4: INSON NAZORATI (HUMAN-IN-THE-LOOP) & ESKALATSIYA GURUHI", font=font_stage_title, fill=(52, 211, 153))

draw_arrow((900, 2025), (900, 2150), color=(52, 211, 153))

# Decision in Stage 4: Javob yetarlimi yoki eskalatsiyami?
d_escalate = (900, 2200)
draw_diamond(d_escalate[0], d_escalate[1], 460, 85, fill=(30, 41, 59), border=(52, 211, 153), width=2)
draw_text_centered(d_escalate[0], d_escalate[1], [
    "AI Javobi Yetarlimi yoki Mentor Aralashuvi Kerakmi?",
    "Ishonch darajasi, murakkablik va eskalatsiya qoidalari"
], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])

# Output Left: Oddiy foydalanuvchiga javob
reply_user_box = (150, 2340, 750, 2520)
draw_card(reply_user_box, fill=(16, 185, 129, 30), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(450, 2430, [
    "💬 FOYDALANUVCHIGA TO'G'RIDAN-TO'G'RI JAVOB",
    "• Telegram orqali tabiiy va xushmuomala yuborish",
    "• Shaxsiy rolga (Ota-ona / O'quvchi / Mijoz) mos uslub",
    "• Matn yoki Ovozli xabar shaklida",
    "• BOT_SENT_MESSAGE_IDS orqali sikllardan himoya"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(52, 211, 153), (255, 255, 255), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

# Output Right: Vazifalar Guruhi (Eskalatsiya)
escalate_box = (1050, 2340, 1650, 2520)
draw_card(escalate_box, fill=(40, 25, 45), border=(236, 72, 153), radius=14, width=2)
draw_text_centered(1350, 2430, [
    "🚨 VAZIFALAR GURUHI: INSON NAZORATI (-5388159517)",
    "• 👤 Suhbatdosh: Ismi, ID, Bog'langan kanali va Dosyesi",
    "• 📜 Suhbat Konteksti: So'nggi 5-6 xabar va muammo mohiyati",
    "• 👨‍🏫 Mentor aralashuvi: Mentor javob bersa, AI jim turadi",
    "• 📝 Dars Saboqlari: Mentor xatosini ko'rib, keyingi safar o'rganadi"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(244, 114, 182), (255, 255, 255), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

draw_arrow((720, 2200), (450, 2340), color=(52, 211, 153), label="AI ishonchi yuqori", label_side="left")
draw_arrow((1080, 2200), (1350, 2340), color=(236, 72, 153), label="Eskalatsiya / Yordam", label_side="right")

# Smart Reminders & GPS Bar
remind_box = (300, 2560, 1500, 2640)
draw_card(remind_box, fill=(25, 35, 50), border=(251, 191, 36), radius=12, width=1)
draw_text_centered(900, 2600, [
    "⏰ SMART REMINDERS & GPS: 'Ertaga 10:00 da eslat' buyruqlari avtomatik navbatga qo'yiladi va koordinatalar xaritaga saqlanadi"
], [font_node_bold], [(251, 191, 36)])

# =========================================================================
# BOSQICH 5: XOTIRA & MULTI-TENANT BULUT EKOLOGIYASI
# =========================================================================
s5_box = (60, 2720, WIDTH - 60, 3420)
draw_card(s5_box, fill=(15, 23, 42, 160), border=(56, 189, 248), radius=16, width=2)
draw.text((s5_box[0] + 25, s5_box[1] + 18), "5. DUAL XOTIRA & MULTI-TENANT B2B BULUT EKOLOGIYASI", font=font_stage_title, fill=(56, 189, 248))

draw_arrow((450, 2520), (450, 2770), color=(52, 211, 153))
draw_arrow((1350, 2520), (1350, 2770), color=(236, 72, 153))

# SQLite Box
sql_full = (120, 2780, 620, 3050)
draw_card(sql_full, fill=(20, 30, 55), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(370, 2915, [
    "💾 SQLITE (coddy_memory.db)",
    "Mahalliy Ultra-Tezkor Kesh (<1ms)",
    "--------------------------------------------------",
    "• 280+ Shaxsiy foydalanuvchi dosyelari",
    "• 1,600+ Precomputed kesh yechimlari",
    "• Foydalanuvchi obunalari va guruhlar",
    "• Tezkor status, sozlamalar va eslatmalar"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(56, 189, 248), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225)])

# MongoDB Atlas Box
mongo_full = (660, 2780, 1140, 3050)
draw_card(mongo_full, fill=(20, 40, 45), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(900, 2915, [
    "🍃 MONGODB ATLAS CLOUD",
    "Doimiy Global Bulut Sinxronizatsiyasi",
    "--------------------------------------------------",
    "• Server qayta yonganda to'liq avto-tiklash",
    "• brain_frontline.user_dossiers (umumiy guruhlar)",
    "• brain_knowledge.precomputed_answers (1,600+)",
    "• brain_core.subscriptions (B2B mijozlar)",
    "• Render konteyneri o'chib yonsa ham 0% yo'qotish"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(52, 211, 153), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (251, 191, 36)])

# WebApp Box
webapp_box = (1180, 2780, 1680, 3050)
draw_card(webapp_box, fill=(35, 25, 55), border=(168, 85, 247), radius=14, width=2)
draw_text_centered(1430, 2915, [
    "📱 TELEGRAM MINI APP & PWA",
    "Boshqaruv Paneli & Multi-Tenant CRM",
    "--------------------------------------------------",
    "• Super Admin: Barcha mijozlar, metrikalar, dosyelar",
    "• Obunachi Mijoz: Shaxsiy statistika va bilimlari",
    "• Real-time AI Metrikalari (RPM, TPM, Sarf)",
    "• Ovozli xabarlar, CRM va shaxsiy promptlar"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(216, 180, 254), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225)])

draw_arrow((620, 2915), (660, 2915), color=(52, 211, 153), label="Sync", label_side="right")
draw_arrow((1140, 2915), (1180, 2915), color=(168, 85, 247), label="API", label_side="right")

# Bottom Summary Card
bot_sum = (120, 3100, 1680, 3370)
draw_card(bot_sum, fill=(15, 23, 42, 230), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(900, 3235, [
    "🌟 XULOSA: INSONIYATGA MOSLASHGAN AVTONOM SIKL (CONTINUOUS COGNITIVE LOOP)",
    "------------------------------------------------------------------------------------------------------------------------------------------------------------------------",
    "1. Qabul qilish: Xabar kelishi bilan Miya 1 xavfsizlikdan o'tkazadi va tinchlik oynasida buferlaydi.",
    "2. Razvedka & Qoidalar: Miya 5 shaxsning umumiy guruhlari va rolini tahlil qiladi, Miya 2 esa shaxsiy mavzular chegarasini belgilaydi.",
    "3. Neyro-Qaror: Miya 3 Groq klasteri orqali insoniy ohangda javob generatsiya qiladi; muammo tug'ilsa Miya 4 orqali mentorga eskalatsiya bo'ladi.",
    "4. Dual Xotira: Barcha xulosalar mahalliy SQLite va global MongoDB Atlas bulutida saqlanib, tizim 24/7 uzluksiz o'rganadi."
], [font_node_bold, font_node_sm, font_node, font_node, font_node, font_node],
[(56, 189, 248), (100, 116, 139), (255, 255, 255), (203, 213, 225), (52, 211, 153), (216, 180, 254)])

# Save output
output_path = "/Applications/Project/coddyHelper/toliq_miya_sxemasi.png"
img.save(output_path, "PNG", optimize=True)
print(f"🎉 Rasm muvaffaqiyatli saqlandi: {output_path}")

# Copy to artifacts directory
artifact_dir = "/Users/nuriddin/.gemini/antigravity/brain/1f21b7c7-5c0f-45c7-88a2-a4504f26a125"
if os.path.exists(artifact_dir):
    artifact_img = os.path.join(artifact_dir, "toliq_miya_sxemasi.png")
    shutil.copy2(output_path, artifact_img)
    print(f"📁 Artifactga nusxalandi: {artifact_img}")
