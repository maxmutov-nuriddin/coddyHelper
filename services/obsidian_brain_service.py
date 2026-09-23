"""
services/obsidian_brain_service.py
CoddyHelper - Obsidian Knowledge Vault Brain Service.
Agentning tashqi, ko'rinadigan va tahrirlanadigan "Tirik Miyasi" (Living Brain Graph).
Barcha o'quvchilar profillari, guruhlar, oltin qoidalar, o'rganilgan saboqlar,
mentor leksikoni va xatolar refleksiya kartochkalari Obsidian Markdown formatida
[[wikilinks]], teglari va YAML frontmatter bilan saqlanadi.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("coddy.obsidian_brain")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = PROJECT_ROOT / "brain_vault"


def _clean_filename(name: str) -> str:
    """Fayl nomi uchun noqulay belgilarni tozalaydi."""
    if not name:
        return "Nomalum"
    clean = re.sub(r'[\\/*?:"<>|#^\[\]]', "_", name).strip()
    return clean or "Nomalum"


def _tashkent_now_str() -> str:
    try:
        return datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ObsidianBrainService:
    def __init__(self, vault_dir: Path = VAULT_DIR):
        self.vault_dir = vault_dir
        self.staff_dir = self.vault_dir / "Mamuriyat_va_Ustozlar"
        self.students_dir = self.vault_dir / "Oquvchilar"
        self.groups_dir = self.vault_dir / "Guruhlar"
        self.rules_dir = self.vault_dir / "Oltin_Qoidalar"
        self.lessons_dir = self.vault_dir / "Organilgan_Saboqlar"
        self.mistakes_dir = self.vault_dir / "Xatolar_va_Refleksiya"
        self.lexicon_dir = self.vault_dir / "Lugat_va_Slang"
        self.plans_dir = self.vault_dir / "Kunlik_Rejalar"
        self._initialized = False

    def init_vault(self) -> None:
        """Vault papkalari va asosiy xarita faylini yaratadi."""
        try:
            for d in (
                self.vault_dir,
                self.staff_dir,
                self.students_dir,
                self.groups_dir,
                self.rules_dir,
                self.lessons_dir,
                self.mistakes_dir,
                self.lexicon_dir,
                self.plans_dir,
            ):
                d.mkdir(parents=True, exist_ok=True)

            self._create_root_moc_if_missing()
            self._initialized = True
            logger.info("🧠 Obsidian Brain Vault muvaffaqiyatli ishga tushdi: %s", self.vault_dir)
        except Exception as e:
            logger.error("Obsidian Brain Vault yaratishda xatolik: %s", e)

    def _create_root_moc_if_missing(self) -> None:
        """Asosiy xarita (Map of Content - MOC) markaziy tugunini yaratadi."""
        moc_file = self.vault_dir / "🏠 Asosiy_Miya_Xaritasi.md"
        content = f"""---
title: CoddyHelper Kognitiv Miya Xaritasi
created: {_tashkent_now_str()}
tags:
  - coddycamp
  - ai_brain
  - moc
---

# 🧠 CoddyHelper - Avtonom Sun'iy Intellekt Miyasi

Ushbu Obsidian Vault — CoddyHelper agentining **tirik, o'zgaruvchan va o'rganuvchi xotirasi** hisoblanadi.
Har bir o'quvchi, guruh, qoida va saboq bir-biri bilan `[[havolalar]]` orqali bog'langan.

> [!TIP] Obsidian Graph View
> Barcha neyron bog'liqliklarni ko'rish uchun Obsidianda **`Cmd + G`** (Windowsda `Ctrl + G`) tugmasini bosing!

---

## 🗺️ Miya Bo'limlari

