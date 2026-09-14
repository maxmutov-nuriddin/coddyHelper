"""
Doimiy SQLite xotira xizmati (Persistent Memory)
Suhbatlar kompyuter o'chsa yoki dastur qayta ishga tushsa ham saqlanib qoladi.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from config import config

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "coddy_memory.db"


@dataclass
class ChatMessage:
    role: Literal["user", "model"]
    content: str


class SQLiteMemoryService:
    def __init__(self, db_path: Path = DB_PATH, limit: int = 15):
        self.db_path = db_path
        self.limit = config.memory_limit or limit
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=10.0)

    def _init_db(self) -> None:
        """Ma'lumotlar bazasi va jadvallarni yaratadi."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_id ON messages (chat_id, id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ignored_users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        creator_id INTEGER NOT NULL,
                        reminder_text TEXT NOT NULL,
                        remind_at TEXT NOT NULL,
                        is_sent INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_remind_at ON reminders (is_sent, remind_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE,
                        full_name TEXT NOT NULL,
                        username TEXT DEFAULT '',
                        group_name TEXT DEFAULT '',
                        questions_count INTEGER DEFAULT 0,
                        strengths TEXT DEFAULT '',
                        weaknesses TEXT DEFAULT '',
                        mentor_notes TEXT DEFAULT '',
                        status TEXT DEFAULT 'yaxshi',
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_student_user_id ON students (user_id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS learned_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT DEFAULT 'rule',
                        topic TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source TEXT DEFAULT 'mentor',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_learned_topic ON learned_memory (topic)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS saved_locations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        name_clean TEXT NOT NULL,
                        lat REAL NOT NULL,
                        long REAL NOT NULL,
                        address TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_saved_locations_name ON saved_locations (name_clean)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        plan_date TEXT NOT NULL,
                        plan_time TEXT DEFAULT '',
                        is_completed INTEGER DEFAULT 0,
                        priority TEXT DEFAULT 'normal',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_daily_plans_date ON daily_plans (plan_date, is_completed)"
                )
                conn.commit()
        except Exception as e:
            logger.error("SQLite xotirasini ishga tushirishda xatolik: %s", e)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Doimiy sozlamani o'qiydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error("Sozlamani o'qishda xatolik: %s", e)
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Doimiy sozlamani saqlaydi."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
                conn.commit()
        except Exception as e:
            logger.error("Sozlamani saqlashda xatolik: %s", e)

    def get_private_quiet_window(self) -> int:
        """
        Mentor shaxsiy chatda yozib bo'lgandan so'ng, yangi kelgan xabarlarga
        AI darhol aralashmasdan mentor javobini kutib turadigan vaqt (soniyalarda). Default: 180 (3 daqiqa).
        """
        val = self.get_setting("private_quiet_window", "180")
        try:
            return int(val)
        except Exception:
            return 180

    def set_private_quiet_window(self, seconds: int) -> None:
        """Lichka sokinlik/kutish vaqtini yangilaydi."""
        self.set_setting("private_quiet_window", str(max(0, int(seconds))))

    DEFAULT_TRUSTED_WEBSITES = [
        "w3schools.com",
        "docs.python.org",
        "developer.mozilla.org",
        "metanit.com",
        "geeksforgeeks.org",
    ]

    def get_trusted_websites(self) -> list[str]:
        """Ishonchli ta'limiy va dasturlash saytlari ro'yxatini qaytaradi."""
        import json
        raw = self.get_setting("trusted_websites")
        if not raw:
            return list(self.DEFAULT_TRUSTED_WEBSITES)
        try:
            sites = json.loads(raw)
            return sites if isinstance(sites, list) and sites else list(self.DEFAULT_TRUSTED_WEBSITES)
        except Exception:
            return list(self.DEFAULT_TRUSTED_WEBSITES)

    def set_trusted_websites(self, sites: list[str]) -> None:
        """Ishonchli saytlar ro'yxatini to'liq yangilaydi."""
        import json
        clean_sites = []
        for s in sites:
            clean = self._clean_domain(s)
            if clean and clean not in clean_sites:
                clean_sites.append(clean)
        self.set_setting("trusted_websites", json.dumps(clean_sites))

    def add_trusted_website(self, domain: str) -> bool:
        """Yangi ishonchli saytni ro'yxatga qo'shadi."""
        clean = self._clean_domain(domain)
        if not clean:
            return False
        current = self.get_trusted_websites()
        if clean in current:
            return True
        current.append(clean)
        self.set_trusted_websites(current)
        return True

    def remove_trusted_website(self, domain: str) -> bool:
        """Ishonchli saytni ro'yxatdan o'chiradi."""
        clean = self._clean_domain(domain)
        current = self.get_trusted_websites()
        if clean not in current:
            return False
        current.remove(clean)
        self.set_trusted_websites(current)
        return True

    @staticmethod
    def _clean_domain(raw_url: str) -> str:
        """URL yoki domenni toza domen ko'rinishiga keltiradi (masalan: https://w3schools.com/python -> w3schools.com)."""
        import urllib.parse
        s = raw_url.strip().lower()
        if not s:
            return ""
        if "://" in s:
            parsed = urllib.parse.urlparse(s)
            s = parsed.netloc or parsed.path
        elif "/" in s:
            s = s.split("/")[0]
        s = s.split(":")[0]
        if s.startswith("www."):
            s = s[4:]
        return s.strip()

    DEFAULT_CURRICULUM_TOPICS = [
        "HTML",
        "CSS",
        "JavaScript (JS)",
        "Tailwind CSS",
        "Bootstrap",
        "React",
        "Next.js",
        "Node.js",
        "Express.js",
        "MongoDB",
        "REST API",
        "Asinxron dasturlash",
        "Git & GitHub",
        "Netlify",
        "Vercel",
        "Telegram Bot",
        "Authentication & Security",
        "Figma",
        "AI mavzulari & vositalari",
        "Wix",
        "Renderforest",
        "Scratch",
        "Pictoblox",
    ]

    def get_curriculum_topics(self) -> list[str]:
        """O'quv markazining rasmiy o'quv mavzulari va texnologiyalari ro'yxatini qaytaradi."""
        import json
        raw = self.get_setting("curriculum_topics")
        if not raw:
            return list(self.DEFAULT_CURRICULUM_TOPICS)
        try:
            topics = json.loads(raw)
            return topics if isinstance(topics, list) and topics else list(self.DEFAULT_CURRICULUM_TOPICS)
        except Exception:
            return list(self.DEFAULT_CURRICULUM_TOPICS)

    def set_curriculum_topics(self, topics: list[str]) -> None:
        """O'quv mavzulari ro'yxatini saqlaydi."""
        import json
        clean_topics = []
        for t in topics:
            val = str(t).strip()
            if val and val not in clean_topics:
                clean_topics.append(val)
        self.set_setting("curriculum_topics", json.dumps(clean_topics))

    def add_curriculum_topic(self, topic: str) -> bool:
        """Yangi o'quv mavzusini qo'shadi."""
        t = str(topic).strip()
        if not t:
            return False
        current = self.get_curriculum_topics()
        if any(c.lower() == t.lower() for c in current):
            return True
        current.append(t)
        self.set_curriculum_topics(current)
        return True

    def remove_curriculum_topic(self, topic: str) -> bool:
        """O'quv mavzusini ro'yxatdan olib tashlaydi."""
        t = str(topic).strip().lower()
        current = self.get_curriculum_topics()
        filtered = [c for c in current if c.lower() != t]
        if len(filtered) == len(current):
            return False
        self.set_curriculum_topics(filtered)
        return True

    def add_message(self, chat_id: int, role: Literal["user", "model"], content: str) -> None:
        """Yangi xabarni doimiy bazaga qo'shadi."""
        if not content or not content.strip():
            return

        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                    (chat_id, role, content.strip()),
                )
                conn.commit()
        except Exception as e:
            logger.error("Xotiraga yozishda xatolik: %s", e)

    def update_last_message(self, chat_id: int, content: str) -> None:
        """Chatdagi eng so'nggi xabar matnini yangilaydi (Action agent natijalarini yozish uchun)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
                    (chat_id,),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (content.strip(), row[0]))
                    conn.commit()
        except Exception as e:
            logger.error("Oxirgi xabarni yangilashda xatolik: %s", e)

    def get_history(self, chat_id: int) -> list[ChatMessage]:
        """Oxirgi N ta xabarlar tarixini xronologik tartibda qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role, content FROM (
                        SELECT id, role, content FROM messages 
                        WHERE chat_id = ? 
                        ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                    """,
                    (chat_id, self.limit),
                )
                rows = cursor.fetchall()
                return [ChatMessage(role=r[0], content=r[1]) for r in rows]
        except Exception as e:
            logger.error("Xotirani o'qishda xatolik: %s", e)
            return []

    def is_new_session_or_day(self, chat_id: int) -> bool:
        """
        Oxirgi xabar kecha yozilganmi (yangi kun) yoki oxirgi xabardan 6 soatdan ko'p vaqt o'tganmi?
        Agar yangi kun yoki yangi sessiya bo'lsa, True qaytaradi.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        date(created_at, '+5 hours') != date('now', '+5 hours'),
                        (strftime('%s', 'now') - strftime('%s', created_at)) > 21600
                    FROM messages 
                    WHERE chat_id = ? 
                    ORDER BY id DESC LIMIT 1
                    """,
                    (chat_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return True
                is_different_date, is_over_6_hours = row
                return bool(is_different_date or is_over_6_hours)
        except Exception as e:
            logger.error("Yangi kun tekshiruvida xatolik: %s", e)
            return True

    def clear(self, chat_id: int) -> bool:
        """Chat tarixini butunlay tozalaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Xotirani tozalashda xatolik: %s", e)
            return False

    def total_active_chats(self) -> int:
        """Xotiradagi jami faol o'quvchilar/chatlar soni."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM messages")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error("Chatlar sonini olishda xatolik: %s", e)
            return 0

    def ignore_user(self, user_id: int, username: str = "", reason: str = "") -> None:
        """Foydalanuvchini bloklanganlar (ignore) ro'yxatiga qo'shadi."""
        # 🛡 MENTOR DAXILSIZLIGI (IMMUNITY GUARD):
        # Mentorni (Yagona mentor / 8105823872) hech qanday holatda bloklab yoki ignore qilib bo'lmaydi!
        try:
            from config import config
            if user_id in (config.mentor_user_id, 8105823872):
                logger.warning("Xavfsizlik: Mentorni (ID: %s) ignore ro'yxatiga qo'shish qat'iyan man etiladi!", user_id)
                return
        except Exception:
            if user_id == 8105823872:
                return

        try:
            with self._get_connection() as conn:
                try:
                    conn.execute("ALTER TABLE ignored_users ADD COLUMN reason TEXT DEFAULT ''")
                except Exception:
                    pass
                conn.execute(
                    "INSERT OR REPLACE INTO ignored_users (user_id, username, reason) VALUES (?, ?, ?)",
                    (user_id, username, reason),
                )
                conn.commit()
        except Exception as e:
            logger.error("Foydalanuvchini ignore ro'yxatiga qo'shishda xatolik: %s", e)

    def unignore_user(self, user_id: int) -> bool:
        """Foydalanuvchini ignore ro'yxatidan chiqaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ignored_users WHERE user_id = ?", (user_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Foydalanuvchini ignore ro'yxatidan o'chirishda xatolik: %s", e)
            return False

    def is_user_ignored(self, user_id: int) -> bool:
        """Foydalanuvchi bloklanganligini tekshiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM ignored_users WHERE user_id = ?", (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error("Ignore holatini tekshirishda xatolik: %s", e)
            return False

    def get_ignored_users(self) -> list[dict]:
        """Bloklangan barcha foydalanuvchilar ro'yxati."""
        try:
            with self._get_connection() as conn:
                try:
                    conn.execute("ALTER TABLE ignored_users ADD COLUMN reason TEXT DEFAULT ''")
                except Exception:
                    pass
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, username, created_at, COALESCE(reason, '') FROM ignored_users ORDER BY created_at DESC")
                rows = cursor.fetchall()
                return [{"user_id": r[0], "username": r[1], "created_at": r[2], "reason": r[3]} for r in rows]
        except Exception as e:
            logger.error("Ignore ro'yxatini olishda xatolik: %s", e)
            return []

    def get_user_strikes(self, user_id: int) -> int:
        """Foydalanuvchining mavzudan tashqari savollari sonini oladi."""
        val = self.get_setting(f"strike_{user_id}", "0")
        return int(val) if val and str(val).isdigit() else 0

    def increment_user_strikes(self, user_id: int) -> int:
        """Foydalanuvchining ogohlantirishlar (strikes) sonini 1 taga oshiradi."""
        current = self.get_user_strikes(user_id) + 1
        self.set_setting(f"strike_{user_id}", str(current))
        return current

    def reset_user_strikes(self, user_id: int) -> None:
        """Foydalanuvchining ogohlantirishlar sonini nollaydi."""
        self.set_setting(f"strike_{user_id}", "0")

    def get_recent_user_questions(self, limit: int = 50) -> list[str]:
        """Tahlil uchun o'quvchilar tomonidan yozilgan so'nggi savollarni oladi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content FROM messages WHERE role = 'user' ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                return [r[0] for r in rows if r[0] and len(r[0].strip()) > 3]
        except Exception as e:
            logger.error("O'quvchilar savollarini olishda xatolik: %s", e)
            return []

    # -----------------------------------------------------------
    # O'z ustida ishlash va Bilimlar Bazasi (Continuous Learning)
    # -----------------------------------------------------------
    def add_learned_fact(self, topic: str, content: str, category: str = "rule") -> int:
        """Mentor ko'rsatmasi, qoidasi yoki yangi faktni doimiy xotiraga yozadi."""
        t = topic.strip()
        c = content.strip()
        if not t or not c:
            return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM learned_memory WHERE LOWER(topic) = LOWER(?)", (t,))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        "UPDATE learned_memory SET content = ?, category = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (c, category, existing[0]),
                    )
                    conn.commit()
                    return existing[0]
                else:
                    cursor.execute(
                        "INSERT INTO learned_memory (category, topic, content) VALUES (?, ?, ?)",
                        (category, t, c),
                    )
                    conn.commit()
                    return cursor.lastrowid
        except Exception as e:
            logger.error("Yangi bilimni saqlashda xatolik: %s", e)
            return 0

    def get_all_learned_facts(self, limit: int = 50) -> list[dict]:
        """Barcha o'rganilgan bilimlar va qoidalarni qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, category, topic, content, created_at, updated_at FROM learned_memory ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "category": r[1],
                        "topic": r[2],
                        "content": r[3],
                        "created_at": r[4],
                        "updated_at": r[5],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("O'rganilgan bilimlarni olishda xatolik: %s", e)
            return []

    def delete_learned_fact(self, target: str | int) -> bool:
        """Bilimni mavzusi yoki ID si bo'yicha o'chiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if str(target).isdigit():
                    cursor.execute("DELETE FROM learned_memory WHERE id = ?", (int(target),))
                else:
                    cursor.execute("DELETE FROM learned_memory WHERE LOWER(topic) = LOWER(?)", (str(target).strip(),))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Bilimni o'chirishda xatolik: %s", e)
            return False

    def get_knowledge_context(self, limit: int = 30) -> str:
        """AI promptiga qo'shish uchun barcha o'rganilgan qoidalar va faktlarni chiroyli formatda qaytaradi."""
        facts = self.get_all_learned_facts(limit=limit)
        if not facts:
            return ""
        lines = [
            "# DOIMIY O'RGANILGAN BILIMLAR VA MENTORNING QOIDALARI (LEARNED KNOWLEDGE BASE):",
            "Siz oldingi suhbatlarda mentor tomonidan o'rgatilgan quyidagi qoidalar, ma'lumotlar va tuzatishlarga QAT'IY amal qilishingiz shart:"
        ]
        for f in reversed(facts):
            lines.append(f"• [{f['topic'].upper()}]: {f['content']}")
        return "\n".join(lines)

    # -----------------------------------------------------------
    # Eslatmalar (Reminders) Boshqaruvi
    # -----------------------------------------------------------
    def add_reminder(
        self, chat_id: int, reminder_text: str, remind_at: str, creator_id: int = 0
    ) -> int:
        """Yangi eslatmani bazaga saqlaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reminders (chat_id, creator_id, reminder_text, remind_at, is_sent)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (chat_id, creator_id, reminder_text.strip(), remind_at),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error("Eslatmani saqlashda xatolik: %s", e)
            return 0

    def get_active_reminders(self, limit: int = 20) -> list[dict]:
        """Kutilayotgan faol eslatmalar ro'yxatini qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, chat_id, creator_id, reminder_text, remind_at, created_at
                    FROM reminders
                    WHERE is_sent = 0
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "chat_id": r[1],
                        "creator_id": r[2],
                        "text": r[3],
                        "remind_at": r[4],
                        "created_at": r[5],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Faol eslatmalarni olishda xatolik: %s", e)
            return []

    def get_due_reminders(self, current_time_str: str) -> list[dict]:
        """Vaqti yetgan (muddati kelgan) eslatmalarni qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, chat_id, creator_id, reminder_text, remind_at
                    FROM reminders
                    WHERE is_sent = 0 AND remind_at <= ?
                    ORDER BY remind_at ASC
                    """,
                    (current_time_str,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "chat_id": r[1],
                        "creator_id": r[2],
                        "text": r[3],
                        "remind_at": r[4],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Muddati kelgan eslatmalarni olishda xatolik: %s", e)
            return []

    def mark_reminder_sent(self, reminder_id: int) -> None:
        """Eslatmani yuborilgan (is_sent = 1) deb belgilaydi."""
        try:
            with self._get_connection() as conn:
                conn.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
                conn.commit()
        except Exception as e:
            logger.error("Eslatmani yuborilgan deb belgilashda xatolik: %s", e)

    def mark_reminder_sent_if_pending(self, reminder_id: int) -> bool:
        """Faqat yuborilmagan bo'lsa (is_sent = 0), is_sent = 1 qiladi va True qaytaradi.
        Dublikat xabarlar va takrorlanishlarning oldini oladi.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = ? AND is_sent = 0", (reminder_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Eslatmani atomar belgilashda xatolik: %s", e)
            return False

    def delete_reminder(self, reminder_id: int) -> bool:
        """Eslatmani bekor qiladi/o'chiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Eslatmani o'chirishda xatolik: %s", e)
            return False

    # -----------------------------------------------------------
    # O'quvchilar CRM boshqaruvi (Student Digital Profile)
    # -----------------------------------------------------------
    def upsert_student(
        self,
        full_name: str,
        user_id: int | None = None,
        username: str = "",
        group_name: str = "",
        status: str = "yaxshi",
        strengths: str = "",
        weaknesses: str = "",
        mentor_notes: str = "",
    ) -> int:
        """O'quvchini qo'shadi yoki yangilaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if user_id:
                    cursor.execute(
                        """
                        INSERT INTO students (user_id, full_name, username, group_name, status, strengths, weaknesses, mentor_notes, last_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id) DO UPDATE SET
                            full_name = excluded.full_name,
                            username = CASE WHEN excluded.username != '' THEN excluded.username ELSE students.username END,
                            group_name = CASE WHEN excluded.group_name != '' THEN excluded.group_name ELSE students.group_name END,
                            status = CASE WHEN excluded.status != '' THEN excluded.status ELSE students.status END,
                            strengths = CASE WHEN excluded.strengths != '' THEN excluded.strengths ELSE students.strengths END,
                            weaknesses = CASE WHEN excluded.weaknesses != '' THEN excluded.weaknesses ELSE students.weaknesses END,
                            mentor_notes = CASE WHEN excluded.mentor_notes != '' THEN excluded.mentor_notes ELSE students.mentor_notes END,
                            last_active = CURRENT_TIMESTAMP
                        """,
                        (user_id, full_name, username, group_name, status, strengths, weaknesses, mentor_notes),
                    )
                    conn.commit()
                    return cursor.lastrowid or 0
                else:
                    cursor.execute(
                        """
                        INSERT INTO students (full_name, username, group_name, status, strengths, weaknesses, mentor_notes, last_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (full_name, username, group_name, status, strengths, weaknesses, mentor_notes),
                    )
                    conn.commit()
                    return cursor.lastrowid
        except Exception as e:
            logger.error("O'quvchini saqlashda xatolik: %s", e)
            return 0

    def record_student_activity(
        self,
        user_id: int,
        full_name: str = "",
        username: str = "",
        question_text: str = "",
    ) -> None:
        """O'quvchi savol berganda uning faolligini oshiradi va profilini yangilab boradi."""
        if not user_id:
            return
        try:
            # Mavzularni aniqlash
            topic_tag = ""
            q_lower = question_text.lower()
            if any(k in q_lower for k in ["for", "while", "loop", "takrorlash"]):
                topic_tag = "Loops (Sikllar)"
            elif any(k in q_lower for k in ["class", "def", "oop", "self", "object", "vorislik"]):
                topic_tag = "OOP (Klasslar)"
            elif any(k in q_lower for k in ["list", "dict", "tuple", "set", "lug'at"]):
                topic_tag = "Ma'lumot tuzilmalari"
            elif any(k in q_lower for k in ["import", "pip", "modul", "venv"]):
                topic_tag = "Modullar / Kutubxonalar"
            elif any(k in q_lower for k in ["indexerror", "keyerror", "typeerror", "indentationerror"]):
                topic_tag = "Xatoliklar (Exceptions)"

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, questions_count, weaknesses FROM students WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row:
                    s_id, q_count, w_text = row
                    new_w = w_text or ""
                    if topic_tag and topic_tag not in new_w:
                        new_w = f"{new_w}, {topic_tag}".strip(", ")

                    cursor.execute(
                        """
                        UPDATE students SET
                            questions_count = questions_count + 1,
                            weaknesses = ?,
                            last_active = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (new_w, s_id),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO students (user_id, full_name, username, questions_count, weaknesses, last_active)
                        VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
                        """,
                        (user_id, full_name or f"O'quvchi {user_id}", username, topic_tag),
                    )
                conn.commit()
        except Exception as e:
            logger.debug("O'quvchi faolligini yozishda ogohlantirish: %s", e)

    def get_students(self, limit: int = 100, search: str = "", status_filter: str = "") -> list[dict]:
        """Barcha o'quvchilar ro'yxatini oladi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT id, user_id, full_name, username, group_name, questions_count, strengths, weaknesses, mentor_notes, status, last_active, created_at FROM students WHERE 1=1"
                params = []

                if search:
                    query += " AND (full_name LIKE ? OR username LIKE ? OR group_name LIKE ?)"
                    p = f"%{search.strip()}%"
                    params.extend([p, p, p])

                if status_filter and status_filter != "all":
                    query += " AND status = ?"
                    params.append(status_filter)

                query += " ORDER BY last_active DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "user_id": r[1],
                        "full_name": r[2],
                        "username": r[3],
                        "group_name": r[4],
                        "questions_count": r[5],
                        "strengths": r[6] or "",
                        "weaknesses": r[7] or "",
                        "mentor_notes": r[8] or "",
                        "status": r[9] or "yaxshi",
                        "last_active": str(r[10]),
                        "created_at": str(r[11]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("O'quvchilarni olishda xatolik: %s", e)
            return []

    def get_student_by_id(self, student_id: int) -> dict | None:
        """ID bo'yicha bitta o'quvchini oladi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, user_id, full_name, username, group_name, questions_count, strengths, weaknesses, mentor_notes, status, last_active, created_at FROM students WHERE id = ?",
                    (student_id,),
                )
                r = cursor.fetchone()
                if not r:
                    return None
                return {
                    "id": r[0],
                    "user_id": r[1],
                    "full_name": r[2],
                    "username": r[3],
                    "group_name": r[4],
                    "questions_count": r[5],
                    "strengths": r[6] or "",
                    "weaknesses": r[7] or "",
                    "mentor_notes": r[8] or "",
                    "status": r[9] or "yaxshi",
                    "last_active": str(r[10]),
                    "created_at": str(r[11]),
                }
        except Exception as e:
            logger.error("O'quvchini ID bo'yicha olishda xatolik: %s", e)
            return None

    def update_student(self, student_id: int, **kwargs) -> bool:
        """O'quvchi ma'lumotlarini qisman yangilaydi."""
        allowed_fields = {"full_name", "username", "group_name", "status", "strengths", "weaknesses", "mentor_notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        try:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values())
            values.append(student_id)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE students SET {set_clause}, last_active = CURRENT_TIMESTAMP WHERE id = ?", values)
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("O'quvchini yangilashda xatolik: %s", e)
            return False

    def delete_student(self, student_id: int) -> bool:
        """O'quvchini bazadan o'chiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("O'quvchini o'chirishda xatolik: %s", e)
            return False

    # -----------------------------------------------------------
    # Aqlli Lokatsiya Xotirasi (Saved Locations)
    # -----------------------------------------------------------
    def add_saved_location(self, name: str, lat: float, long: float, address: str = "") -> int:
        """Yangi joylashuvni nom bilan saqlaydi."""
        clean = name.lower().strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO saved_locations (name, name_clean, lat, long, address)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name.strip(), clean, lat, long, address.strip()),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error("Lokatsiyani saqlashda xatolik: %s", e)
            return 0

    def get_saved_location(self, query: str) -> dict | None:
        """Nom bo'yicha eng mos lokatsiyani topadi."""
        clean = query.lower().strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Aniq moslik
                cursor.execute("SELECT id, name, lat, long, address, created_at FROM saved_locations WHERE name_clean = ? ORDER BY id DESC LIMIT 1", (clean,))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "name": row[1],
                        "lat": row[2],
                        "long": row[3],
                        "latitude": row[2],
                        "longitude": row[3],
                        "address": row[4],
                        "created_at": str(row[5]),
                    }

                # 2. Qidiruv mosligi (LIKE)
                cursor.execute("SELECT id, name, lat, long, address, created_at FROM saved_locations WHERE name_clean LIKE ? ORDER BY id DESC LIMIT 1", (f"%{clean}%",))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "name": row[1],
                        "lat": row[2],
                        "long": row[3],
                        "latitude": row[2],
                        "longitude": row[3],
                        "address": row[4],
                        "created_at": str(row[5]),
                    }
                return None
        except Exception as e:
            logger.error("Lokatsiyani qidirishda xatolik: %s", e)
            return None

    def list_saved_locations(self, limit: int = 50) -> list[dict]:
        """Barcha saqlangan joylashuvlar ro'yxatini qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, lat, long, address, created_at FROM saved_locations ORDER BY id DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "name": r[1],
                        "lat": r[2],
                        "long": r[3],
                        "latitude": r[2],
                        "longitude": r[3],
                        "address": r[4],
                        "created_at": str(r[5]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Lokatsiyalar ro'yxatini olishda xatolik: %s", e)
            return []

    def delete_saved_location(self, loc_id: int) -> bool:
        """Lokatsiyani o'chiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM saved_locations WHERE id = ?", (loc_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Lokatsiyani o'chirishda xatolik: %s", e)
            return False

    # -----------------------------------------------------------
    # Kunlik Rejalar va Vazifalar (Daily Plans / Checklist)
    # -----------------------------------------------------------
    def add_daily_plan(self, title: str, plan_date: str, plan_time: str = "", priority: str = "normal") -> int:
        """Kunlik rejaga yangi vazifa qo'shadi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO daily_plans (title, plan_date, plan_time, is_completed, priority)
                    VALUES (?, ?, ?, 0, ?)
                    """,
                    (title.strip(), plan_date.strip(), plan_time.strip(), priority),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error("Rejani saqlashda xatolik: %s", e)
            return 0

    def get_plans_for_date(self, plan_date: str) -> list[dict]:
        """Muayyan sanadagi barcha rejalarni qaytaradi (YYYY-MM-DD)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, title, plan_date, plan_time, is_completed, priority, created_at
                    FROM daily_plans
                    WHERE plan_date = ?
                    ORDER BY plan_time ASC, id ASC
                    """,
                    (plan_date,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "title": r[1],
                        "plan_text": r[1],
                        "plan_date": r[2],
                        "plan_time": r[3],
                        "is_completed": bool(r[4]),
                        "status": "completed" if r[4] else "pending",
                        "priority": r[5],
                        "created_at": str(r[6]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Sanadagi rejalarni olishda xatolik: %s", e)
            return []

    def mark_plan_completed(self, plan_id: int, is_completed: bool = True) -> bool:
        """Rejadagi vazifani bajarilgan yoki kutilayotgan deb belgilaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE daily_plans SET is_completed = ? WHERE id = ?", (1 if is_completed else 0, plan_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Reja holatini yangilashda xatolik: %s", e)
            return False

    def delete_daily_plan(self, plan_id: int) -> bool:
        """Rejani o'chiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM daily_plans WHERE id = ?", (plan_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Rejani o'chirishda xatolik: %s", e)
            return False

    # -----------------------------------------------------------
    # Agent IQ, Level va Ko'nikmalar Statistikasi
    # -----------------------------------------------------------
    def get_agent_stats(self) -> dict:
        """Agentning real-time intellekt darajasi, leveli, XP va o'rganilgan bilimlarini hisoblaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM messages")
                total_msgs = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM students")
                total_students = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM reminders WHERE is_sent = 1")
                sent_reminders = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM saved_locations")
                total_locations = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM learned_memory")
                total_learned = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM daily_plans WHERE is_completed = 1")
                completed_plans = cursor.fetchone()[0]

                # Tajriba ballari (XP) formulasi:
                # Har bir xabar: 1 XP
                # Har bir o'quvchi: 10 XP
                # Har bir bajarilgan eslatma/reja: 15 XP
                # Har bir o'rganilgan fakt/manzil: 25 XP
                xp = (total_msgs * 1) + (total_students * 10) + ((sent_reminders + completed_plans) * 15) + ((total_locations + total_learned) * 25)
                
                # Level hisoblash: Har 250 XP da yangi Level
                level = max(1, (xp // 250) + 1)
                xp_current_level = xp % 250
                progress_pct = int((xp_current_level / 250) * 100)

                # IQ Indeksi va Tahlilini hisoblash (Base: 115 IQ + tajriba/o'rganishlar orqali oshib boradi)
                iq_bonus = min(50, int((level * 2.5) + (total_learned * 2.0) + (total_students * 1.5) + (total_locations * 2.0) + (completed_plans * 1.5)))
                iq_score = 115 + iq_bonus

                if iq_score < 125:
                    iq_status = "Aqlli Yordamchi (Smart AI)"
                elif iq_score < 140:
                    iq_status = "Yuqori Intellekt (High IQ)"
                elif iq_score < 155:
                    iq_status = "Katta Strategik Hamkor (Superior IQ)"
                else:
                    iq_status = "Daho Avtonom AI (Genius Level)"

                # Kognitiv qobiliyatlar tahlili (0-100% shkalada)
                cognitive_metrics = {
                    "memory_depth": min(100, max(20, int(35 + (total_learned * 5) + (total_locations * 6)))),
                    "pedagogical_analysis": min(100, max(20, int(45 + (total_students * 6)))),
                    "adaptive_intelligence": min(100, max(30, int(50 + (level * 4)))),
                    "execution_discipline": min(100, max(20, int(40 + (completed_plans * 10) + (sent_reminders * 5)))),
                }

                # Unvonlar
                if level < 5:
                    title = "Kichik AI Yordamchi (Junior Co-Pilot)"
                elif level < 12:
                    title = "O'rta Darajadagi Shaxsiy Assistent (Middle Co-Pilot)"
                elif level < 25:
                    title = "Katta Hayotiy va Ish Boshqaruvchisi (Senior Executive Co-Pilot)"
                else:
                    title = "Master Avtonom AI Hamkor (Master Autonomous AI)"

                emergency_id = self.get_setting("emergency_contact_id", "5023430798")

                return {
                    "level": level,
                    "title": title,
                    "iq_score": iq_score,
                    "iq_status": iq_status,
                    "cognitive_metrics": cognitive_metrics,
                    "total_xp": xp,
                    "current_level_xp": xp_current_level,
                    "next_level_xp": 250,
                    "progress_pct": progress_pct,
                    "total_messages": total_msgs,
                    "total_students": total_students,
                    "sent_reminders": sent_reminders,
                    "total_locations": total_locations,
                    "total_learned_facts": total_learned,
                    "completed_plans": completed_plans,
                    "emergency_contact_id": emergency_id,
                }
        except Exception as e:
            logger.error("Agent statistikasini hisoblashda xatolik: %s", e)
            return {
                "level": 1,
                "title": "Boshlang'ich AI Yordamchi",
                "total_xp": 0,
                "progress_pct": 0,
                "emergency_contact_id": "5023430798",
            }

    # -----------------------------------------------------------
    # Baza xavfsizligi, tiklash va birlashtirish (Database Merge)
    # -----------------------------------------------------------
    def is_database_empty(self) -> bool:
        """Baza yangi yoki bo'sh ekanligini aniqlaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM messages")
                msg_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM reminders")
                rem_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM students")
                stu_count = cursor.fetchone()[0]
                return (msg_count + rem_count + stu_count) == 0
        except Exception:
            return True

    def merge_database(self, source_db_path: Path | str) -> tuple[bool, str]:
        """
        Boshqa SQLite faylidagi ma'lumotlarni (messages, settings, ignored_users, reminders, students)
        joriy faol bazaga xavfsiz birlashtiradi (INSERT OR IGNORE).
        """
        source = Path(source_db_path)
        if not source.exists():
            return False, f"{source} fayli topilmadi"

        try:
            with sqlite3.connect(str(source)) as s_conn:
                s_cursor = s_conn.cursor()

                s_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in s_cursor.fetchall()}

                imported_stats = []
                with self._get_connection() as target_conn:
                    # 1. messages
                    if "messages" in tables:
                        s_cursor.execute("SELECT chat_id, role, content, created_at FROM messages")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO messages (chat_id, role, content, created_at)
                            SELECT ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM messages WHERE chat_id = ? AND role = ? AND content = ? AND created_at = ?
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[0], r[1], r[2], r[3]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta xabar")

                    # 2. settings
                    if "settings" in tables:
                        s_cursor.execute("SELECT key, value FROM settings")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                            rows,
                        )
                        imported_stats.append(f"{len(rows)} ta sozlama")

                    # 3. ignored_users
                    if "ignored_users" in tables:
                        s_cursor.execute("SELECT user_id, username, created_at FROM ignored_users")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            "INSERT OR IGNORE INTO ignored_users (user_id, username, created_at) VALUES (?, ?, ?)",
                            rows,
                        )

                    # 4. reminders
                    if "reminders" in tables:
                        s_cursor.execute("SELECT chat_id, creator_id, reminder_text, remind_at, is_sent, created_at FROM reminders")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO reminders (chat_id, creator_id, reminder_text, remind_at, is_sent, created_at)
                            SELECT ?, ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM reminders WHERE chat_id = ? AND reminder_text = ? AND remind_at = ?
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[4], r[5], r[0], r[2], r[3]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta eslatma")

                    # 5. students
                    if "students" in tables:
                        s_cursor.execute("SELECT user_id, full_name, username, group_name, questions_count, strengths, weaknesses, mentor_notes, status, last_active, created_at FROM students")
                        rows = s_cursor.fetchall()
                        for r in rows:
                            target_conn.execute(
                                """
                                INSERT INTO students (user_id, full_name, username, group_name, questions_count, strengths, weaknesses, mentor_notes, status, last_active, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(user_id) DO UPDATE SET
                                    questions_count = MAX(students.questions_count, excluded.questions_count),
                                    group_name = CASE WHEN excluded.group_name != '' THEN excluded.group_name ELSE students.group_name END,
                                    status = CASE WHEN excluded.status != '' THEN excluded.status ELSE students.status END,
                                    mentor_notes = CASE WHEN excluded.mentor_notes != '' THEN excluded.mentor_notes ELSE students.mentor_notes END
                                """,
                                r,
                            )
                        imported_stats.append(f"{len(rows)} ta o'quvchi")

                    target_conn.commit()

            msg = "Muvaffaqiyatli birlashtirildi: " + ", ".join(imported_stats)
            logger.info("Baza birlashtirildi (%s): %s", source.name, msg)
            return True, msg
        except Exception as e:
            logger.error("Baza birlashtirishda xatolik: %s", e)
            return False, str(e)


# Global xotira instansiyasi
memory_service = SQLiteMemoryService()
