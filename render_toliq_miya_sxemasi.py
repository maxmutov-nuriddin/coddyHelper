#!/usr/bin/env python3
"""
render_toliq_miya_sxemasi.py
Generates the complete high-resolution, crystal-clear diagram of CoddyHelper's full cognitive architecture.
"""
import math
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1600
HEIGHT = 3400
BG_COLOR = (7, 11, 20)  # Deep obsidian dark slate #070b14

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

try:
    font_main_title = ImageFont.truetype(FONT_BOLD_PATH, 32)
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
    
    cur_y = cy - total_h / 2
    for line, font, color, (w, h) in zip(lines, fonts, colors, line_metrics):
        draw.text((cx - w / 2, cur_y), line, font=font, fill=color)
        cur_y += h + line_spacing

def draw_arrow(p1, p2, color=(56, 189, 248), width=2, arrow_size=8, label=None, label_side="right"):
    x1, y1 = p1
    x2, y2 = p2
    draw.line([p1, p2], fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    ax1 = x2 - arrow_size * math.cos(angle - math.pi / 6)
    ay1 = y2 - arrow_size * math.sin(angle - math.pi / 6)
    ax2 = x2 - arrow_size * math.cos(angle + math.pi / 6)
    ay2 = y2 - arrow_size * math.sin(angle + math.pi / 6)
    draw.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=color)
    
    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        bbox = draw.textbbox((0, 0), label, font=font_edge)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        offset = 12 if label_side == "right" else -(lw + 12)
        bx0 = mx + offset - 6
        by0 = my - lh / 2 - 3
        bx1 = bx0 + lw + 12
        by1 = by0 + lh + 6
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=5, fill=(15, 23, 42, 240), outline=color, width=1)
        draw.text((bx0 + 6, by0 + 3), label, font=font_edge, fill=color)

# =========================================================================
# HEADER
# =========================================================================
header_box = (60, 40, WIDTH - 60, 140)
draw_card(header_box, fill=(15, 23, 42, 230), border=(99, 102, 241), radius=20, width=2)
draw_text_centered(
    (header_box[0] + header_box[2]) / 2, 72,
    ["🧠 CODDYHELPER — TO'LIQ KOGNITIV MIYA SXEMASI VA ISHLASH MEXANIZMI"],
    [font_main_title],
    [(255, 255, 255)]
)
draw_text_centered(
    (header_box[0] + header_box[2]) / 2, 112,
    ["Ko'p Formatli Qabul (Multimodal) ➔ 4 Pog'onali Qalqon ➔ Dinamik Agregator ➔ Gibrid Xotira ➔ 5 ta Mustaqil Miya ➔ Dual Chiqish & Eskalatsiya"],
    [font_subtitle],
    [(148, 163, 184)]
)

# =========================================================================
# 1-BOSQICH: MULTIMODAL KIRISH OQIMI (INGESTION)
# =========================================================================
s1_box = (60, 165, WIDTH - 60, 480)
draw_card(s1_box, fill=(15, 23, 42, 160), border=(56, 189, 248), radius=16, width=2)
draw.text((s1_box[0] + 25, s1_box[1] + 18), "1. XABAR KIRIB KELISHI VA FORMATLARNI DEKODLASH (MULTIMODAL INGESTION)", font=font_stage_title, fill=(56, 189, 248))

# Node 1: Telegram Hodisa
c1_box = (650, 225, 950, 285)
draw_card(c1_box, fill=(30, 41, 59), border=(56, 189, 248), radius=12, width=2)
draw_text_centered(800, 255, ["Telegram'dan Yangi Xabar (NewMessage Event)", "Telethon MTProto orqali olinadi"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])

# Diamond: Qayerdan keldi?
d1_center = (800, 360)
draw_diamond(d1_center[0], d1_center[1], 280, 80, fill=(30, 41, 59), border=(56, 189, 248), width=2)
draw_text_centered(d1_center[0], d1_center[1], ["Xabar kimdan va qayerdan keldi?"], [font_node_bold], [(255, 255, 255)])
draw_arrow((800, 285), (800, 320), color=(56, 189, 248))

