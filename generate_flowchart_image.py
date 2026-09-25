#!/usr/bin/env python3
"""
Generates the complete 6-stage CoddyHelper Agent Mermaid Architecture Diagram as a high-resolution PNG image.
"""
import math
from PIL import Image, ImageDraw, ImageFont

# Canvas Configuration
WIDTH = 1440
HEIGHT = 3500
BG_COLOR = (11, 15, 25)  # #0b0f19

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

try:
    font_title = ImageFont.truetype(FONT_BOLD_PATH, 28)
    font_subtitle = ImageFont.truetype(FONT_PATH, 16)
    font_stage = ImageFont.truetype(FONT_BOLD_PATH, 20)
    font_node_bold = ImageFont.truetype(FONT_BOLD_PATH, 15)
    font_node = ImageFont.truetype(FONT_PATH, 14)
    font_node_sm = ImageFont.truetype(FONT_PATH, 12)
    font_edge = ImageFont.truetype(FONT_BOLD_PATH, 13)
except Exception:
    font_title = font_subtitle = font_stage = font_node_bold = font_node = font_node_sm = font_edge = ImageFont.load_default()

img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG_COLOR, 255))
draw = ImageDraw.Draw(img)

# Helper: Draw rounded card
def draw_card(box, fill, border, radius=12, width=2):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=border, width=width)

# Helper: Draw diamond (rhombus)
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