* 👥 **[[Oquvchilar/index|O'quvchilar Profillari]]**: Barcha o'quvchilarning digital dosyelari, kuchli va zaif tomonlari.
* 🏫 **[[Guruhlar/index|CoddyCamp Guruhlari]]**: Faol dars guruhlari va ularga biriktirilgan talabalar.
* 📜 **[[Oltin_Qoidalar/index|Agent Oltin Qoidalari]]**: Mentor tomonidan kiritilgan yoki tasdiqlangan doimiy xulq-atvor qoidalari.
* 💡 **[[Organilgan_Saboqlar/index|O'rganilgan Saboqlar]]**: Suhbatlar va darslardan olingan yangi tushunchalar.
* ⚠️ **[[Xatolar_va_Refleksiya/index|Xatolar va Refleksiya]]**: Agent o'z xatolaridan chiqargan xulosalari va tuzatishlar.
* 📚 **[[Lugat_va_Slang/Mentor_Leksikoni|Mentor Leksikoni va Slang]]**: Mentorning maxsus atamalari, qisqartmalari va ma'nolari.
* 🤖 **[[Kunlik_Rejalar/index|Kunlik Rejalar]]**: Kun tartibi va vazifalar jurnali.

---
*Oxirgi yangilanish vaqti: {_tashkent_now_str()}*
"""
        try:
            moc_file.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning("MOC faylini yozishda ogohlantirish: %s", e)

    # =========================================================
    # 1. O'QUVCHILAR PROFILLERI (STUDENTS)
    # =========================================================
    def export_student(self, student: Dict[str, Any]) -> None:
        """Bitta o'quvchini Obsidian Markdown kartochkasi sifatida yozadi/yangilaydi."""
        if not self._initialized:
            self.init_vault()

        full_name = student.get("full_name") or "Nomalum Oquvchi"
        clean_name = _clean_filename(full_name)
        filename = f"{clean_name}.md"
        filepath = self.students_dir / filename

        group_name = student.get("group_name") or "Biriktirilmagan"
        group_clean = _clean_filename(group_name)
        group_link = f"[[Guruhlar/{group_clean}|{group_name}]]" if group_name != "Biriktirilmagan" else "Biriktirilmagan"

        user_id = student.get("user_id") or ""
        username = student.get("username") or ""
        status = student.get("status") or "yaxshi"
        strengths = student.get("strengths") or ""
        weaknesses = student.get("weaknesses") or ""
        notes = student.get("mentor_notes") or ""
        last_active = student.get("last_active") or _tashkent_now_str()

        md_content = f"""---
title: "{full_name}"
user_id: "{user_id}"
username: "{username}"
group: "{group_name}"
status: "{status}"
last_active: "{last_active}"
tags:
  - oquvchi
  - coddycamp
  - status/{status}
---

# 👤 {full_name}

- **Guruh:** {group_link}
- **Telegram:** {f"@{username}" if username else "Mavjud emas"}
- **Telegram ID:** `{user_id}`
- **Holati:** `{status.upper()}`
- **Oxirgi faollik:** {last_active}

---

## 🌟 Kuchli tomonlari
{strengths if strengths else "*Hozircha belgilanmagan*"}

## ⚠️ E'tibor talab tomonlari (Kamchiliklari)
{weaknesses if weaknesses else "*Hozircha aniqlanmagan*"}

## 📝 Mentor qaydlari va Tarix
{notes if notes else "*Qaydlar kiritilmagan*"}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi]]*
"""
        try:
            filepath.write_text(md_content, encoding="utf-8")
            # Guruh faylini ham avtomatik yangilab qo'yamiz:
            if group_name and group_name != "Biriktirilmagan":
                self._link_student_to_group(group_name, clean_name, full_name)
        except Exception as e:
            logger.warning("O'quvchi kartochkasini saqlashda ogohlantirish: %s", e)

    def _link_student_to_group(self, group_name: str, clean_student_name: str, full_name: str) -> None:
        """Guruh fayliga o'quvchi havolasini qo'shadi."""
        clean_grp = _clean_filename(group_name)
        grp_file = self.groups_dir / f"{clean_grp}.md"
        student_link = f"- [[Oquvchilar/{clean_student_name}|{full_name}]]"

        existing_content = ""
        if grp_file.exists():
            try:
                existing_content = grp_file.read_text(encoding="utf-8")
            except Exception:
                existing_content = ""

        if student_link in existing_content:
            return

        if not existing_content:
            content = f"""---
title: "{group_name}"
type: group
tags:
  - guruh
  - coddycamp
---

# 🏫 Guruh: {group_name}

## 👥 Guruh O'quvchilari
{student_link}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi]]*
"""
        else:
            if "## 👥 Guruh O'quvchilari" in existing_content:
                parts = existing_content.split("## 👥 Guruh O'quvchilari")
                content = f"{parts[0]}## 👥 Guruh O'quvchilari\n{student_link}\n{parts[1].lstrip()}"
            else:
                content = f"{existing_content}\n\n## 👥 Guruh O'quvchilari\n{student_link}\n"

        try:
            grp_file.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning("Guruh faylini yangilashda ogohlantirish: %s", e)

    def export_dossier(
        self,
        user_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        bio: str = "",
        dossier_text: str = "",
    ) -> None:
        """Foydalanuvchi dosyesi yaratilganda yoki yangilanganda Obsidian kartochkasini avtomatik yangilaydi."""
        if not self._initialized:
            self.init_vault()

        raw_name = f"{first_name or ''} {last_name or ''}".strip()
        display_name = raw_name if raw_name else (f"@{username}" if username else f"Foydalanuvchi {user_id}")
        clean_file = _clean_filename(display_name)
        if len(clean_file) > 35 or clean_file.startswith(('.', '-', '@')):
            clean_file = _clean_filename(username) if username else f"User_{user_id}"

        filename = f"{clean_file}.md"
        filepath = self.students_dir / filename

        # Guruhni aniqlash
        full_text_lower = f"{display_name} {bio} {dossier_text}".lower()
        is_parent = False
        target_group = "CoddyCamp_Sergeli_Markazi"
        group_title = "CoddyCamp Sergeli Filiali - Umumiy Jamoa"

        if any(w in full_text_lower for w in ["oila", "ona", "ota", "farzand", "qizim", "o'g'lim", "deti", "семь", "мама"]):
            target_group = "Ota_onalar_va_Vasiylar_Hamjamiyati"
            group_title = "Ota-onalar va Vasiylar Hamjamiyati"
            is_parent = True
        elif any(w in full_text_lower for w in ["frontend", "react", "html", "css", "javascript", "web"]):
            target_group = "Frontend_Dasturlash_Web"
            group_title = "Frontend Dasturlash (HTML, CSS, JS, React)"
        elif any(w in full_text_lower for w in ["backend", "fastapi", "django", "sql", "postgres"]):
            target_group = "Backend_va_Ma_lumotlar_Bazasi"
            group_title = "Backend va Ma'lumotlar Bazasi (FastAPI & PostgreSQL)"
        elif any(w in full_text_lower for w in ["python", "bot", "algoritm", "kod"]):
            target_group = "Python_Dasturlash_Asoslari"
            group_title = "Python Dasturlash Asoslari"

        group_link = f"[[Guruhlar/{target_group}|{group_title}]]"
        status = "ota_ona" if is_parent else "faol"
        phone_display = f"+{phone}" if phone and not phone.startswith("+") else (phone or "Ko'rsatilmagan")
        username_display = f"@{username}" if username else "Mavjud emas"

        dossier_section = ""
        if dossier_text and len(dossier_text.strip()) > 30:
            cleaned_dossier = dossier_text.strip()
            cleaned_dossier = re.sub(r"🕵️‍♂️ \*\*\[Miya 5: Shaxs Kognitiv Dosyesi\]\*\*\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n?", "", cleaned_dossier)
            dossier_section = f"### 🧠 AI Kognitiv Tahlili va Psixologik Portret:\n{cleaned_dossier}\n"
        else:
            dossier_section = "### 🧠 AI Kognitiv Tahlili:\n*Profil yangi. Agent suhbatlar va xabarlar asosida kognitiv tahlil yuritmoqda.*\n"

        md_content = f"""---
title: "{display_name}"
user_id: {user_id}
username: "{username}"
phone: "{phone_display}"
role: "{"ota_ona" if is_parent else "oquvchi"}"
group: "{group_title}"
status: "{status}"
updated: "{_tashkent_now_str()}"
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
- **Telegram ID:** `{user_id}`
- **Bio/Status:** {bio or "*Mavjud emas*"}

---

### 🏫 Biriktirilgan O'quv Rejasi:
- **Yo'nalish Guruhi:** {group_link}
- **Bosh Mentor:** [[Mamuriyat_va_Ustozlar/Nuriddin Makhmutov|Nuriddin Ustoz]]
- **Kurator:** [[Mamuriyat_va_Ustozlar/Kurator Sergeli|Kurator Sergeli]]

---

{dossier_section}

---

### 🔗 Bog'liq Tizim Havolalari:
- Markaziy Miya Xaritasi: [[🏠 Asosiy_Miya_Xaritasi|🏠 Asosiy Miya Xaritasi]]
- Akademiya Qoidalari: [[Oltin_Qoidalar/Dars_qoldirish_va_kasallik_tartibi|Dars Qoldirish Tartibi]]
- Leksikon va Slang: [[Lugat_va_Slang/Mentor_Leksikoni|Mentor Leksikoni]]
"""
        try:
            filepath.write_text(md_content, encoding="utf-8")
            self._link_student_to_group(target_group, clean_file, display_name)
        except Exception as e:
            logger.warning("Obsidianda dosye saqlashda ogohlantirish: %s", e)

    def delete_student_note(self, student_name: str) -> None:
        """O'quvchi o'chirilganda uning Obsidian faylini ham o'chiradi."""
        if not self._initialized:
            self.init_vault()
        clean = _clean_filename(student_name)
        target = self.students_dir / f"{clean}.md"
        if target.exists():
            try:
                target.unlink()
                logger.info("🗑️ Obsidiandan o'quvchi kartochkasi o'chirildi: %s", clean)
            except Exception as e:
                logger.warning("Obsidiandan o'quvchini o'chirishda xatolik: %s", e)

    def delete_rule_note(self, topic: str) -> None:
        """Qoida o'chirilganda uning Obsidian faylini ham o'chiradi."""
        if not self._initialized:
            self.init_vault()
        clean = _clean_filename(topic)
        target = self.rules_dir / f"{clean}.md"
        if target.exists():
            try:
                target.unlink()
                logger.info("🗑️ Obsidiandan qoida o'chirildi: %s", clean)
            except Exception as e:
                logger.warning("Obsidiandan qoidani o'chirishda xatolik: %s", e)

    # =========================================================
    # 2. OLTIN QOIDALAR VA SABOQLAR
    # =========================================================
    def export_rule(self, topic: str, content: str, source: str = "mentor") -> None:
        """Oltin qoidani Obsidian fayli sifatida saqlaydi."""
        if not self._initialized:
            self.init_vault()

        clean_topic = _clean_filename(topic)
        filename = f"{clean_topic}.md"
        filepath = self.rules_dir / filename

        md_content = f"""---
title: "{topic}"
category: "oltin_qoida"
source: "{source}"
updated_at: "{_tashkent_now_str()}"
tags:
  - oltin_qoida
  - kognitiv_baza
---

# 📜 Oltin Qoida: {topic}

> [!IMPORTANT] Qat'iy Ko'rsatma
> {content}

- **Manbasi:** `{source}`
- **Yangilangan vaqti:** {_tashkent_now_str()}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi]]*
"""
        try:
            filepath.write_text(md_content, encoding="utf-8")
        except Exception as e:
            logger.warning("Qoidani Obsidianga yozishda ogohlantirish: %s", e)

    # =========================================================
    # 3. XATOLAR VA REFLEKSIYA
    # =========================================================
    def export_mistake(self, mistake_text: str, lesson_learned: str, golden_rule: str = "") -> None:
        """Agent o'z xatosidan chiqargan saboqni alohida tahlil kartochkasi qilib saqlaydi."""
        if not self._initialized:
            self.init_vault()

        date_prefix = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        snippet = _clean_filename(mistake_text[:30])
        filename = f"{date_prefix}_{snippet}.md"
        filepath = self.mistakes_dir / filename

        md_content = f"""---
title: "Xato Tahlili - {date_prefix}"
type: reflection
created: "{_tashkent_now_str()}"
tags:
  - refleksiya
  - xatolikdan_saboq
---

# ⚠️ Xato va Refleksiya Tahlili ({date_prefix})

### ❌ Nima xato bo'ldi (Muammo):
> {mistake_text}

### 💡 Chiqarilgan Saboq:
> {lesson_learned}

### 🛡️ O'rnatilgan Oltin Himoya Qoidasi:
> {golden_rule if golden_rule else "Ushbu xatoni qayta takrorlamaslik uchun filtr va xatti-harakat yangilandi."}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi]]*
"""
        try:
            filepath.write_text(md_content, encoding="utf-8")
        except Exception as e:
            logger.warning("Refleksiya faylini yozishda ogohlantirish: %s", e)

    # =========================================================
    # 4. MENTOR LEKSIKONI VA SLANG
    # =========================================================
    def export_lexicon(self, lexicon_entries: List[Dict[str, Any]]) -> None:
        """Barcha o'rganilgan leksikon atamalarini tartibli jadval va kartochka qilib yangilaydi."""
        if not self._initialized:
            self.init_vault()

        filepath = self.lexicon_dir / "Mentor_Leksikoni.md"
        rows = []
        for e in lexicon_entries:
            term = e.get("term", "")
            meaning = e.get("meaning", "")
            example = e.get("example", "")
            rows.append(f"| **{term}** | {meaning} | *{example}* |")

        table_str = "\n".join(rows) if rows else "| *Atamalar hozircha yo'q* | - | - |"

        md_content = f"""---
title: Mentor Leksikoni va Atamalar
updated: "{_tashkent_now_str()}"
tags:
  - leksikon
  - slang
  - atamalar
---

# 📚 Mentor Leksikoni va Slang Lug'ati

Ushbu lug'at agent tomonidan suhbatlar jarayonida o'rganilgan barcha maxsus so'zlar,
mentor qisqartmalari va jargonlarni o'z ichiga oladi.

| Atama / Qisqartma | Asl Ma'nosi | Misol |
| :--- | :--- | :--- |
{table_str}

---
*Bog'liq havola: [[🏠 Asosiy_Miya_Xaritasi]]*
"""
        try:
            filepath.write_text(md_content, encoding="utf-8")
        except Exception as e:
            logger.warning("Leksikonni Obsidianga yozishda ogohlantirish: %s", e)

    # =========================================================
    # 5. OBSIDIANDAGI QOIDALARNI O'QISH (HUMAN-IN-THE-LOOP)
    # =========================================================
    def read_custom_rules(self) -> List[str]:
        """
        Mentor Obsidiandagi 'Oltin_Qoidalar' papkasida qo'lda yozgan yoki tahrirlagan
        barcha markdown fayllarni o'qib, AI tizim promptiga qo'shish uchun qaytaradi.
        """
        if not self.rules_dir.exists():
            return []

        rules = []
        try:
            for md_file in self.rules_dir.glob("*.md"):
                if md_file.name.startswith("index") or md_file.name.startswith("."):
                    continue
                text = md_file.read_text(encoding="utf-8")
                # Frontmatter ni tozalash
                cleaned = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
                # Sarlavhani ajratish
                topic = md_file.stem.replace("_", " ")
                if cleaned:
                    rules.append(f"• [{topic.upper()}]: {cleaned}")
        except Exception as e:
            logger.warning("Obsidian qoidalarini o'qishda ogohlantirish: %s", e)

        return rules

    # =========================================================
    # 6. TO'LIQ BAZANI OBSIDIAN BILAN SINXRONLASH
    # =========================================================
    def sync_all_from_db(self) -> None:
        """
        SQLite va xotiradagi barcha mavjud o'quvchilar, saboqlar va leksikonni
        Obsidian Vault papkasiga to'liq eksport qiladi.
        """
        from services.memory_service import memory_service

        logger.info("🔄 Obsidian Vault bilan to'liq sinxronlash boshlandi...")
        self.init_vault()

        # 1. O'quvchilarni sinxronlash
        students = memory_service.get_students(limit=200)
        for s in students:
            self.export_student(s)

        # 2. O'rganilgan bilimlarni (Oltin qoidalar) sinxronlash
        facts = memory_service.get_learned_facts(limit=100)
        for f in facts:
            topic = f.get("topic") or "Umumiy"
            content = f.get("content") or ""
            source = f.get("source") or "mentor"
            if content:
                self.export_rule(topic, content, source)

        # 3. Leksikonni sinxronlash
        lex_entries = memory_service.get_all_mentor_lexicon(limit=100)
        if lex_entries:
            self.export_lexicon(lex_entries)

        # 4. Xatolarni sinxronlash
        mistakes = memory_service.get_recent_self_mistakes(limit=30)
        for m in mistakes:
            self.export_mistake(
                mistake_text=m.get("mistake") or m.get("mistake_text", ""),
                lesson_learned=m.get("correction") or m.get("lesson_learned", ""),
                golden_rule=m.get("rule") or m.get("golden_rule", ""),
            )

        # 5. user_dossiers va to'liq ma'lumotlar bazasini yangilash
        try:
            from scripts.populate_real_data import main as populate_main
            populate_main()
        except Exception as e:
            logger.warning("To'liq dosyelarni eksport qilishda ogohlantirish: %s", e)

        logger.info("✅ Obsidian Vault to'liq sinxronlandi: %d o'quvchi, %d qoida, %d leksikon.", len(students), len(facts), len(lex_entries))


# Global instansiya
obsidian_brain_service = ObsidianBrainService()