# Branch 1A: Mentor AI Buyrug'i (Express VIP)
m_box = (150, 415, 450, 470)
draw_card(m_box, fill=(24, 30, 56), border=(168, 85, 247), radius=12, width=2)
draw_text_centered(300, 442, ["Mentor: 'ai <vazifa>' yoki reply 'ai'", "Miya 2 VIP Klasterga to'g'ridan-to'g'ri"], [font_node_bold, font_node_sm], [(216, 180, 254), (192, 132, 252)])
draw_arrow((660, 360), (450, 442), color=(168, 85, 247), label="Mentor 'ai' buyrug'i", label_side="left")

# Branch 1B: Lichka (DM)
dm_box = (650, 415, 950, 470)
draw_card(dm_box, fill=(30, 41, 59), border=(56, 189, 248), radius=12, width=2)
draw_text_centered(800, 442, ["Lichka (DM): To'g'ridan-to'g'ri qabul", "Barcha kod, rasm, .ipynb, .docx ruxsat"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])
draw_arrow((800, 400), (800, 415), color=(56, 189, 248), label="Lichka (DM)", label_side="right")

# Branch 1C: Guruh
grp_box = (1150, 415, 1450, 470)
draw_card(grp_box, fill=(30, 41, 59), border=(251, 191, 36), radius=12, width=2)
draw_text_centered(1300, 442, ["Guruh Oqimi: O'quvchilar chati", "Kognitiv Qalqonga yo'naltirish"], [font_node_bold, font_node_sm], [(255, 255, 255), (251, 191, 36)])
draw_arrow((940, 360), (1150, 442), color=(251, 191, 36), label="Guruh chati", label_side="right")

# =========================================================================
# 2-BOSQICH: KOGNITIV GURUH QALQONI (COGNITIVE SHIELD)
# =========================================================================
s2_box = (60, 505, WIDTH - 60, 1140)
draw_card(s2_box, fill=(15, 23, 42, 160), border=(251, 191, 36), radius=16, width=2)
draw.text((s2_box[0] + 25, s2_box[1] + 18), "2. KOGNITIV GURUH QALQONI (4 POG'ONALI FILTR VA PEER INTELLIGENCE)", font=font_stage_title, fill=(251, 191, 36))

# Silent Drop Node
silent_box = (150, 780, 470, 870)
draw_card(silent_box, fill=(45, 20, 20), border=(248, 113, 113), radius=14, width=2)
draw_text_centered(310, 825, ["🚫 AI JIM TURADI (SILENT DROP)", "Suhbatga aralashmaydi, tinch kuzatadi", "O'quvchilar o'zaro tajriba almashadi"], [font_node_bold, font_node, font_node_sm], [(248, 113, 113), (252, 165, 165), (254, 202, 202)])

# P1: Xavfli fayl yoki Botga reply bormi?
d_p1 = (1300, 580)
draw_diamond(d_p1[0], d_p1[1], 340, 80, fill=(30, 41, 59), border=(251, 191, 36), width=2)
draw_text_centered(d_p1[0], d_p1[1], ["1-Pog'ona: Botga reply yoki", "Xavfli/Begona fayl bormi?"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])
draw_arrow((1300, 470), (1300, 540), color=(251, 191, 36))

# P2: Ustozga murojaat bormi?
d_p2 = (1300, 720)
draw_diamond(d_p2[0], d_p2[1], 340, 80, fill=(30, 41, 59), border=(251, 191, 36), width=2)
draw_text_centered(d_p2[0], d_p2[1], ["2-Pog'ona: Ustoz chaqirilganmi?", "('Ustoz', 'Nuriddin aka', '@mentor_cc')"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])
draw_arrow((1300, 620), (1300, 680), color=(251, 191, 36), label="Yo'q", label_side="right")