# Helper: Draw multiline text centered
def draw_centered_text(cx, cy, lines, fonts, colors, line_spacing=4):
    total_h = 0
    line_metrics = []
    for line, font in zip(lines, fonts):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_metrics.append((w, h))
        total_h += h
    total_h += (len(lines) - 1) * line_spacing

    curr_y = cy - total_h // 2
    for (line, font), (w, h), color in zip(zip(lines, fonts), line_metrics, colors):
        draw.text((cx - w // 2, curr_y), line, font=font, fill=color)
        curr_y += h + line_spacing

# Helper: Draw arrow line
def draw_arrow(points, color=(148, 163, 184), width=2, arrow_size=8):
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=width)
    p_last = points[-1]
    p_prev = points[-2]
    dx = p_last[0] - p_prev[0]
    dy = p_last[1] - p_prev[1]
    angle = math.atan2(dy, dx)
    p1 = (p_last[0] - arrow_size * math.cos(angle - math.pi / 6),
          p_last[1] - arrow_size * math.sin(angle - math.pi / 6))
    p2 = (p_last[0] - arrow_size * math.cos(angle + math.pi / 6),
          p_last[1] - arrow_size * math.sin(angle + math.pi / 6))
    draw.polygon([p_last, p1, p2], fill=color)

# Draw Edge Label with background pill
def draw_edge_label(x, y, text, color=(248, 250, 252), bg=(30, 41, 59)):
    bbox = draw.textbbox((0, 0), text, font=font_edge)
    w = bbox[2] - bbox[0] + 16
    h = bbox[3] - bbox[1] + 8
    draw.rounded_rectangle([x - w // 2, y - h // 2, x + w // 2, y + h // 2], radius=6, fill=bg, outline=(71, 85, 105), width=1)
    draw.text((x - (bbox[2] - bbox[0]) // 2, y - (bbox[3] - bbox[1]) // 2 - 1), text, font=font_edge, fill=color)

# Draw Subgraph Box
def draw_subgraph(box, title, border_color=(71, 85, 105)):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=(15, 23, 42, 180), outline=border_color, width=2)
    # Header bar
    draw.rounded_rectangle([x0, y0, x1, y0 + 44], radius=16, fill=(30, 41, 59, 230))
    draw.text((x0 + 20, y0 + 12), title, font=font_stage, fill=border_color)

# ----------------- MAIN TITLE -----------------
draw_card([60, 30, WIDTH - 60, 115], fill=(30, 27, 75, 220), border=(129, 140, 248), radius=16, width=2)
draw.text((85, 45), "CoddyHelper — Agent Miya Strukturasi va Ishlash Mexanizmi", font=font_title, fill=(255, 255, 255))
draw.text((85, 82), "Telegram Ingestion  ->  4 Pog'onali Qalqon  ->  Agregator  ->  5 ta Miya  ->  Vaqtli Xotira  ->  Chiqish", font=font_subtitle, fill=(203, 213, 225))

# ================= 1. TELEGRAM INGESTION =================
draw_subgraph([80, 140, WIDTH - 80, 420], "1. Xabar Kirib Kelishi (Telegram Ingestion)", border_color=(56, 189, 248))

# Node A1: Telegram'dan yangi hodisa
draw_card([520, 195, 920, 250], fill=(30, 41, 59), border=(56, 189, 248), radius=10)
draw_centered_text(720, 222, ["Telegram'dan yangi hodisa (event)"], [font_node_bold], [(241, 245, 249)])

# Diamond A2: Xabar qayerdan keldi?
draw_diamond(720, 310, 240, 80, fill=(30, 41, 59), border=(56, 189, 248))
draw_centered_text(720, 310, ["Xabar qayerdan keldi?"], [font_node_bold], [(255, 255, 255)])

# Arrow A1 -> A2
draw_arrow([(720, 250), (720, 270)], color=(56, 189, 248))

# Node A3: Lichka oqimi
draw_card([240, 360, 560, 405], fill=(15, 118, 110, 160), border=(20, 184, 166), radius=10)
draw_centered_text(400, 382, ["Lichka (Shaxsiy chat) -> To'g'ridan-to'g'ri"], [font_node_bold], [(204, 251, 241)])

# Node B1: Guruh oqimi
draw_card([880, 360, 1200, 405], fill=(67, 56, 202, 160), border=(129, 140, 248), radius=10)
draw_centered_text(1040, 382, ["Guruh (O'quvchilar chati) -> Qalqonga"], [font_node_bold], [(224, 231, 255)])

# Arrows A2 -> A3 and A2 -> B1
draw_arrow([(600, 310), (400, 310), (400, 360)], color=(20, 184, 166))
draw_edge_label(490, 295, "Lichka", color=(45, 212, 191), bg=(19, 78, 74))

draw_arrow([(840, 310), (1040, 310), (1040, 360)], color=(129, 140, 248))
draw_edge_label(950, 295, "Guruh", color=(165, 180, 252), bg=(49, 46, 129))

# ================= 2. KOGNITIV GURUH QALQONI =================
draw_subgraph([80, 450, WIDTH - 80, 1490], "2. Kognitiv Guruh Qalqoni (4 Pog'onali Filtrlash)", border_color=(192, 132, 252))

# Arrow B1 into Stage 2
draw_arrow([(1040, 405), (1040, 480), (720, 480), (720, 500)], color=(192, 132, 252))

# Diamond C1: 1-Pog'ona: Xavfli fayl yoki Botga reply bormi?
draw_diamond(720, 545, 420, 90, fill=(30, 41, 59), border=(192, 132, 252))
draw_centered_text(720, 545, ["1-Pog'ona: Xavfli fayl yoki", "Botga to'g'ridan-to'g'ri reply bormi?"], [font_node_bold, font_node], [(255, 255, 255), (226, 232, 240)])

# Diamond C2: 2-Pog'ona: Ustozga murojaat bormi?
draw_diamond(720, 700, 460, 100, fill=(30, 41, 59), border=(56, 189, 248))
draw_centered_text(720, 700, ["2-Pog'ona: Ustozga murojaat bormi?", "('Ustoz', 'Nuriddin aka', '@mentor_cc', 'ko'rib bering')"], [font_node_bold, font_node_sm], [(56, 189, 248), (203, 213, 225)])

# Arrow C1 -> C2 (Yo'q)
draw_arrow([(720, 590), (720, 650)], color=(148, 163, 184))
draw_edge_label(755, 620, "Yo'q", color=(203, 213, 225))

# Diamond C3: 3-Pog'ona: O'quvchilar o'zaro gaplashyaptimi?
draw_diamond(720, 875, 480, 110, fill=(69, 10, 10, 220), border=(239, 68, 68))
draw_centered_text(720, 875, ["3-Pog'ona: O'quvchilar o'zaro gaplashyaptimi?", "(Boshqa o'quvchiga reply / 'sanda', 'bro', 'tashavor', 'ko'rchi')"], [font_node_bold, font_node_sm], [(254, 202, 202), (252, 165, 165)])

# Arrow C2 -> C3 (Yo'q)
draw_arrow([(720, 750), (720, 820)], color=(148, 163, 184))
draw_edge_label(755, 785, "Yo'q", color=(203, 213, 225))

# Diamond C4: Mavzu dasturlash/kodga doirmi?
draw_diamond(720, 1045, 460, 95, fill=(30, 41, 59), border=(192, 132, 252))
draw_centered_text(720, 1045, ["Mavzu dasturlash yoki IT kodga doirmi?", "(Off-topic suhbat: futbol, CS, kino, ob-havo)"], [font_node_bold, font_node_sm], [(255, 255, 255), (203, 213, 225)])

# Arrow C3 -> C4 (Yo'q)
draw_arrow([(720, 930), (720, 998)], color=(148, 163, 184))
draw_edge_label(755, 965, "Yo'q", color=(203, 213, 225))

# Node C5: 4-Pog'ona: Sokratik 12s kutish oynasi
draw_card([500, 1150, 940, 1205], fill=(69, 26, 3, 220), border=(245, 158, 11), radius=10)
draw_centered_text(720, 1177, ["4-Pog'ona: Sokratik 12 soniya kutish oynasi", "(Umumiy kod savoli — bolalar bir-biriga yordam berishiga imkon)"], [font_node_bold, font_node_sm], [(254, 240, 138), (253, 224, 71)])

# Arrow C4 -> C5 (Ha)
draw_arrow([(720, 1092), (720, 1150)], color=(245, 158, 11))
draw_edge_label(765, 1120, "Ha (Kod)", color=(253, 224, 71), bg=(69, 26, 3))

# Diamond C6: 12s ichida boshqa o'quvchi javob berdimi?
draw_diamond(720, 1285, 440, 90, fill=(30, 41, 59), border=(245, 158, 11))
draw_centered_text(720, 1285, ["12s ichida boshqa o'quvchi javob berdimi?", "(Tengdosh yechim topdimi?)"], [font_node_bold, font_node_sm], [(254, 240, 138), (226, 232, 240)])

# Arrow C5 -> C6
draw_arrow([(720, 1205), (720, 1240)], color=(245, 158, 11))

# TARGET 1: AI JIM TURADI (Red stop block)
draw_card([1000, 1390, 1300, 1465], fill=(127, 29, 29, 240), border=(239, 68, 68), radius=12, width=2)
draw_centered_text(1150, 1427, ["[STOP] AI JIM TURADI", "(O'quvchilar suhbatiga aralashmaydi)"], [font_node_bold, font_node_sm], [(254, 202, 202), (252, 165, 165)])

# Connections into "AI JIM TURADI":
# From C3 (Ha - Peer chat) -> AI JIM TURADI
draw_arrow([(960, 875), (1150, 875), (1150, 1390)], color=(239, 68, 68))
draw_edge_label(1050, 855, "Ha (Tengdosh suhbati)", color=(254, 202, 202), bg=(127, 29, 29))

# From C4 (Yo'q - Off-topic) -> AI JIM TURADI
draw_arrow([(950, 1045), (1120, 1045), (1120, 1390)], color=(239, 68, 68))
draw_edge_label(1035, 1025, "Yo'q (CS / Futbol)", color=(254, 202, 202), bg=(127, 29, 29))

# From C6 (Ha - Peer answered) -> AI JIM TURADI
draw_arrow([(940, 1285), (1090, 1285), (1090, 1390)], color=(239, 68, 68))
draw_edge_label(1015, 1265, "Ha (Tengdosh yechdi)", color=(254, 202, 202), bg=(127, 29, 29))

# TARGET 2: XABAR QABUL QILINDI (Green success block)
draw_card([220, 1390, 520, 1465], fill=(6, 78, 59, 240), border=(16, 185, 129), radius=12, width=2)
draw_centered_text(370, 1427, ["Xabar qabul qilindi [OK]", "(AI to'liq ishlov beradi)"], [font_node_bold, font_node_sm], [(167, 243, 208), (209, 250, 229)])

# Connections into "Xabar qabul qilindi":
# From C1 (Ha - dangerous or bot reply)
draw_arrow([(510, 545), (200, 545), (200, 1425), (220, 1425)], color=(16, 185, 129))
draw_edge_label(330, 530, "Ha (Reply / Skript)", color=(167, 243, 208), bg=(6, 78, 59))

# From C2 (Ha - Ustoz called)
draw_arrow([(490, 700), (250, 700), (250, 1390)], color=(16, 185, 129))
draw_edge_label(360, 680, "Ha (Ustoz chaqirildi)", color=(167, 243, 208), bg=(6, 78, 59))

# From C6 (Yo'q - no peer answered)
draw_arrow([(500, 1285), (370, 1285), (370, 1390)], color=(16, 185, 129))
draw_edge_label(430, 1265, "Yo'q (Hech kim bilmadi)", color=(167, 243, 208), bg=(6, 78, 59))

# Also Lichka A3 connects straight to "Xabar qabul qilindi"
draw_arrow([(400, 405), (400, 440), (160, 440), (160, 1445), (220, 1445)], color=(20, 184, 166))

# ================= 3. XABARLAR AGREGATORI =================
draw_subgraph([80, 1520, WIDTH - 80, 1920], "3. Xabarlar Agregatori (MESSAGE_ACCUMULATOR)", border_color=(245, 158, 11))

# Arrow from Stage 2 into Stage 3
draw_arrow([(370, 1465), (370, 1550), (720, 1550), (720, 1570)], color=(245, 158, 11))

# Node E1: O'quvchi bo'lib yozishini kutish
draw_card([460, 1570, 980, 1625], fill=(30, 41, 59), border=(245, 158, 11), radius=10)
draw_centered_text(720, 1597, ["O'quvchi bo'lib-bo'lib yozishini kutish (5 soniya)", "Har bir yangi kelgan xabar taymerni qayta boshlaydi"], [font_node_bold, font_node_sm], [(254, 240, 138), (203, 213, 225)])

# Diamond E2: Yana qo'shimcha xabar yozdimi?
draw_diamond(720, 1695, 360, 80, fill=(30, 41, 59), border=(245, 158, 11))
draw_centered_text(720, 1695, ["Yana qo'shimcha xabar yozdimi?"], [font_node_bold], [(255, 255, 255)])

# Arrow E1 -> E2
draw_arrow([(720, 1625), (720, 1655)], color=(245, 158, 11))

# Node E3: Loop box
draw_card([970, 1670, 1320, 1720], fill=(69, 26, 3, 220), border=(245, 158, 11), radius=8)
draw_centered_text(1145, 1695, ["Yangi xabarni buferga qo'shish va taymerni qayta yoqish"], [font_node_sm], [(254, 240, 138)])

# Arrow E2 -> E3 (Ha) and loop back to E1
draw_arrow([(900, 1695), (970, 1695)], color=(245, 158, 11))
draw_edge_label(935, 1675, "Ha", color=(254, 240, 138), bg=(69, 26, 3))
draw_arrow([(1145, 1670), (1145, 1597), (980, 1597)], color=(245, 158, 11))

# Node E4: Yaxlit bitta savolga birlashtirish
draw_card([460, 1800, 980, 1860], fill=(6, 78, 59, 220), border=(16, 185, 129), radius=10)
draw_centered_text(720, 1830, ["Barcha bo'lingan xabarlarni yaxlit 1 ta savolga birlashtirish", "Xabar matni, skrinshot va fayllar bitta so'rov paketiga yig'iladi"], [font_node_bold, font_node_sm], [(167, 243, 208), (209, 250, 229)])

# Arrow E2 -> E4 (Yo'q)
draw_arrow([(720, 1735), (720, 1800)], color=(16, 185, 129))
draw_edge_label(765, 1765, "Yo'q (5s tugadi)", color=(167, 243, 208), bg=(6, 78, 59))

# ================= 4. XOTIRA VA KONTEKST =================
draw_subgraph([80, 1950, WIDTH - 80, 2250], "4. Xotira va Kontekstni Boyitish (Dual Memory)", border_color=(16, 185, 129))

# Arrow from Stage 3 into Stage 4
draw_arrow([(720, 1860), (720, 1990)], color=(16, 185, 129))

# Node M1: SQLite
draw_card([160, 2010, 640, 2090], fill=(6, 78, 59, 180), border=(52, 211, 153), radius=10)
draw_centered_text(400, 2050, ["SQLite: Oxirgi suhbatlarni olish", "Toshkent vaqti [HH:MM] tamg'asi bilan (Dual Memory)"], [font_node_bold, font_node_sm], [(167, 243, 208), (209, 250, 229)])

# Node M2: MongoDB
draw_card([800, 2010, 1280, 2090], fill=(6, 78, 59, 180), border=(52, 211, 153), radius=10)
draw_centered_text(1040, 2050, ["MongoDB Atlas: Talaba profili & Dars darajasi", "O'zlashtirish tezligi va oldindan hisoblangan kesh"], [font_node_bold, font_node_sm], [(167, 243, 208), (209, 250, 229)])

# Split arrow E4 to M1 and M2
draw_arrow([(720, 1990), (400, 1990), (400, 2010)], color=(52, 211, 153))
draw_arrow([(720, 1990), (1040, 1990), (1040, 2010)], color=(52, 211, 153))

# Node M3: Yaxlit boyitilgan so'rov paketi
draw_card([440, 2150, 1000, 2210], fill=(30, 27, 75, 240), border=(129, 140, 248), radius=10)
draw_centered_text(720, 2180, ["Yaxlit boyitilgan so'rov paketi (Rich Context Packet)", "Xabar + Skrinshot + [HH:MM] suhbat tarixi + Talaba profili"], [font_node_bold, font_node_sm], [(224, 231, 255), (199, 210, 254)])

# Arrows M1, M2 -> M3
draw_arrow([(400, 2090), (400, 2180), (440, 2180)], color=(52, 211, 153))
draw_arrow([(1040, 2090), (1040, 2180), (1000, 2180)], color=(52, 211, 153))

# ================= 5. MIYA MARSHRUTIZATORI =================
draw_subgraph([80, 2280, WIDTH - 80, 2800], "5. Miya Marshrutizatori (5 Core Brains)", border_color=(129, 140, 248))

# Arrow Stage 4 into Stage 5
draw_arrow([(720, 2210), (720, 2320)], color=(129, 140, 248))

# Diamond R1: So'rov turini aniqlash
draw_diamond(720, 2360, 320, 80, fill=(30, 41, 59), border=(129, 140, 248))
draw_centered_text(720, 2360, ["So'rov turini aniqlash"], [font_node_bold], [(255, 255, 255)])

# Brain 3: Vision OCR
draw_card([110, 2480, 350, 2555], fill=(30, 41, 59), border=(192, 132, 252), radius=10)
draw_centered_text(230, 2517, ["3-Miya: Gemini Vision OCR", "(Rasmdan kodni o'qish)"], [font_node_bold, font_node_sm], [(192, 132, 252), (203, 213, 225)])

# Brain 3: Groq Whisper
draw_card([370, 2480, 610, 2555], fill=(30, 41, 59), border=(192, 132, 252), radius=10)
draw_centered_text(490, 2517, ["3-Miya: Groq Whisper", "(Ovozni matnga o'girish)"], [font_node_bold, font_node_sm], [(192, 132, 252), (203, 213, 225)])

# Brain 1: Groq 70B Socratic Mentor
draw_card([500, 2630, 940, 2715], fill=(15, 23, 42), border=(56, 189, 248), radius=12, width=2)
draw_centered_text(720, 2672, ["1-Miya: Groq LLaMA-3.3 70B (Sokratik Mentor)", "Tayyor yechim bermaydi, savollar orqali xatosini o'ziga topdiradi"], [font_node_bold, font_node_sm], [(56, 189, 248), (203, 213, 225)])

# Brain 2: Gemini 2.5 Pro (VIP / Deep)
draw_card([830, 2480, 1070, 2555], fill=(30, 41, 59), border=(251, 191, 36), radius=10)
draw_centered_text(950, 2517, ["2-Miya: Gemini 2.5 Pro", "(Murakkab arxitektura & DB)"], [font_node_bold, font_node_sm], [(251, 191, 36), (203, 213, 225)])

# Brain 5: Autonomous Escalation
draw_card([1090, 2480, 1330, 2555], fill=(30, 41, 59), border=(52, 211, 153), radius=10)
draw_centered_text(1210, 2517, ["5-Miya: Avtonom Eskalatsiya", "(Darsdan tashqari savollar)"], [font_node_bold, font_node_sm], [(52, 211, 153), (203, 213, 225)])

# Branches from R1 to Brains:
# To Vision
draw_arrow([(560, 2360), (230, 2360), (230, 2480)], color=(192, 132, 252))
draw_edge_label(230, 2435, "Rasm / Skrinshot", color=(192, 132, 252))

# To Whisper
draw_arrow([(600, 2380), (490, 2380), (490, 2480)], color=(192, 132, 252))
draw_edge_label(490, 2435, "Ovoz (Voice)", color=(192, 132, 252))

# To Socratic Groq
draw_arrow([(720, 2400), (720, 2630)], color=(56, 189, 248))
draw_edge_label(720, 2510, "Kod xatosi / Savol", color=(56, 189, 248))

# Vision and Whisper feed into Socratic Groq
draw_arrow([(230, 2555), (230, 2672), (500, 2672)], color=(192, 132, 252))
draw_arrow([(490, 2555), (490, 2672), (500, 2672)], color=(192, 132, 252))

# To Gemini VIP
draw_arrow([(840, 2380), (950, 2380), (950, 2480)], color=(251, 191, 36))
draw_edge_label(950, 2435, "Murakkab / Admin", color=(251, 191, 36))

# To Escalation
draw_arrow([(880, 2360), (1210, 2360), (1210, 2480)], color=(52, 211, 153))
draw_edge_label(1210, 2435, "Darsdan tashqari", color=(52, 211, 153))

# ================= 6. HARAKAT VA CHIQISH =================
draw_subgraph([80, 2830, WIDTH - 80, 3350], "6. Harakat va Chiqish (Dual Output)", border_color=(244, 114, 182))

# Student Output
draw_card([120, 2900, 580, 2985], fill=(131, 24, 67, 180), border=(244, 114, 182), radius=10)
draw_centered_text(350, 2942, ["Telegram: O'quvchiga Sokratik yo'naltiruvchi javob", "Tayyor kod emas, xatosini o'zi topishiga yordam beradi"], [font_node_bold, font_node_sm], [(251, 207, 232), (252, 231, 243)])

# Out-of-scope response to Student
draw_card([620, 2900, 960, 2985], fill=(131, 24, 67, 180), border=(244, 114, 182), radius=10)
draw_centered_text(790, 2942, ["Telegram: O'quvchiga muloyim javob:", "'Xabaringiz Ustozga yetkazildi'"], [font_node_bold, font_node_sm], [(251, 207, 232), (252, 231, 243)])

# Vazifalar group card
draw_card([1000, 2900, 1340, 2985], fill=(131, 24, 67, 180), border=(244, 114, 182), radius=10)
draw_centered_text(1170, 2942, ["Vazifalar Guruhi: Nazorat kartochkasi", "Ustoz darhol tekshirishi uchun to'liq ma'lumot"], [font_node_bold, font_node_sm], [(251, 207, 232), (252, 231, 243)])

# Connections from Brains to Outputs:
# Brain 1 (Socratic) & Brain 2 (VIP) -> Student Output
draw_arrow([(650, 2715), (650, 2850), (350, 2850), (350, 2900)], color=(244, 114, 182))
draw_arrow([(950, 2555), (950, 2850), (350, 2850)], color=(244, 114, 182))

# Brain 5 (Escalation) -> Both notice and Vazifalar
draw_arrow([(1210, 2555), (1210, 2850), (790, 2850), (790, 2900)], color=(244, 114, 182))
draw_arrow([(1210, 2850), (1170, 2850), (1170, 2900)], color=(244, 114, 182))

# Final DB Save Box
draw_card([440, 3090, 1000, 3160], fill=(6, 78, 59, 220), border=(16, 185, 129), radius=10)
draw_centered_text(720, 3125, ["Yangi javobni SQLite [HH:MM] va MongoDB'ga yozib qo'yish", "Keyingi muloqotlarda to'liq eslab qolish uchun xotiraga muhrlanadi"], [font_node_bold, font_node_sm], [(167, 243, 208), (209, 250, 229)])

# Arrows into Final DB Save Box
draw_arrow([(350, 2985), (350, 3040), (720, 3040), (720, 3090)], color=(16, 185, 129))
draw_arrow([(790, 2985), (790, 3040)], color=(16, 185, 129))

# Footer
draw_card([80, 3210, WIDTH - 80, 3270], fill=(15, 23, 42), border=(51, 65, 85), radius=10)
draw.text((110, 3232), "CoddyHelper Architecture • 4 Pog'onali Kognitiv Qalqon & 5-Miya Tizimi • 2026", font=font_subtitle, fill=(148, 163, 184))

# Save Image
OUT_PATH = "/Applications/Project/coddyHelper/coddyhelper_miya_sxemasi.png"
img.save(OUT_PATH, "PNG", quality=95)
print(f"Rasm muvaffaqiyatli saqlandi: {OUT_PATH}")
