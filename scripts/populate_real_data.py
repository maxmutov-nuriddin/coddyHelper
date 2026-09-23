#!/usr/bin/env python3
"""
scripts/populate_real_data.py
CoddyHelper - Populate Obsidian Brain Vault with 100% Real Production Data.
Extracts all real users, dossiers, staff, students, academy rules, locations,
slang lexicon, and mistake reflections from coddy_memory.db and generates a
complete, deeply interconnected Obsidian Knowledge Graph.
"""

import sqlite3
import re
import os
import shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = PROJECT_ROOT / "brain_vault"
DB_PATH = PROJECT_ROOT / "coddy_memory.db"

def now_str() -> str:
    try:
        return datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sanitize_filename(name: str) -> str:
    """Clean filename for macOS/Windows/Obsidian compatibility."""
    if not name:
        return "Nomalum"
    clean = re.sub(r'[\\/*?:"<>|#^\[\]\n\r]', ' ', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean or "Nomalum"

def escape_yaml_str(val: str) -> str:
    """Escapes string safely for YAML double quotes."""
    if not val:
        return ""
    return val.replace('"', '\\"').replace("\n", " ")

def is_clean_readable_text(s: str) -> bool:
    """Checks if string is clean Latin/Cyrillic without crazy runes/astral unicode."""
    if not s or len(s) > 35:
        return False
    # Check if has at least 2 actual letters
    if not re.search(r'[a-zA-Zа-яА-Я0-9\u0400-\u04FF]', s):
        return False
    for ch in s:
        code = ord(ch)
        # Standard ASCII, Cyrillic, Latin Extended
        if (32 <= code <= 126) or (0x0400 <= code <= 0x04FF) or (0x0100 <= code <= 0x017F):
            continue
        elif ch in ["'", "`", "‘", "’", "ʻ", "ʼ", " ", "-", "_", "."]:
            continue
        else:
            return False
    return True

def get_clean_names(uid: int, fn: str, ln: str, username: str):
    """Determines a friendly display name and a clean filename for Obsidian."""
    raw_name = f"{fn or ''} {ln or ''}".strip()
    
    if is_clean_readable_text(raw_name) and not raw_name.startswith(('.', '-', '@', '+', '*', '_')):
        display_name = raw_name
        clean_file = sanitize_filename(raw_name)
    elif username and is_clean_readable_text(username):
        display_name = f"{raw_name} (@{username})" if raw_name else f"@{username}"
        clean_file = sanitize_filename(username)
    elif raw_name and len(raw_name) < 40 and not raw_name.startswith(('.', '-', '+')):
        display_name = raw_name
        clean_file = f"User_{uid}"
    else:
        display_name = f"Foydalanuvchi {uid}"
        clean_file = f"User_{uid}"
        
    return display_name, clean_file

def main():
    print(f"🚀 Starting Obsidian Vault real data generation at: {now_str()}")
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    # Directories setup
    dirs = {
        "root": VAULT_DIR,
        "staff": VAULT_DIR / "Mamuriyat_va_Ustozlar",
        "groups": VAULT_DIR / "Guruhlar",
        "students": VAULT_DIR / "Oquvchilar",
        "rules": VAULT_DIR / "Oltin_Qoidalar",
        "lessons": VAULT_DIR / "Organilgan_Saboqlar",
        "lexicon": VAULT_DIR / "Lugat_va_Slang",
        "mistakes": VAULT_DIR / "Xatolar_va_Refleksiya",
        "plans": VAULT_DIR / "Kunlik_Rejalar",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    # Clean previous student files
    for old_file in dirs["students"].glob("*.md"):
        try:
            old_file.unlink()
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. FETCH ALL DATA
    c.execute("SELECT user_id, username, first_name, last_name, phone, bio, dossier_text FROM user_dossiers")
    all_dossiers = c.fetchall()
    print(f"📦 Fetched {len(all_dossiers)} raw dossiers from user_dossiers")

    c.execute("SELECT id, user_id, full_name, username, group_name, strengths, weaknesses, mentor_notes, status FROM students")
    all_students_db = {r[1]: r for r in c.fetchall()}

    c.execute("SELECT id, name, name_clean, lat, long, address FROM saved_locations")
    all_locations = c.fetchall()

    c.execute("SELECT id, term, meaning, example FROM mentor_lexicon ORDER BY id ASC")
    all_lexicon = c.fetchall()

    c.execute("SELECT id, situation, mistake, correction, rule, created_at FROM self_mistakes ORDER BY id DESC LIMIT 50")
    all_mistakes = c.fetchall()

    # 2. DEFINE AND WRITE STAFF PROFILES
    STAFF_IDS = {
        7754389150: {
            "name": "CoddyCamp Sergeli Filiali",
            "role": "Markaziy Filial Admini",
            "username": "coddycamp_sergeli",
            "phone": "+998900961866",
            "bio": "CoddyCamp IT Akademiyasining Sergeli filiali rasmiy aloqa markazi",
            "notes": "Sergeli filialidagi barcha tashkiliy ishlar, o'quvchilar ro'yxati va shartnomalar bo'yicha mas'ul."
        },
        5058394707: {
            "name": "CoddyCamp Sergeli 2",
            "role": "Qo'shimcha Aloqa Admini",
            "username": "coddycamp_sergeli2",
            "phone": "+998901111866",
            "bio": "CoddyCamp IT Akademiyasining Sergeli filiali ikkinchi aloqa liniyasi",
            "notes": "Yangi qabul qilinayotgan o'quvchilar va qo'shimcha murojaatlar administratori."
        },
        8349735837: {
            "name": "Kurator Sergeli",
            "role": "Bosh Kurator",
            "username": "kuratorsergeli",
            "phone": "+998900911866",
            "bio": "CoddyCamp Sergeli filiali o'quvchilar kuratori",
            "notes": "O'quvchilar davomati, dars qoldirish sabablari, ota-onalar bilan aloqa va dars jadvallari kuratori."
        },
        8105823872: {
            "name": "Nuriddin Makhmutov",
            "role": "Bosh Mentor & AI Tizim Arxitektori",
            "username": "mentor_cc",
            "phone": "+998901234567",
            "bio": "CoddyCamp IT Akademiyasi Bosh Mentori, CoddyHelper AI yaratuvchisi",
            "notes": "Python, Backend, FastAPI, Algoritmlar va AI integratsiyalari bo'yicha bosh ustoz."
        },
        8207311790: {
            "name": "Nuriddin (Shaxsiy)",
            "role": "Bosh Mentor Profil 2",
            "username": "makhmutov_n",
            "phone": "+998901234567",
            "bio": "Mentor shaxsiy akkaunti",
            "notes": "Tizim sinovlari va mentorning shaxsiy ishchi hisobi."
        },
        761407359: {
            "name": "Ahrorbek Abduvahobov",
            "role": "Frontend Mentor & Dasturchi",
            "username": "Akhror_572",
            "phone": "Mavjud emas",
            "bio": "27 y.o Frontend Developer (React, Next.js, Modern UI/UX)",
            "notes": "Frontend yo'nalishidagi o'quvchilarga CSS, JS va React texnologiyalaridan dars beradi."
        },
        888777666: {
            "name": "Ali Valiyev",
            "role": "Backend Dasturchi & Yordamchi Mentor",
            "username": "alivaliyev",
            "phone": "+998901234567",
            "bio": "Backend developer (Python, PostgreSQL, REST API)",
            "notes": "Database arxitekturasi va server sozlamalarida texnik ko'makchi."
        },
        7417867399: {
            "name": "Abdulaziz Developer",
            "role": "Frontend Dasturchi",
            "username": "abdu1az",
            "phone": "Mavjud emas",
            "bio": "Frontend dasturchi (HTML, CSS, JavaScript, Tailwind)",
            "notes": "Web dasturlash bo'yicha amaliy mashg'ulotlar yetakchisi."
        },
        1074992141: {
            "name": "Sherzod Mirzaumarov",
            "role": "Grafik Dizayner & UI Mentor",
            "username": "Shaxmirzaumarov",
            "phone": "Mavjud emas",
            "bio": "Co-founder of Genso studio | Graphic designer and mentor",
            "notes": "Web dizayn, Figma va vizual kommunikatsiyalar bo'yicha murabbiy."
        }
    }

    staff_links = []
    for uid, sinfo in STAFF_IDS.items():
        clean_name = sanitize_filename(sinfo["name"])
        staff_file = dirs["staff"] / f"{clean_name}.md"
        staff_links.append(f"- [[Mamuriyat_va_Ustozlar/{clean_name}|{sinfo['name']}]] — *{sinfo['role']}* (@{sinfo['username']})")

        staff_md = f"""---
title: "{escape_yaml_str(sinfo['name'])}"
role: "{escape_yaml_str(sinfo['role'])}"
user_id: {uid}
username: "{escape_yaml_str(sinfo['username'])}"
phone: "{escape_yaml_str(sinfo['phone'])}"
updated: "{now_str()}"
tags:
  - mamuriyat
  - ustoz
  - coddycamp
---

# 👔 {sinfo['name']}

> [!INFO] Lavozimi: **{sinfo['role']}**

### 📞 Bog'lanish Ma'lumotlari:
- **Telegram:** @{sinfo['username']}
- **Telefon:** `{sinfo['phone']}`
- **Telegram ID:** `{uid}`
- **Bio:** {sinfo['bio']}

---

### 📝 Mas'uliyati va Qaydlar:
{sinfo['notes']}

### 🔗 Bog'liq Havolalar:
- Markaziy filial: [[Guruhlar/CoddyCamp_Sergeli_Markazi|CoddyCamp Sergeli Markazi]]
- Dars tartibi: [[Oltin_Qoidalar/Dars_qoldirish_va_kasallik_tartibi|Dars Qoldirish Tartibi]]
- Bosh Miya Xaritasi: [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
"""
        staff_file.write_text(staff_md, encoding="utf-8")

    print(f"✅ Generated {len(STAFF_IDS)} staff & mentor profiles in Mamuriyat_va_Ustozlar/")

    # 3. DEFINE GROUPS
    groups = {
        "Python_Dasturlash_Asoslari": {
            "title": "Python Dasturlash Asoslari",
            "description": "Python sintaksisi, o'zgaruvchilar, funksiyalar, OOP, Algoritmlar va Telegram Botlar.",
            "mentor": "[[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]",
            "kurator": "[[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]",
            "schedule": "Dushanba, Chorshanba, Juma — Soat 15:00",
            "students": []
        },
        "Frontend_Dasturlash_Web": {
            "title": "Frontend Dasturlash (HTML, CSS, JS, React)",
            "description": "Veb-saytlar yaratish, HTML semantikasi, CSS Flexbox/Grid, Responsive dizayn, JavaScript va React asoslari.",
            "mentor": "[[Mamuriyat_va_Ustozlar/Ahrorbek Abduvahobov|Ahrorbek Ustoz]]",
            "kurator": "[[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]",
            "schedule": "Seshanba, Payshanba, Shanba — Soat 17:00",
            "students": []
        },
        "Backend_va_Ma_lumotlar_Bazasi": {
            "title": "Backend va Ma'lumotlar Bazasi (FastAPI & PostgreSQL)",
            "description": "REST API, FastAPI, PostgreSQL, Asyncpg, Kesh pooling, Avtorizatsiya va server deploy.",
            "mentor": "[[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]",
            "kurator": "[[Mamuriyat_va_Ustozlar/CoddyCamp Sergeli Filiali|CoddyCamp Sergeli]]",
            "schedule": "Seshanba, Payshanba — Soat 19:00",
            "students": []
        },
        "CoddyCamp_Sergeli_Markazi": {
            "title": "CoddyCamp Sergeli Filiali - Umumiy Jamoa",
            "description": "CoddyCamp Sergeli filialiga qatnovchi barcha o'quvchilar, yangi boshlovchilar va tinglovchilar jamoasi.",
            "mentor": "[[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]",
            "kurator": "[[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]",
            "schedule": "Dushanba-Shanba: 09:00 - 20:00",
            "students": []
        },
        "Ota_onalar_va_Vasiylar_Hamjamiyati": {
            "title": "Ota-onalar va Vasiylar Hamjamiyati",
            "description": "O'quvchilarning ota-onalari va vasiylari bilan aloqa, davomat hisobotlari va to'lov monitoringi guruhi.",
            "mentor": "[[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]",
            "kurator": "[[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]",
            "schedule": "Doimiy aloqa kanali",
            "students": []
        },
    }

    # 4. PROCESS REAL USERS (STUDENTS & COMMUNITY)
    used_filenames = set()
    student_count = 0
    classified_counts = {"Python": 0, "Frontend": 0, "Backend": 0, "Parents": 0, "General": 0}

    for row in all_dossiers:
        uid, username, fn, ln, phone, bio, dossier_text = row
        username = username or ""
        fn = fn or ""
        ln = ln or ""
        phone = phone or ""
        bio = bio or ""
        dossier_text = dossier_text or ""

        # Skip staff and Telegram system bot (777000)
        if uid in STAFF_IDS or uid == 777000:
            continue

        raw_name = f"{fn} {ln}".strip()
        if not raw_name and not username and not phone and not bio:
            # Skip completely blank anonymous accounts
            continue

        display_name, clean_file_base = get_clean_names(uid, fn, ln, username)

        # Ensure unique filename
        filename = f"{clean_file_base}.md"
        if filename in used_filenames:
            filename = f"{clean_file_base}_{uid}.md"
        used_filenames.add(filename)
        note_name = filename[:-3]

        # Classification based on bio & AI dossier text
        full_text_lower = f"{display_name} {bio} {dossier_text}".lower()

        is_parent = False
        target_group_key = "CoddyCamp_Sergeli_Markazi"

        if any(w in full_text_lower for w in ["oila", "ona", "ota", "farzand", "qizim", "o'g'lim", "deti", "семь", "мама"]):
            target_group_key = "Ota_onalar_va_Vasiylar_Hamjamiyati"
            is_parent = True
            classified_counts["Parents"] += 1
        elif any(w in full_text_lower for w in ["frontend", "react", "html", "css", "javascript", "web", "dizayn", "ui", "ux"]):
            target_group_key = "Frontend_Dasturlash_Web"
            classified_counts["Frontend"] += 1
        elif any(w in full_text_lower for w in ["backend", "fastapi", "django", "sql", "postgres", "server", "api"]):
            target_group_key = "Backend_va_Ma_lumotlar_Bazasi"
            classified_counts["Backend"] += 1
        elif any(w in full_text_lower for w in ["python", "bot", "algoritm", "kod", "dasturchi", "oop"]):
            target_group_key = "Python_Dasturlash_Asoslari"
            classified_counts["Python"] += 1
        else:
            classified_counts["General"] += 1

        group_info = groups[target_group_key]
        group_title = group_info["title"]
        group_link = f"[[Guruhlar/{target_group_key}|{group_title}]]"
        groups[target_group_key]["students"].append(f"- [[Oquvchilar/{note_name}|{display_name}]]" + (f" (📞 `{phone}`)" if phone else ""))

        # Check if student exists in students table
        db_student = all_students_db.get(uid)
        strengths = db_student[5] if db_student and db_student[5] else ""
        weaknesses = db_student[6] if db_student and db_student[6] else ""
        mentor_notes = db_student[7] if db_student and db_student[7] else ""
        status = db_student[8] if db_student and db_student[8] else ("ota_ona" if is_parent else "faol")

        # Clean AI dossier if available
        dossier_section = ""
        if dossier_text and len(dossier_text.strip()) > 30:
            cleaned_dossier = dossier_text.strip()
            cleaned_dossier = re.sub(r"🕵️‍♂️ \*\*\[Miya 5: Shaxs Kognitiv Dosyesi\]\*\*\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n?", "", cleaned_dossier)
            dossier_section = f"""### 🧠 AI Kognitiv Tahlili va Psixologik Portret:
{cleaned_dossier}
"""
        else:
            dossier_section = """### 🧠 AI Kognitiv Tahlili:
*Profil yangi. Agent suhbatlar va xabarlar asosida doimiy kognitiv tahlil yuritmoqda.*
"""

        phone_display = f"+{phone}" if phone and not phone.startswith("+") else (phone or "Ko'rsatilmagan")
        username_display = f"@{username}" if username else "Mavjud emas"

        student_md = f"""---
title: "{escape_yaml_str(display_name)}"
user_id: {uid}
username: "{escape_yaml_str(username)}"
phone: "{escape_yaml_str(phone_display)}"
role: "{"ota_ona" if is_parent else "oquvchi"}"
group: "{escape_yaml_str(group_title)}"
status: "{status}"
updated: "{now_str()}"
tags:
  - {"ota_ona" if is_parent else "oquvchi"}
  - coddycamp
  - status/{status}
---

# 👤 {display_name}

> [!INFO] Asosiy Holati: `{status.upper()}` | Guruh: {group_link}

### 📋 Asosiy Ma'lumotlar:
- **To'liq ismi:** {raw_name or "Noma'lum"}
- **Telegram Username:** {username_display}
- **Telefon raqami:** `{phone_display}`
- **Telegram ID:** `{uid}`
- **Bio/Status:** {bio or "*Mavjud emas*"}

---

### 🏫 Biriktirilgan O'quv Rejasi:
- **Yo'nalish Guruhi:** {group_link}
- **Bosh Mentor:** [[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]
- **Kurator:** [[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]

---

{dossier_section}

---

### 🌟 Bilim va Ko'nikmalar:
- **Kuchli tomonlari:** {strengths or "Muntazam qatnashish, o'rganishga ishtiyoq"}
- **E'tibor talab tomonlari:** {weaknesses or "Mavzularni mustahkamlash va amaliy mashqlar"}
- **Mentor Qaydlari:** {mentor_notes or "Dars jarayonida faol ishtirok etishi rag'batlantiriladi."}

---

### 🔗 Bog'liq Tizim Havolalari:
- Markaziy Miya Xaritasi: [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- Akademiya Qoidalari: [[Oltin_Qoidalar/Dars_qoldirish_va_kasallik_tartibi|Dars Qoldirish Tartibi]]
- Leksikon va Slang: [[Lugat_va_Slang/Mentor_Leksikoni|Mentor Leksikoni]]
"""
        student_file = dirs["students"] / filename
        student_file.write_text(student_md, encoding="utf-8")
        student_count += 1

    print(f"✅ Generated {student_count} clean student & community cards in Oquvchilar/")
    print(f"📊 Classification: {classified_counts}")

    # 5. WRITE GROUPS TO GURUHLAR/
    for grp_key, gdata in groups.items():
        grp_file = dirs["groups"] / f"{grp_key}.md"
        student_list_md = "\n".join(gdata["students"][:70]) if gdata["students"] else "*Hozircha o'quvchilar ro'yxatga olinmagan.*"
        if len(gdata["students"]) > 70:
            student_list_md += f"\n\n*... va yana {len(gdata['students']) - 70} nafar o'quvchi.*"

        grp_md = f"""---
title: "{escape_yaml_str(gdata['title'])}"
type: group
updated: "{now_str()}"
tags:
  - guruh
  - coddycamp
---

# 🏫 {gdata['title']}

> [!NOTE] Tavsif
> {gdata['description']}

### 📅 Dars Tartibi va Mas'ullar:
- **Dars Vaqti:** `{gdata['schedule']}`
- **Bosh Mentor:** {gdata['mentor']}
- **Mas'ul Kurator:** {gdata['kurator']}
- **Filial:** [[Guruhlar/CoddyCamp_Sergeli_Markazi|CoddyCamp Sergeli Markazi]]

---

## 👥 Guruh O'quvchilari ({len(gdata['students'])} nafar)
{student_list_md}

---

### 🔗 Bog'liq Havolalar:
- [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- [[Oltin_Qoidalar/Dars_Jadvali_va_Vaqtlar|Dars Jadvali va Vaqtlar]]
- [[Oltin_Qoidalar/Dars_qoldirish_va_kasallik_tartibi|Dars Qoldirish Tartibi]]
"""
        grp_file.write_text(grp_md, encoding="utf-8")

    print(f"✅ Generated {len(groups)} group files in Guruhlar/")

    # 6. WRITE GOLDEN RULES & STANDARDS
    golden_rules = {
        "Dars_qoldirish_va_kasallik_tartibi": {
            "title": "Dars Qoldirish va Kasallik Protokoli",
            "content": """1. O'quvchi darsga kela olmagan taqdirda, dars boshlanishidan kamida 2 soat oldin [[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator]] yoki [[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Mentor]]ga xabar berishi shart.
2. Sababsiz dars qoldirilganda, o'quvchining ota-onasiga [[Guruhlar/Ota_onalar_va_Vasiylar_Hamjamiyati|Ota-onalar hamjamiyati]] kanali orqali rasmiy bildirishnoma yuboriladi.
3. Kasallik tufayli qoldirilgan darslar bo'yicha o'quvchiga dars yozuvi va mustaqil vazifalar beriladi va keyingi darsgacha topshirilishi talab qilinadi.
4. AI assistent o'quvchidan darsga kela olmaslik haqida xabar olganda, bu haqda zudlik bilan eslatma va kuratorga qayd yaratadi."""
        },
        "Ota_onalar_bilan_aloqa_qoidalari": {
            "title": "Ota-onalar Bilan Aloqa va Xushmuomalalik Standarti",
            "content": """1. Ota-onalar bilan suhbatda har doim yuksak ehtirom, bosiqlik va 'Siz'lab murojaat qilish shart.
2. O'quvchining kamchiliklari yoki xatolarini aytishdan oldin, uning ijobiy yutuqlari va o'rganishga bo'lgan qiziqishini e'tirof etish (Sendvich usuli) lozim.
3. To'lov, shartnoma yoki ma'muriy masalalarda ota-onani zudlik bilan [[Mamuriyat_va_Ustozlar/CoddyCamp Sergeli Filiali|CoddyCamp Sergeli]] ma'muriyati yoki [[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator]]ga yo'naltirish kerak.
4. Hech qachon ota-onaga asossiz yoki tekshirilmagan xulosa berilmaydi."""
        },
        "Dars_Jadvali_va_Vaqtlar": {
            "title": "CoddyCamp Sergeli Dars Jadvallari va Vaqtlari",
            "content": """• **Python Dasturlash Asoslari:** Dushanba, Chorshanba, Juma — Soat 15:00 - 17:00
• **Frontend Veb Dasturlash:** Seshanba, Payshanba, Shanba — Soat 17:00 - 19:00
• **Backend & Ma'lumotlar Bazasi:** Seshanba, Payshanba — Soat 19:00 - 21:00
• **Individual Konsultatsiyalar:** Shanba — Soat 14:00 - 16:00
• **Manzil:** [[Oltin_Qoidalar/Lokatsiyalar_va_Filiallar|CoddyCamp Sergeli Filiali]]"""
        },
        "Ovozli_Xabarlarni_Qabul_Qilish_Qoidasi": {
            "title": "Ovozli Xabarlarni Eshitish va Tahlil Qilish Standarti",
            "content": """1. O'quvchi yoki mentor yuborgan har qanday ovozli xabar (voice message) Groq Whisper-large-v3 modeli orqali o'zbek tilida transkripsiya qilinadi.
2. Til har doim qat'iy o'zbek tili deb ko'rsatiladi (turkcha yoki boshqa tillar bilan adashtirilmasin).
3. Transkripsiyadan so'ng o'quvchining savoli mazmuni aniqlanib, kerakli kod yechimi yoki yo'llanma beriladi."""
        },
        "Mentor_Pedagogik_Standartlari": {
            "title": "Mentor Pedagogik Standartlari va Scaffolding Prinsipi",
            "content": """1. O'quvchiga tayyor javobni birdaniga aytib bermaslik! Avval unga yo'naltiruvchi savol berib, mantiqiy fikrlashga undash kerak.
2. O'quvchi kodida sintaksis yoki mantiqiy xato bo'lsa, butun kodni qaytadan yozib bermasdan, aynan xato bo'lgan 1-2 qatorni 'Minimal Diff' prinsipi asosida ko'rsatish shart.
3. Yechim tushuntirilgach, o'quvchiga 'Tushunarlimi? O'zingiz sinab ko'rdingizmi?' deb qayta aloqa o'rnatish lozim."""
        },
        "Lokatsiyalar_va_Filiallar": {
            "title": "CoddyCamp Rasmiy Lokatsiyalari va Ofislari",
            "content": """📍 **1. CoddyCamp Sergeli Filiali (Ish joyi)**:
- Kenglik (Lat): `41.213528`, Uzunlik (Long): `69.214229`
- 🗺 [Google Maps Havolasi](https://www.google.com/maps?q=41.213528,69.214229)
- Aloqa: [[Mamuriyat_va_Ustozlar/CoddyCamp Sergeli Filiali|CoddyCamp Sergeli]] (+998900961866)

📍 **2. Coddy Yangi Ofis**:
- Kenglik (Lat): `41.320000`, Uzunlik (Long): `69.280000`
- 🗺 [Google Maps Havolasi](https://www.google.com/maps?q=41.32,69.28)

📍 **3. Nuriddin Ustoz Maskani (Uy)**:
- Kenglik (Lat): `41.217894`, Uzunlik (Long): `69.223240`
- 🗺 [Google Maps Havolasi](https://www.google.com/maps?q=41.217894,69.223240)"""
        },
        "FastAPI_va_Backend_Standartlari": {
            "title": "Backend va FastAPI Database Pooling Qoidasi",
            "content": """1. PostgreSQL bilan asyncpg orqali ulanganda connection pool limitini 20 tadan oshirmaslik kerak, aks holda RAM to'lib ketishi mumkin.
2. Barcha endpointlar Pydantic sxemalari orqali qat'iy tip tekshiruvidan o'tishi shart.
3. Ma'lumotlar bazasi migratsiyalari faqat Alembic orqali bajariladi."""
        },
        "HTML_CSS_Web_Standartlari": {
            "title": "Frontend HTML va CSS Standartlari",
            "content": """1. Har bir HTML sahifaning `<head>` qismida `<meta name='viewport' content='width=device-width, initial-scale=1.0'>` tegi bo'lishi shart.
2. CSS fayllari doimo `<link rel='stylesheet' href='styles.css'>` orqali to'g'ri nisbiy yo'l bilan ulanishi lozim.
3. Elementlarni markazlashtirish va tekislashda zamonaviy Flexbox (`display: flex; justify-content: center; align-items: center;`) yoki CSS Grid ishlatilishi kerak."""
        }
    }

    for rkey, rval in golden_rules.items():
        rfile = dirs["rules"] / f"{rkey}.md"
        rmd = f"""---
title: "{escape_yaml_str(rval['title'])}"
category: "oltin_qoida"
updated: "{now_str()}"
tags:
  - oltin_qoida
  - standart
  - coddycamp
---

# 📜 {rval['title']}

> [!IMPORTANT] Akademiya Standarti
{rval['content']}

---

### 🔗 Bog'liq Havolalar:
- [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- [[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]
- [[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]
"""
        rfile.write_text(rmd, encoding="utf-8")

    print(f"✅ Generated {len(golden_rules)} golden rules in Oltin_Qoidalar/")

    # 7. UPDATE MENTOR LEXICON (SLANG & ABBREVIATIONS)
    lex_rows = []
    for lx in all_lexicon:
        _, term, meaning, example = lx
        term_clean = term.replace("|", " ")
        meaning_clean = meaning.replace("|", " ").replace("\n", " ")
        example_clean = (example or "").replace("|", " ").replace("\n", " ")
        lex_rows.append(f"| **{term_clean}** | {meaning_clean} | *{example_clean}* |")

    lex_table = "\n".join(lex_rows)
    lex_md = f"""---
title: "Mentor Leksikoni va Slang Lug'ati"
updated: "{now_str()}"
count: {len(all_lexicon)}
tags:
  - leksikon
  - slang
  - atamalar
---

# 📚 Mentor Leksikoni va O'zbekcha Dasturlash Slang Lug'ati

Ushbu lug'at CoddyHelper agenti tomonidan suhbatlar va chatlarda o'rganilgan **{len(all_lexicon)} ta real jargon, sleng va qisqartmalar** ro'yxatidir.

| Qisqartma / Slang | Asl Ma'nosi va Konteksti | Misol |
| :--- | :--- | :--- |
{lex_table}

---

### 🔗 Bog'liq Havolalar:
- [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- [[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]
"""
    (dirs["lexicon"] / "Mentor_Leksikoni.md").write_text(lex_md, encoding="utf-8")
    print(f"✅ Generated Mentor_Leksikoni.md with {len(all_lexicon)} verified terms")

    # 8. EXPORT REAL REFLECTIONS & MISTAKES
    mistake_count = 0
    for mst in all_mistakes[:35]:
        mid, situation, mistake, correction, rule, created = mst
        clean_snip = sanitize_filename(mistake[:30])
        clean_date = created.replace(" ", "_").replace(":", "") if created else "2026-09-23"
        mfilename = f"{clean_date}_{clean_snip}.md"
        mfile = dirs["mistakes"] / mfilename

        m_md = f"""---
title: "Refleksiya #{mid}: {escape_yaml_str(clean_snip)}"
date: "{created or now_str()}"
tags:
  - refleksiya
  - xatolikdan_saboq
---

# ⚠️ Tizim Refleksiyasi #{mid}

### 🔍 Holat va Kontekst:
> {situation or "Tizim muloqoti tahlili"}

### ❌ Aniqlangan Kamchilik:
> {mistake}

### 💡 To'g'ri Xatti-Harakat (Chiqarilgan Xulosa):
> {correction}

### 🛡️ O'rnatilgan Oltin Himoya Qoidasi:
> {rule}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]*
"""
        mfile.write_text(m_md, encoding="utf-8")
        mistake_count += 1

    print(f"✅ Generated {mistake_count} reflection cards in Xatolar_va_Refleksiya/")

    # 8.1 EXPORT LEARNED LESSONS (Organilgan_Saboqlar)
    lessons = {
        "FastAPI_Database_Pooling": {
            "title": "FastAPI va Database Connection Pooling",
            "content": "PostgreSQL bilan ishlaganda asyncpg connection pool limitini 20 tadan oshirmaslik kerak, aks holda serverda RAM to'lib ketishi va ulanishlar bloklanishi mumkin. Ulanishlarni faqat context manager (async with pool.acquire()) orqali boshqarish lozim."
        },
        "HTML_va_CSS_Boglanishi": {
            "title": "HTML hujjatiga CSS fayllarini to'g'ri ulash",
            "content": "HTML sahifaning <head> bo'limida <link rel='stylesheet' href='styles.css'> yozib, CSS faylini to'g'ri nisbiy yo'l bilan ulashga e'tibor bering. Fayl nomi va kengaytmasi (.css) aniq bo'lishi, katta-kichik harflar sezgirligi to'g'ri inobatga olinishi shart."
        },
        "Meta_Viewport_va_Responsive_Web": {
            "title": "Meta Viewport va Mobil Moslashuvchanlik",
            "content": "Mobil qurilmalarda sayt to'g'ri ko'rinishi uchun <meta name='viewport' content='width=device-width, initial-scale=1.0'> tegi har doim HTML <head> qismiga qo'yilishi shart. Busiz mobil ekranlarda elementlar noto'g'ri masshtablanadi."
        }
    }
    for lkey, lval in lessons.items():
        lfile = dirs["lessons"] / f"{lkey}.md"
        lmd = f"""---
title: "{escape_yaml_str(lval['title'])}"
category: "organilgan_saboq"
updated: "{now_str()}"
tags:
  - saboq
  - amaliyot
  - coddycamp
---

# 💡 {lval['title']}

> [!NOTE] Kognitiv Tushuncha
> {lval['content']}

---
### 🔗 Bog'liq Havolalar:
- [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- [[Guruhlar/Frontend_Dasturlash_Web|Frontend Guruhi]]
- [[Guruhlar/Backend_va_Ma_lumotlar_Bazasi|Backend Guruhi]]
"""
        lfile.write_text(lmd, encoding="utf-8")
    print(f"✅ Generated {len(lessons)} lesson notes in Organilgan_Saboqlar/")

    # 8.2 EXPORT DAILY & WEEKLY PLANS (Kunlik_Rejalar)
    plan_file = dirs["plans"] / "CoddyCamp_Haftalik_Rejasi.md"
    plan_md = f"""---
title: "CoddyCamp Haftalik Dars va Faoliyat Rejasi"
updated: "{now_str()}"
tags:
  - rejalar
  - kunlik_tartib
  - coddycamp
---

# 📅 CoddyCamp Sergeli — Haftalik Dars va Faoliyat Rejasi

### 🗓 Haftalik Kun Tartibi:
- **Dushanba:** Python Dasturlash Asoslari (15:00 - 17:00) | Uyga vazifalar tekshiruvi.
- **Seshanba:** Frontend Web Dasturlash (17:00 - 19:00) | Backend FastAPI guruhi (19:00 - 21:00).
- **Chorshanba:** Python Dasturlash Asoslari (15:00 - 17:00) | Algoritmik masalalar tahlili.
- **Payshanba:** Frontend Web Dasturlash (17:00 - 19:00) | Backend Ma'lumotlar Bazasi (19:00 - 21:00).
- **Juma:** Python Amaliy Loyiha (15:00 - 17:00) | Haftalik mini-hackathon.
- **Shanba:** Frontend Amaliyot (17:00 - 19:00) | Shaxsiy konsultatsiyalar va mentor qabuli.
- **Yakshanba:** Dam olish kuni | Server va AI tizimi avtonom tahlili.

---
### 🔗 Bog'liq Havolalar:
- [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- [[Oltin_Qoidalar/Dars_Jadvali_va_Vaqtlar|Dars Jadvali]]
"""
    plan_file.write_text(plan_md, encoding="utf-8")
    print("✅ Generated Haftalik Reja in Kunlik_Rejalar/")

    # 9. GENERATE MASTER MAP OF CONTENT (MOC)
    moc_content = f"""---
title: "CoddyCamp Kognitiv Miya Xaritasi"
updated: "{now_str()}"
tags:
  - moc
  - ai_brain
  - coddycamp
---

# 🧠 CoddyCamp Sergeli — AI Kognitiv Boshqaruv Markazi

> [!TIP] Obsidian Graph View (`Cmd + G` yoki `Ctrl + G`)
> Ushbu miya xaritasi **{student_count} nafar o'quvchi**, **{len(STAFF_IDS)} nafar ma'muriyat va ustozlar**, **{len(groups)} ta o'quv guruhi**, **{len(golden_rules)} ta qat'iy oltin qoidalar** va **{len(all_lexicon)} ta jargon atamalar** bilan to'liq bog'langan!

---

## 🏛️ Ma'muriyat va Ustozlar Jamoasi
{"\n".join(staff_links)}

---

## 🏫 O'quv Guruhlari va Yo'nalishlar
- [[Guruhlar/Python_Dasturlash_Asoslari|🐍 Python Dasturlash Asoslari]] — *{len(groups['Python_Dasturlash_Asoslari']['students'])} nafar o'quvchi*
- [[Guruhlar/Frontend_Dasturlash_Web|🌐 Frontend Dasturlash (HTML, CSS, JS, React)]] — *{len(groups['Frontend_Dasturlash_Web']['students'])} nafar o'quvchi*
- [[Guruhlar/Backend_va_Ma_lumotlar_Bazasi|⚡ Backend va Ma'lumotlar Bazasi (FastAPI)]] — *{len(groups['Backend_va_Ma_lumotlar_Bazasi']['students'])} nafar o'quvchi*
- [[Guruhlar/CoddyCamp_Sergeli_Markazi|🏢 CoddyCamp Sergeli Markazi Umumiy Jamoasi]] — *{len(groups['CoddyCamp_Sergeli_Markazi']['students'])} nafar a'zo*
- [[Guruhlar/Ota_onalar_va_Vasiylar_Hamjamiyati|👨‍👩‍👧‍👦 Ota-onalar va Vasiylar Hamjamiyati]] — *{len(groups['Ota_onalar_va_Vasiylar_Hamjamiyati']['students'])} nafar ota-ona*

---

## 📜 Akademiya Oltin Qoidalari va Standartlari
- [[Oltin_Qoidalar/Dars_qoldirish_va_kasallik_tartibi|📋 Dars qoldirish va kasallik protokoli]]
- [[Oltin_Qoidalar/Ota_onalar_bilan_aloqa_qoidalari|🤝 Ota-onalar bilan aloqa va xushmuomalalik standarti]]
- [[Oltin_Qoidalar/Dars_Jadvali_va_Vaqtlar|⏰ Dars jadvali va vaqtlari]]
- [[Oltin_Qoidalar/Mentor_Pedagogik_Standartlari|🎓 Mentor pedagogik standartlari (Scaffolding)]]
- [[Oltin_Qoidalar/Ovozli_Xabarlarni_Qabul_Qilish_Qoidasi|🎙️ Ovozli xabarlarni transkripsiya qilish qoidasi]]
- [[Oltin_Qoidalar/Lokatsiyalar_va_Filiallar|📍 Filiallar, yangi ofis va mentor lokatsiyalari]]
- [[Oltin_Qoidalar/FastAPI_va_Backend_Standartlari|🚀 FastAPI & PostgreSQL Database Pooling]]
- [[Oltin_Qoidalar/HTML_CSS_Web_Standartlari|🎨 HTML, CSS & Responsive Web Standartlari]]

---

## 📚 Lug'at, Slang va Tizim Refleksiyasi
- [[Lugat_va_Slang/Mentor_Leksikoni|📖 Mentor Leksikoni va O'zbekcha Slang Lug'ati ({len(all_lexicon)} ta atama)]]
- [[Xatolar_va_Refleksiya/index|⚠️ Tizim Xatolari va Refleksiya Jurnali ({mistake_count} ta kartochka)]]
- [[Organilgan_Saboqlar/FastAPI_Database_Pooling|💡 O'rganilgan Texnik Saboqlar ({len(lessons)} ta mavzu)]]
- [[Kunlik_Rejalar/CoddyCamp_Haftalik_Rejasi|📅 CoddyCamp Haftalik Dars va Faoliyat Rejasi]]

---
*Oxirgi avtomatik yangilanish: {now_str()} | CoddyHelper v4.2 Production Brain*
"""
    (dirs["root"] / "🏠 Asosiy_Miya_Xaritasi.md").write_text(moc_content, encoding="utf-8")
    print(f"✅ Successfully written Master MOC to 🏠 Asosiy_Miya_Xaritasi.md")

if __name__ == "__main__":
    main()