# P3: O'quvchilar o'zaro gaplashyaptimi?
d_p3 = (1300, 860)
draw_diamond(d_p3[0], d_p3[1], 340, 80, fill=(30, 41, 59), border=(251, 191, 36), width=2)
draw_text_centered(d_p3[0], d_p3[1], ["3-Pog'ona: O'zaro suhbatmi?", "(Boshqa o'quvchiga reply / 'sanda', 'bro')"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])
draw_arrow((1300, 760), (1300, 820), color=(251, 191, 36), label="Yo'q", label_side="right")
draw_arrow((1130, 860), (470, 840), color=(248, 113, 113), label="Ha (O'zaro suhbat) ➔ JIM TURISH", label_side="right")

# P4: Dasturlash mavzusimi?
d_p4 = (1300, 1000)
draw_diamond(d_p4[0], d_p4[1], 340, 80, fill=(30, 41, 59), border=(251, 191, 36), width=2)
draw_text_centered(d_p4[0], d_p4[1], ["4-Pog'ona: Mavzu kod/darsga doirmi?", "Off-topic (futbol, ob-havo) bormi?"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])
draw_arrow((1300, 900), (1300, 960), color=(251, 191, 36), label="Yo'q", label_side="right")
draw_arrow((1130, 1000), (470, 860), color=(248, 113, 113), label="Yo'q (Befoyda suhbat) ➔ JIM TURISH", label_side="right")

# Sokratik 12 soniya kutish
sok_box = (1150, 1070, 1450, 1125)
draw_card(sok_box, fill=(30, 41, 59), border=(52, 211, 153), radius=12, width=2)
draw_text_centered(1300, 1097, ["Sokratik 12s Kutish Oynasi", "Tengdosh yordamini kutish"], [font_node_bold, font_node_sm], [(52, 211, 153), (148, 163, 184)])
draw_arrow((1300, 1040), (1300, 1070), color=(52, 211, 153), label="Ha (Kod savoli)", label_side="right")

# D_OK Node: Qabul qilindi
dok_box = (680, 1070, 920, 1125)
draw_card(dok_box, fill=(16, 185, 129, 40), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(800, 1097, ["XABAR QABUL QILINDI ✅", "Tahlil va Buferga uzatildi"], [font_node_bold, font_node_sm], [(52, 211, 153), (255, 255, 255)])

draw_arrow((dm_box[0] + 150, dm_box[3]), (800, 1070), color=(52, 211, 153))
draw_arrow((d_p1[0] - 170, d_p1[1]), (860, 1070), color=(52, 211, 153), label="Ha (Bot chaqirilgan)", label_side="right")
draw_arrow((d_p2[0] - 170, d_p2[1]), (840, 1070), color=(52, 211, 153), label="Ha (Ustoz murojaati)", label_side="right")
draw_arrow((sok_box[0], 1097), (dok_box[2], 1097), color=(52, 211, 153), label="12s da hech kim bilmadi", label_side="right")

# =========================================================================
# 3-BOSQICH: XABARLAR AGREGATORI (ACCUMULATOR & LIVE TELEGRAM ORDER)
# =========================================================================
s3_box = (60, 1165, WIDTH - 60, 1500)
draw_card(s3_box, fill=(15, 23, 42, 160), border=(56, 189, 248), radius=16, width=2)
draw.text((s3_box[0] + 25, s3_box[1] + 18), "3. XABARLAR AGREGATORI VA DEBOUNCE (MESSAGE_ACCUMULATOR)", font=font_stage_title, fill=(56, 189, 248))

draw_arrow((800, 1125), (800, 1205), color=(56, 189, 248))

# Node 3A
acc1_box = (650, 1205, 950, 1265)
draw_card(acc1_box, fill=(30, 41, 59), border=(56, 189, 248), radius=12, width=2)
draw_text_centered(800, 1235, ["O'quvchi bo'lib-bo'lib yozishi kutiladi", "5–8 soniyalik dinamik debounce oynasi"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])

# Diamond: Yana xabar bormi?
d_acc = (800, 1340)
draw_diamond(d_acc[0], d_acc[1], 300, 75, fill=(30, 41, 59), border=(56, 189, 248), width=2)
draw_text_centered(d_acc[0], d_acc[1], ["Yana qo'shimcha xabar bormi?"], [font_node_bold], [(255, 255, 255)])
draw_arrow((800, 1265), (800, 1302), color=(56, 189, 248))

# Loop back
loop_box = (1080, 1280, 1380, 1340)
draw_card(loop_box, fill=(30, 41, 59), border=(251, 191, 36), radius=12, width=1)
draw_text_centered(1230, 1310, ["Yangi qismni buferga qo'shish", "Taymerni qayta boshlash"], [font_node_bold, font_node_sm], [(251, 191, 36), (148, 163, 184)])
draw_arrow((950, 1340), (1080, 1310), color=(251, 191, 36), label="Ha (Yozmoqda)", label_side="right")
draw_arrow((1230, 1280), (950, 1235), color=(251, 191, 36))

# Node 3B: Birlashtirish
acc2_box = (650, 1420, 950, 1480)
draw_card(acc2_box, fill=(30, 41, 59), border=(52, 211, 153), radius=12, width=2)
draw_text_centered(800, 1450, ["Barcha xabarlarni yaxlit 1 ta paketga jamlash", "Live Telegram ID tekshiruvi (lm.id > max_id)"], [font_node_bold, font_node_sm], [(52, 211, 153), (148, 163, 184)])
draw_arrow((800, 1378), (800, 1420), color=(52, 211, 153), label="Yo'q (Kutish tugadi)", label_side="right")

# =========================================================================
# 4-BOSQICH: GIBRID XOTIRA VA SHAXSIYAT (DUAL HYBRID MEMORY)
# =========================================================================
s4_box = (60, 1525, WIDTH - 60, 1820)
draw_card(s4_box, fill=(15, 23, 42, 160), border=(168, 85, 247), radius=16, width=2)
draw.text((s4_box[0] + 25, s4_box[1] + 18), "4. GIBRID XOTIRA VA PROFIL INTELLEKTI (DUAL PERSISTENCE MEMORY)", font=font_stage_title, fill=(168, 85, 247))

draw_arrow((800, 1480), (800, 1560), color=(168, 85, 247))

# SQLite Box
sql_box = (250, 1580, 650, 1670)
draw_card(sql_box, fill=(24, 30, 56), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(450, 1625, [
    "💾 SQLite (coddy_memory.db): Mahalliy Tezkor Xotira",
    "• Dialogni vaqt tamg'alari [HH:MM] bilan olish",
    "• Doimiy eslatmalar va smart-briefing",
    "• Har 1 soatda avto-backup (@coddyassistanstbot)"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm], [(56, 189, 248), (203, 213, 225), (203, 213, 225), (203, 213, 225)])

# Mongo Box
mongo_box = (950, 1580, 1350, 1670)
draw_card(mongo_box, fill=(24, 30, 56), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(1150, 1625, [
    "🍃 MongoDB Atlas: Doimiy Bulut Xotirasi",
    "• O'quvchi darajasi (Boshlang'ich, O'rta, Kuchli)",
    "• Shaxsiy qiziqishlar va qora ro'yxat (Blacklist)",
    "• Pre-computation kesh (Oldindan hisoblangan yechimlar)"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm], [(52, 211, 153), (203, 213, 225), (203, 213, 225), (203, 213, 225)])

# Unified Context Box
uni_box = (600, 1720, 1000, 1790)
draw_card(uni_box, fill=(30, 41, 59), border=(168, 85, 247), radius=14, width=2)
draw_text_centered(800, 1755, ["TO'LIQ BOYTILGAN KOGNITIV PROMPT PAKETI", "Matn + Hujjatlar + Xotira + Shaxsiy profil darajasi"], [font_node_bold, font_node_sm], [(216, 180, 254), (255, 255, 255)])

draw_arrow((450, 1670), (700, 1720), color=(168, 85, 247))
draw_arrow((1150, 1670), (900, 1720), color=(168, 85, 247))

# =========================================================================
# 5-BOSQICH: 5 TA MUSTAQIL MIYA KLASTERI (5 CORE BRAINS ARCHITECTURE)
# =========================================================================
s5_box = (60, 1845, WIDTH - 60, 2600)
draw_card(s5_box, fill=(15, 23, 42, 160), border=(236, 72, 153), radius=16, width=2)
draw.text((s5_box[0] + 25, s5_box[1] + 18), "5. 5 TA MUSTAQIL MIYA KLASTERI (MULTI-TIER BRAIN ROUTING)", font=font_stage_title, fill=(236, 72, 153))

draw_arrow((800, 1790), (800, 1880), color=(236, 72, 153))

# Decision: Qaysi Miya ishlaydi?
d_brain = (800, 1920)
draw_diamond(d_brain[0], d_brain[1], 360, 80, fill=(30, 41, 59), border=(236, 72, 153), width=2)
draw_text_centered(d_brain[0], d_brain[1], ["Miya Tanlagich (Smart Dispatcher)", "So'rov egasi va vazifa murakkabligi"], [font_node_bold, font_node_sm], [(255, 255, 255), (244, 114, 182)])

# Miya 1: Frontline
b1_box = (100, 2030, 360, 2340)
draw_card(b1_box, fill=(24, 30, 56), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(230, 2185, [
    "🧠 1-MIYA: FRONTLINE",
    "Groq LLaMA-3.3 70B",
    "-------------------------",
    "• O'quvchilar savollari",
    "• Sokratik yo'l-yo'riq",
    "• Tayyor kod bermaydi",
    "• Fikrlashga o'rgatadi",
    "• 12 ta mustaqil kalit",
    "• Tezlik: ~0.8 soniya"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(56, 189, 248), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184), (52, 211, 153)])

# Miya 2: VIP Klaster
b2_box = (390, 2030, 650, 2340)
draw_card(b2_box, fill=(28, 20, 50), border=(168, 85, 247), radius=14, width=2)
draw_text_centered(520, 2185, [
    "👑 2-MIYA: VIP KLASTER",
    "openai/gpt-oss-120b",
    "-------------------------",
    "• Faqat Mentor & Vazifalar",
    "• 'ai <vazifa>' buyruqlari",
    "• Sokratik cheklovsiz",
    "• To'liq tayyor yechimlar",
    "• 12 ta VIP Groq kaliti",
    "• 0% o'quvchilarga ta'sir"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(216, 180, 254), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184), (52, 211, 153)])

# Miya 3: Zaxira Qalqoni (Buffer)
b3_box = (680, 2030, 940, 2340)
draw_card(b3_box, fill=(20, 35, 45), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(810, 2185, [
    "🛡️ 3-MIYA: ZAXIRA QALQONI",
    "Groq Buffer Pool (20B/Qwen)",
    "-------------------------",
    "• Kalitlar band bo'lganda",
    "• Rate Limit (429) qalqoni",
    "• Avtomatik zaxira rotatsiyasi",
    "• Har doim 100% ulanish",
    "• Uzluksiz barqarorlik",
    "• Hech qachon to'xtamaydi"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(52, 211, 153), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184), (52, 211, 153)])

# Miya 4: Avtonom O'rganuvchi Ong
b4_box = (970, 2030, 1230, 2340)
draw_card(b4_box, fill=(35, 25, 20), border=(251, 191, 36), radius=14, width=2)
draw_text_centered(1100, 2185, [
    "🔮 4-MIYA: AVTONOM ONG",
    "Pre-Cognition Daemon",
    "-------------------------",
    "• 24/7 orqa fonda o'ylash",
    "• Xatolarni tahlil qilish",
    "• Mentor leksikonini o'rganish",
    "• Oldindan tayyor yechimlar",
    "• Kunlik debrief (20:00 da)",
    "• Mustaqil #8-#10 kalitlar"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(251, 191, 36), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184), (52, 211, 153)])

# Miya 5: Google Gemini Multimodal
b5_box = (1260, 2030, 1520, 2340)
draw_card(b5_box, fill=(30, 30, 60), border=(99, 102, 241), radius=14, width=2)
draw_text_centered(1390, 2185, [
    "⚡ 5-MIYA: GEMINI PRO",
    "Gemini 2.5 Flash / Pro",
    "-------------------------",
    "• 1M Token ulkan kontekst",
    "• Rasmlar va skrinshotlar OCR",
    "• Katta repozitoriya tahlili",
    "• So'nggi 'Temir Zaxira'",
    "• Groq tugaganda qutqaruvchi",
    "• Google AI Multimodal"
], [font_node_bold, font_node, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(165, 180, 252), (255, 255, 255), (100, 116, 139), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184), (52, 211, 153)])

# Arrows from Decision to Brains
draw_arrow((640, 1940), (230, 2030), color=(56, 189, 248), label="O'quvchi kodi", label_side="left")
draw_arrow((720, 1960), (520, 2030), color=(168, 85, 247), label="Mentor 'ai'", label_side="left")
draw_arrow((800, 1960), (810, 2030), color=(52, 211, 153), label="Zaxira ehtiyoji", label_side="right")
draw_arrow((880, 1960), (1100, 2030), color=(251, 191, 36), label="Fon tahlili", label_side="right")
draw_arrow((960, 1940), (1390, 2030), color=(99, 102, 241), label="Rasm/Katta fayl", label_side="right")

# Cascade Arrow Box
casc_box = (200, 2400, 1400, 2550)
draw_card(casc_box, fill=(15, 23, 42, 220), border=(236, 72, 153), radius=14, width=1)
draw_text_centered(800, 2475, [
    "⛓️ AVTOMATIK FALBACK VA KASKAD ALMASHISH (ZERO-DOWNTIME CASCADE)",
    "Har bir miyada 4 bosqichli kaskad: 120B Asosiy ➔ 20B Zaxira 1 ➔ Qwen-27B Zaxira 2 ➔ Gemini 1M Temir Zaxira",
    "Barcha 48+ ta Groq kalitlari 5 ta mustaqil jamoaga ajratilgan. Bironta so'rov javobsiz yoki xatoliksiz qolmaydi!"
], [font_node_bold, font_node, font_node_sm], [(236, 72, 153), (255, 255, 255), (148, 163, 184)])

# =========================================================================
# 6-BOSQICH: NATIJA, CHIQISH VA ESKALATSIYA (DUAL OUTPUT & ESCALATION)
# =========================================================================
s6_box = (60, 2635, WIDTH - 60, 3320)
draw_card(s6_box, fill=(15, 23, 42, 160), border=(52, 211, 153), radius=16, width=2)
draw.text((s6_box[0] + 25, s6_box[1] + 18), "6. NATIJA, CHIQISH VA AVTOMATIK ESKALATSIYA (DUAL OUTPUT & RESILIENCE)", font=font_stage_title, fill=(52, 211, 153))

draw_arrow((800, 2550), (800, 2680), color=(52, 211, 153))

# Decision: Natija qayerga chiqadi?
d_out = (800, 2720)
draw_diamond(d_out[0], d_out[1], 340, 80, fill=(30, 41, 59), border=(52, 211, 153), width=2)
draw_text_centered(d_out[0], d_out[1], ["Javob Turi va Eskalatsiya Tahlili", "O'quvchiga yo'l-yo'riqmi yoki Mentor nazoratimi?"], [font_node_bold, font_node_sm], [(255, 255, 255), (148, 163, 184)])

# Output 1: Telegram O'quvchi
out1_box = (150, 2830, 600, 2980)
draw_card(out1_box, fill=(16, 185, 129, 30), border=(52, 211, 153), radius=14, width=2)
draw_text_centered(375, 2905, [
    "📱 TELEGRAM: O'QUVCHIGA JAVOB",
    "• Tushunarli pedagogik yo'nalish",
    "• Xatolik joyini ko'rsatish va savollar",
    "• Agar mentor chaqirsa: 'Ustozga yetkazdim'",
    "• >4000 belgi bo'lsa xavfsiz bo'lib chiqarish",
    "• BOT_SENT_MESSAGE_IDS orqali loopdan himoya"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(52, 211, 153), (255, 255, 255), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

# Output 2: Vazifalar guruhi (Eskalatsiya)
out2_box = (1000, 2830, 1450, 2980)
draw_card(out2_box, fill=(40, 25, 45), border=(236, 72, 153), radius=14, width=2)
draw_text_centered(1225, 2905, [
    "📋 VAZIFALAR GURUHI: ESKALATSIYA",
    "• 📍 Manba: Lichka yoki Guruh nomi",
    "• 👤 O'quvchi: Ismi, username, ID",
    "• ⏰ Vaqt: Toshkent aniq vaqti",
    "• 📁 Biriktirilgan materiallar (DOCX, IPYNB, Rasm)",
    "• 📜 Suhbat Konteksti: So'nggi 5-6 xabar xulosasi",
    "• 🤖 AI tavsiyasi va mentor nazorati"
], [font_node_bold, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm, font_node_sm],
[(244, 114, 182), (255, 255, 255), (203, 213, 225), (203, 213, 225), (203, 213, 225), (203, 213, 225), (148, 163, 184)])

draw_arrow((650, 2720), (375, 2830), color=(52, 211, 153), label="O'quvchiga to'g'ridan-to'g'ri", label_side="left")
draw_arrow((950, 2720), (1225, 2830), color=(236, 72, 153), label="Eskalatsiya sharti bajarilganda", label_side="right")

# Bottom Bar: UptimeRobot & Healthcheck
stat_box = (150, 3040, 1450, 3260)
draw_card(stat_box, fill=(20, 25, 45), border=(56, 189, 248), radius=14, width=2)
draw_text_centered(800, 3150, [
    "🛡️ 24/7 BARQARORLIK VA UPTIMEROBOT KOGNITIV INTEGRATSIYASI",
    "--------------------------------------------------------------------------------------------------------------------------------",
    "• ⚡ 0.001s Keshli Healthcheck: UptimeRobot pinglari Telegram RPC'ni kutmaydi, lahzada 200 OK qaytaradi (Timeout 0%).",
    "• 🧹 Avtomatik Xotira Tozalash (gc.collect): Har 4 daqiqada o'lik keshlar tozalanadi, RAM doim < 250MB (512MB limitdan xavfsiz).",
    "• 🌐 Tashqi Render Keep-Alive: Render'ning 15 daqiqalik uxlab qolish (spin-down) mexanizmi butunlay bartaraf etilgan.",
    "• 🔄 Baza Avto-Tiklash: Qayta ishga tushganda eng so'nggi zaxira bazani Telegramdan yuklab, barcha xotiralarni to'liq tiklaydi."
], [font_node_bold, font_node_sm, font_node, font_node, font_node, font_node],
[(56, 189, 248), (100, 116, 139), (255, 255, 255), (203, 213, 225), (203, 213, 225), (52, 211, 153)])

# Save image
output_path = "/Applications/Project/coddyHelper/toliq_miya_sxemasi.png"
img.save(output_path, "PNG", optimize=True)
print(f"🎉 Rasm muvaffaqiyatli saqlandi: {output_path}")
