"""
Doimiy SQLite xotira xizmati (Persistent Memory)
Suhbatlar kompyuter o'chsa yoki dastur qayta ishga tushsa ham saqlanib qoladi.
"""

import logging
import sqlite3
import re
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from config import config
from services.mongo_memory_service import mongo_memory_service

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "coddy_memory.db"


@dataclass
class ChatMessage:
    role: Literal["user", "model"]
    content: str
    created_at: str | None = None


class SQLiteMemoryService:
    def __init__(self, db_path: Path = DB_PATH, limit: int = 15):
        self.db_path = db_path
        self.limit = config.memory_limit or limit
        self._settings_cache: dict[str, str] = {}
        self._init_db()
        try:
            if mongo_memory_service.is_connected():
                # Dastlabki ishga tushishda: 1. Avval MongoDB Atlas'dan SQLite ga tiklash (Auto-Restore)
                restore_stats = mongo_memory_service.restore_to_sqlite(self.db_path)
                logger.info("🔄 [Startup] MongoDB→SQLite restore yakunlandi: %s", restore_stats)
                # 2. So'ngra yangi lokal ma'lumotlarni MongoDB ga sinxronlash
                mongo_memory_service.migrate_from_sqlite(self.db_path)
            else:
                logger.warning("⚠️ [Startup] MongoDB ulanmagan! Foydalanuvchi ro'yxati restore bo'lmadi.")
        except Exception as me:
            logger.warning("⚠️ MongoDB bilan avto-sinxronlashda xatolik: %s", me)
        try:
            from services.obsidian_brain_service import obsidian_brain_service
            obsidian_brain_service.init_vault()
        except Exception as oe:
            logger.debug("Obsidian vault init ogohlantirish: %s", oe)

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
                        user_id INTEGER,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                try:
                    conn.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER")
                except Exception:
                    pass
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_id ON messages (chat_id, id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_user ON messages (chat_id, user_id, id)"
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
                    CREATE TABLE IF NOT EXISTS user_quotas (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        max_messages INTEGER NOT NULL,
                        current_count INTEGER DEFAULT 0,
                        notify_text TEXT DEFAULT '',
                        reason TEXT DEFAULT '',
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
                        user_id INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                try:
                    conn.execute("ALTER TABLE learned_memory ADD COLUMN user_id INTEGER DEFAULT 0")
                except Exception:
                    pass
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_learned_topic ON learned_memory (topic)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_learned_user ON learned_memory (user_id)"
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS precomputed_answers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        question_pattern TEXT NOT NULL,
                        answer_text TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mentor_lexicon (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        term TEXT UNIQUE NOT NULL,
                        meaning TEXT NOT NULL,
                        example TEXT DEFAULT '',
                        confidence REAL DEFAULT 1.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mentor_lexicon_term ON mentor_lexicon (term)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS self_mistakes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        situation TEXT NOT NULL,
                        mistake TEXT NOT NULL,
                        correction TEXT NOT NULL,
                        rule TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS active_inquiries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        target_user_id INTEGER NOT NULL,
                        target_username TEXT DEFAULT '',
                        target_name TEXT DEFAULT '',
                        question_text TEXT NOT NULL,
                        expected_info TEXT NOT NULL,
                        mentor_chat_id TEXT DEFAULT '',
                        status TEXT DEFAULT 'pending',
                        result_summary TEXT DEFAULT '',
                        attempts INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_active_inquiries_user ON active_inquiries (target_user_id, status)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS student_weaknesses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        topic TEXT NOT NULL,
                        error_count INTEGER DEFAULT 1,
                        last_question TEXT DEFAULT '',
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(student_id, topic)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_student_weaknesses_user ON student_weaknesses (student_id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_dossiers (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT DEFAULT '',
                        first_name TEXT DEFAULT '',
                        last_name TEXT DEFAULT '',
                        phone TEXT DEFAULT '',
                        bio TEXT DEFAULT '',
                        channel_username TEXT DEFAULT '',
                        channel_summary TEXT DEFAULT '',
                        photo_count INTEGER DEFAULT 0,
                        has_stories INTEGER DEFAULT 0,
                        dossier_text TEXT NOT NULL,
                        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_dossiers_analyzed ON user_dossiers (analyzed_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pedagogical_outcomes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        topic TEXT NOT NULL,
                        question TEXT NOT NULL,
                        answer_snippet TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        student_reaction TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pedagogical_outcomes_topic ON pedagogical_outcomes (topic, outcome)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS high_yield_pedagogy (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL UNIQUE,
                        winning_analogy TEXT NOT NULL,
                        success_count INTEGER DEFAULT 1,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_interaction_patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bot_username TEXT NOT NULL,
                        pattern_type TEXT NOT NULL,
                        observation_summary TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT DEFAULT '',
                        full_name TEXT DEFAULT '',
                        phone TEXT DEFAULT '',
                        business_name TEXT DEFAULT '',
                        profession TEXT DEFAULT '',
                        system_prompt TEXT DEFAULT '',
                        group_id INTEGER DEFAULT 0,
                        active INTEGER DEFAULT 1,
                        expires_at TIMESTAMP,
                        role TEXT DEFAULT 'client',
                        session_string TEXT DEFAULT '',
                        session_active INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_subs_group_id ON user_subscriptions (group_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_subs_active ON user_subscriptions (active, expires_at)"
                )
                # Mavjud DB ga yangi ustunlar qo'shish (migration)
                for col_def in [
                    "ALTER TABLE user_subscriptions ADD COLUMN session_string TEXT DEFAULT ''",
                    "ALTER TABLE user_subscriptions ADD COLUMN session_active INTEGER DEFAULT 0",
                ]:
                    try:
                        conn.execute(col_def)
                    except Exception:
                        pass  # Ustun allaqachon mavjud
                # Standart doimiy sozlamalar (Render restart bo'lganda ham avto-javoblar doimo YOQIQ turishi uchun)
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_reply_enabled', 'true')")
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('group_reply_enabled', 'true')")
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('voice_reply_enabled', 'true')")
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('web_search_enabled', 'true')")
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('silent_mode_enabled', 'false')")
                conn.commit()
        except Exception as e:
            logger.error("SQLite xotirasini ishga tushirishda xatolik: %s", e)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Doimiy sozlamani chaqmoqdek tez o'qiydi (Xotira keshi -> SQLite -> MongoDB fallback)."""
        # 1. Tezkor xotira keshi (0.0001 ms)
        if hasattr(self, "_settings_cache") and key in self._settings_cache:
            return self._settings_cache[key]

        # 2. Lokal SQLite (<1 ms)
        val = None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    val = row[0]
        except Exception as e:
            logger.debug("Sozlamani SQLite'dan o'qishda ogohlantirish: %s", e)

        # 3. Agar SQLite'da topilmasa, MongoDB Atlas'dan fallback qilib olib, keshlaymiz
        if val is None:
            try:
                if mongo_memory_service.is_connected():
                    val = mongo_memory_service.get_setting(key, None)
                    if val is not None:
                        # SQLite ga ham saqlab qo'yamiz
                        try:
                            with self._get_connection() as conn:
                                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))
                                conn.commit()
                        except Exception:
                            pass
            except Exception:
                pass

        final_val = val if val is not None else default
        if final_val is not None:
            if not hasattr(self, "_settings_cache"):
                self._settings_cache = {}
            self._settings_cache[key] = final_val
        return final_val

    def set_setting(self, key: str, value: str) -> None:
        """Doimiy sozlamani saqlaydi (Kesh + SQLite darhol + MongoDB Atlas sync)."""
        if not hasattr(self, "_settings_cache"):
            self._settings_cache = {}
        self._settings_cache[key] = str(value)

        # 1. SQLite'ga darhol yozish (<1 ms)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
                conn.commit()
        except Exception as e:
            logger.error("Sozlamani saqlashda xatolik: %s", e)

        # 2. MongoDB Atlas'ga orqa fonda / sinxron saqlash
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.set_setting(key, str(value))
        except Exception:
            pass

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

    def get_curriculum_topics(self, user_id: int = 0) -> list[str]:
        """O'quv yoki biznes mavzulari ro'yxatini qaytaradi.
        user_id=0 (Super Admin) bo'lsa CoddyCamp steki.
        user_id>0 bo'lsa, o'sha mijozning shaxsiy biznes mavzulari (dastlab toza / bo'sh).
        """
        import json
        if user_id and not self.is_super_admin(user_id):
            raw = self.get_setting(f"client_topics_{user_id}")
            if not raw:
                return []
            try:
                topics = json.loads(raw)
                return topics if isinstance(topics, list) else []
            except Exception:
                return []

        raw = self.get_setting("curriculum_topics")
        if not raw:
            return list(self.DEFAULT_CURRICULUM_TOPICS)
        try:
            topics = json.loads(raw)
            return topics if isinstance(topics, list) and topics else list(self.DEFAULT_CURRICULUM_TOPICS)
        except Exception:
            return list(self.DEFAULT_CURRICULUM_TOPICS)

    def set_curriculum_topics(self, topics: list[str], user_id: int = 0) -> None:
        """Mavzular ro'yxatini saqlaydi."""
        import json
        clean_topics = []
        for t in topics:
            val = str(t).strip()
            if val and val not in clean_topics:
                clean_topics.append(val)
        setting_key = f"client_topics_{user_id}" if (user_id and not self.is_super_admin(user_id)) else "curriculum_topics"
        self.set_setting(setting_key, json.dumps(clean_topics))

    def add_curriculum_topic(self, topic: str, user_id: int = 0) -> bool:
        """Yangi mavzuni qo'shadi."""
        t = str(topic).strip()
        if not t:
            return False
        current = self.get_curriculum_topics(user_id=user_id)
        if any(c.lower() == t.lower() for c in current):
            return True
        current.append(t)
        self.set_curriculum_topics(current, user_id=user_id)
        return True

    def remove_curriculum_topic(self, topic: str, user_id: int = 0) -> bool:
        """Mavzuni ro'yxatdan olib tashlaydi."""
        t = str(topic).strip().lower()
        current = self.get_curriculum_topics(user_id=user_id)
        filtered = [c for c in current if c.lower() != t]
        if len(filtered) == len(current):
            return False
        self.set_curriculum_topics(filtered, user_id=user_id)
        return True

    def add_message(self, chat_id: int, role: Literal["user", "model"], content: str, user_id: Optional[int] = None) -> None:
        """Yangi xabarni doimiy bazaga qo'shadi (Dual-Persistence: MongoDB + SQLite)."""
        if not content or not content.strip():
            return

        # 1. MongoDB Atlas'ga yozish
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.add_conversation_message(chat_id, role, content.strip(), sender_id=user_id)
        except Exception as me:
            logger.debug("MongoDB ga suhbat yozishda ogohlantirish: %s", me)

        # 2. Mahalliy SQLite keshiga yozish
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO messages (chat_id, user_id, role, content) VALUES (?, ?, ?, ?)",
                    (chat_id, user_id, role, content.strip()),
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

    def get_history(self, chat_id: int, user_id: Optional[int] = None) -> list[ChatMessage]:
        """Oxirgi N ta xabarlar tarixini xronologik tartibda vaqti (Toshkent vaqti) bilan qaytaradi (MongoDB -> SQLite)."""
        try:
            if mongo_memory_service.is_connected():
                docs = mongo_memory_service.get_conversation_history(chat_id, limit=self.limit, sender_id=user_id)
                if docs:
                    return [
                        ChatMessage(
                            role=d["role"],
                            content=d["content"],
                            created_at=str(d.get("created_at") or d.get("timestamp") or "")
                        )
                        for d in docs
                    ]
        except Exception as me:
            logger.debug("MongoDB dan tarixni olishda ogohlantirish: %s", me)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if user_id is not None and chat_id < 0:
                    cursor.execute(
                        """
                        SELECT role, content, datetime(created_at, '+5 hours') FROM (
                            SELECT id, role, content, created_at FROM messages 
                            WHERE chat_id = ? AND (user_id = ? OR user_id IS NULL)
                            ORDER BY id DESC LIMIT ?
                        ) ORDER BY id ASC
                        """,
                        (chat_id, user_id, self.limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT role, content, datetime(created_at, '+5 hours') FROM (
                            SELECT id, role, content, created_at FROM messages 
                            WHERE chat_id = ? 
                            ORDER BY id DESC LIMIT ?
                        ) ORDER BY id ASC
                        """,
                        (chat_id, self.limit),
                    )
                rows = cursor.fetchall()
                return [
                    ChatMessage(
                        role=r[0],
                        content=r[1],
                        created_at=str(r[2]) if len(r) > 2 and r[2] else None
                    )
                    for r in rows
                ]
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

    def get_students_count(self) -> int:
        """Talabalar sonini SQLite'dan 0.1ms da hisoblaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM students")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_active_reminders_count(self) -> int:
        """Faol eslatmalar sonini SQLite'dan 0.1ms da hisoblaydi."""
        now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM reminders WHERE is_sent = 0 AND remind_at >= ?", (now_str,))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_ignored_users_count(self) -> int:
        """Bloklanganlar sonini SQLite'dan 0.1ms da hisoblaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM ignored_users")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_learned_facts_count(self) -> int:
        """Bilimlar (insights) sonini SQLite'dan 0.1ms da hisoblaydi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM learned_memory")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
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
            if mongo_memory_service.is_connected():
                mongo_memory_service.blacklist_user(user_id=user_id, username=username, reason=reason)
        except Exception:
            pass

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
        ok = False
        try:
            if mongo_memory_service.is_connected():
                if mongo_memory_service.unblacklist_user(user_id):
                    ok = True
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ignored_users WHERE user_id = ?", (user_id,))
                conn.commit()
                if cursor.rowcount > 0:
                    ok = True
        except Exception as e:
            logger.error("Foydalanuvchini ignore ro'yxatidan o'chirishda xatolik: %s", e)
        return ok

    def is_user_ignored(self, user_id: int) -> bool:
        """Foydalanuvchi bloklanganligini tekshiradi."""
        try:
            if mongo_memory_service.is_connected():
                if mongo_memory_service.is_user_blacklisted(user_id):
                    return True
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM ignored_users WHERE user_id = ?", (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error("Ignore holatini tekshirishda xatolik: %s", e)
            return False

    def get_ignored_users(self) -> list[dict]:
        """Bloklangan barcha foydalanuvchilar ro'yxati (Lokal SQLite -> Mongo fallback)."""
        try:
            with self._get_connection() as conn:
                try:
                    conn.execute("ALTER TABLE ignored_users ADD COLUMN reason TEXT DEFAULT ''")
                except Exception:
                    pass
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, username, created_at, COALESCE(reason, '') FROM ignored_users ORDER BY created_at DESC")
                rows = cursor.fetchall()
                if rows:
                    return [{"user_id": r[0], "username": r[1], "created_at": r[2], "reason": r[3]} for r in rows]
        except Exception as e:
            logger.debug("Ignore ro'yxatini SQLite'dan olishda ogohlantirish: %s", e)

        # Fallback to Mongo if SQLite is empty
        try:
            if mongo_memory_service.is_connected():
                m_users = mongo_memory_service.get_all_blacklisted_users()
                if m_users:
                    return [
                        {
                            "user_id": u.get("user_id"),
                            "username": u.get("username", ""),
                            "created_at": str(u.get("created_at", "")),
                            "reason": u.get("reason", ""),
                        }
                        for u in m_users
                    ]
        except Exception:
            pass
        return []

    def set_user_message_quota(
        self,
        user_id: int,
        max_messages: int,
        username: str = "",
        notify_text: str = "",
        reason: str = "",
        block_in_telegram: bool = False,
    ) -> None:
        """Foydalanuvchiga xabarlar soni bo'yicha limit (quota) o'rnatadi. Limitga yetganda avtomatik bloklanadi."""
        try:
            from config import config
            if user_id in (config.mentor_user_id, 8105823872):
                logger.warning("Xavfsizlik: Mentorni quota/ignore qilish mumkin emas!")
                return
        except Exception:
            if user_id == 8105823872:
                return

        try:
            with self._get_connection() as conn:
                try:
                    conn.execute("ALTER TABLE user_quotas ADD COLUMN block_in_telegram INTEGER DEFAULT 0")
                except Exception:
                    pass
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_quotas 
                    (user_id, username, max_messages, current_count, notify_text, reason, block_in_telegram) 
                    VALUES (?, ?, ?, 0, ?, ?, ?)
                    """,
                    (user_id, username, max(1, max_messages), notify_text, reason, 1 if block_in_telegram else 0),
                )
                conn.commit()
                logger.info("Foydalanuvchi %s uchun %d ta xabarlik quota belgilandi (block_in_telegram=%s).", user_id, max_messages, block_in_telegram)
        except Exception as e:
            logger.error("User quota belgilashda xatolik: %s", e)

    def get_user_quota(self, user_id: int) -> dict | None:
        """Foydalanuvchining faol quotasi mavjudligini qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_id, username, max_messages, current_count, notify_text, reason, COALESCE(block_in_telegram, 0) FROM user_quotas WHERE user_id = ?",
                    (user_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1] or "",
                        "max_messages": row[2],
                        "current_count": row[3],
                        "notify_text": row[4] or "",
                        "reason": row[5] or "",
                        "block_in_telegram": bool(row[6]),
                    }
        except Exception as e:
            logger.error("User quota olishda xatolik: %s", e)
        return None

    def check_user_quota_limit(self, user_id: int) -> dict | None:
        """
        Foydalanuvchi xabar yuborganda hisoblagichni 1 taga oshiradi.
        Agar limitga yetsa, avtomatik ignore_user qiladi va exceeded=True qaytaradi.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT max_messages, current_count, username, notify_text, reason, COALESCE(block_in_telegram, 0) FROM user_quotas WHERE user_id = ?",
                    (user_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                max_m, cur_c, uname, n_text, r_text, b_tg = row
                new_c = cur_c + 1
                if new_c >= max_m:
                    # Limit tugadi! Foydalanuvchini bloklaymiz va quota jadvalidan tozalaymiz
                    cursor.execute("DELETE FROM user_quotas WHERE user_id = ?", (user_id,))
                    conn.commit()
                    self.ignore_user(user_id, username=uname or "", reason=r_text or f"Xabarlar limiti ({max_m} ta) tugadi")
                    return {
                        "exceeded": True,
                        "user_id": user_id,
                        "username": uname or "",
                        "notify_text": n_text or "",
                        "reason": r_text or f"{max_m} ta xabardan so'ng bloklandi",
                        "max_messages": max_m,
                        "block_in_telegram": bool(b_tg),
                    }
                else:
                    cursor.execute("UPDATE user_quotas SET current_count = ? WHERE user_id = ?", (new_c, user_id))
                    conn.commit()
                    return {
                        "exceeded": False,
                        "user_id": user_id,
                        "username": uname or "",
                        "current_count": new_c,
                        "remaining": max_m - new_c,
                        "max_messages": max_m,
                    }
        except Exception as e:
            logger.error("User quota tekshirishda xatolik: %s", e)
        return None

    def clear_user_quota(self, user_id: int) -> bool:
        """Foydalanuvchi quotasini bekor qiladi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_quotas WHERE user_id = ?", (user_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("User quotani o'chirishda xatolik: %s", e)
            return False

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

    def get_recent_mentor_messages(self, limit: int = 30) -> list[str]:
        """Mentor tomonidan yozilgan so'nggi xabarlarni oladi (slang/leksikon tahlili uchun)."""
        try:
            from config import config
            vazifalar_group = self.get_setting("vazifalar_group_id")
            valid_chat_ids = [config.mentor_user_id, 8105823872]
            if vazifalar_group and vazifalar_group.lstrip("-").isdigit():
                valid_chat_ids.append(int(vazifalar_group))

            placeholders = ",".join("?" for _ in valid_chat_ids)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT content FROM messages WHERE chat_id IN ({placeholders}) AND role = 'user' ORDER BY id DESC LIMIT ?",
                    (*valid_chat_ids, limit),
                )
                rows = cursor.fetchall()
                if not rows or len(rows) < 2:
                    cursor.execute(
                        "SELECT content FROM messages WHERE role = 'user' ORDER BY id DESC LIMIT ?",
                        (limit,),
                    )
                    rows = cursor.fetchall()
                return [r[0] for r in rows if r[0] and len(r[0].strip()) > 1]
        except Exception as e:
            logger.error("Mentor xabarlarini olishda xatolik: %s", e)
            return []

    def get_recent_dialogues_for_reflection(self, limit: int = 15) -> list[dict[str, str]]:
        """Miya 4 o'z xatolarini tahlil qilishi uchun so'nggi suhbat juftliklarini oladi."""
        try:
            from config import config
            vazifalar_group = self.get_setting("vazifalar_group_id")
            valid_chat_ids = [config.mentor_user_id, 8105823872]
            if vazifalar_group and vazifalar_group.lstrip("-").isdigit():
                valid_chat_ids.append(int(vazifalar_group))

            placeholders = ",".join("?" for _ in valid_chat_ids)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT role, content FROM messages WHERE chat_id IN ({placeholders}) ORDER BY id DESC LIMIT ?",
                    (*valid_chat_ids, limit * 2),
                )
                rows = cursor.fetchall()
                if not rows or len(rows) < 2:
                    cursor.execute(
                        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
                        (limit * 2,),
                    )
                    rows = cursor.fetchall()

                rows = list(reversed(rows))
                dialogues = []
                for i in range(len(rows) - 1):
                    # CoddyHelper ba'zan 'model', ba'zan 'assistant' deb saqlaydi - ikkalasini ham qabul qilish:
                    if rows[i][0] in ("model", "assistant") and rows[i + 1][0] == "user":
                        dialogues.append({
                            "assistant": rows[i][1][:300],
                            "user_feedback": rows[i + 1][1][:300],
                        })
                return dialogues
        except Exception as e:
            logger.error("Suhbatlarni tahlil uchun olishda xatolik: %s", e)
            return []


    # -----------------------------------------------------------
    # O'z ustida ishlash va Bilimlar Bazasi (Continuous Learning)
    # -----------------------------------------------------------
    def add_learned_fact(self, topic: str, content: str, category: str = "rule", user_id: int = 0) -> int:
        """Mentor ko'rsatmasi, qoidasi yoki yangi faktni doimiy xotiraga yozadi (Dual-Persistence).
        user_id=0 (Super Admin/Global), user_id>0 bo'lsa o'sha mijozning shaxsiy bilimi.
        """
        t = topic.strip()
        c = content.strip()
        if not t or not c:
            return 0

        # 1. MongoDB Atlas'ga saqlash va XP/IQ oshirish (faqat Super Admin uchun)
        if not user_id or self.is_super_admin(user_id):
            try:
                if mongo_memory_service.is_connected():
                    mongo_memory_service.save_learned_insight(key=t, content=c, category=category)
                    mongo_memory_service.update_cognitive_growth(xp_gain=15, iq_points=1, reason=f"O'rganildi: {t}")
            except Exception as me:
                logger.debug("MongoDB ga saboq yozishda ogohlantirish: %s", me)

        # 2. Mahalliy SQLite keshiga saqlash
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM learned_memory WHERE LOWER(topic) = LOWER(?) AND user_id = ?", (t, user_id))
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
                        "INSERT INTO learned_memory (category, topic, content, user_id) VALUES (?, ?, ?, ?)",
                        (category, t, c, user_id),
                    )
                    conn.commit()
                    res_id = cursor.lastrowid
                if not user_id or self.is_super_admin(user_id):
                    try:
                        from services.obsidian_brain_service import obsidian_brain_service
                        obsidian_brain_service.export_rule(t, c, source="mentor")
                    except Exception:
                        pass
                return res_id
        except Exception as e:
            logger.error("Yangi bilimni saqlashda xatolik: %s", e)
            return 0

    def get_all_learned_facts(self, limit: int = 50, user_id: int = 0) -> list[dict]:
        """Barcha o'rganilgan bilimlar va qoidalarni qaytaradi.
        user_id > 0 bo'lsa faqat o'sha mijozning bilimlari qaytadi (dastlab toza / bo'sh).
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if user_id and not self.is_super_admin(user_id):
                    cursor.execute(
                        "SELECT id, category, topic, content, created_at, updated_at FROM learned_memory WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                        (user_id, limit),
                    )
                else:
                    cursor.execute(
                        "SELECT id, category, topic, content, created_at, updated_at FROM learned_memory WHERE user_id = 0 OR user_id IS NULL ORDER BY id DESC LIMIT ?",
                        (limit,),
                    )
                rows = cursor.fetchall()
                if rows:
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
            logger.debug("O'rganilgan bilimlarni SQLite'dan olishda ogohlantirish: %s", e)

        # Agar bu mijoz bo'lsa, global CoddyCamp Mongo fallback kerak EMAS! Mijoz toza bo'lishi shart!
        if user_id and not self.is_super_admin(user_id):
            return []

        # Fallback to Mongo if SQLite is empty (faqat Super Admin uchun)
        try:
            if mongo_memory_service.is_connected():
                docs = mongo_memory_service.get_all_learned_insights()
                if docs:
                    return [
                        {
                            "id": str(d.get("_id", "")),
                            "category": d.get("category", "general"),
                            "topic": d.get("key", ""),
                            "content": d.get("content", ""),
                            "created_at": str(d.get("created_at", "")),
                            "updated_at": str(d.get("updated_at", "")),
                        }
                        for d in docs[:limit]
                    ]
        except Exception as me:
            logger.debug("MongoDB dan saboqlarni olishda ogohlantirish: %s", me)
        return []

    def delete_learned_fact(self, target: str | int, topic: str = None, user_id: int = 0) -> bool:
        """Bilimni mavzusi yoki ID si bo'yicha o'chiradi (MongoDB + SQLite)."""
        deleted = False
        target_str = str(target).strip() if target is not None else ""
        topic_str = str(topic).strip() if topic is not None else ""

        # 1. MongoDB Atlas dan o'chirish (faqat Super Admin uchun)
        if not user_id or self.is_super_admin(user_id):
            try:
                if mongo_memory_service.is_connected():
                    if target_str and mongo_memory_service.delete_learned_insight(target_str):
                        deleted = True
                    if topic_str and mongo_memory_service.delete_learned_insight(topic_str):
                        deleted = True
            except Exception as me:
                logger.debug("MongoDB dan bilim o'chirishda ogohlantirish: %s", me)

        # 2. SQLite dan ham o'chirish
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if user_id and not self.is_super_admin(user_id):
                    if target_str.isdigit():
                        cursor.execute("DELETE FROM learned_memory WHERE id = ? AND user_id = ?", (int(target_str), user_id))
                    elif target_str:
                        cursor.execute("DELETE FROM learned_memory WHERE LOWER(topic) = LOWER(?) AND user_id = ?", (target_str, user_id))
                else:
                    if target_str.isdigit():
                        cursor.execute("DELETE FROM learned_memory WHERE id = ?", (int(target_str),))
                    elif target_str:
                        cursor.execute("DELETE FROM learned_memory WHERE LOWER(topic) = LOWER(?)", (target_str,))
                if cursor.rowcount > 0:
                    deleted = True

                if topic_str:
                    if user_id and not self.is_super_admin(user_id):
                        cursor.execute("DELETE FROM learned_memory WHERE LOWER(topic) = LOWER(?) AND user_id = ?", (topic_str, user_id))
                    else:
                        cursor.execute("DELETE FROM learned_memory WHERE LOWER(topic) = LOWER(?)", (topic_str,))
                    if cursor.rowcount > 0:
                        deleted = True
                conn.commit()
        except Exception as e:
            logger.error("SQLite bilimni o'chirishda xatolik: %s", e)

        if deleted and (target_str or topic_str) and (not user_id or self.is_super_admin(user_id)):
            try:
                from services.obsidian_brain_service import obsidian_brain_service
                if topic_str:
                    obsidian_brain_service.delete_rule_note(topic_str)
                if target_str and not target_str.isdigit():
                    obsidian_brain_service.delete_rule_note(target_str)
            except Exception:
                pass

        return deleted

    def get_learned_facts(self, limit: int = 50) -> list[dict]:
        """get_all_learned_facts uchun qulay alias."""
        return self.get_all_learned_facts(limit=limit)

    def learn_fact(self, topic: str, content: str, category: str = "general") -> int:
        """add_learned_fact uchun qulay alias."""
        return self.add_learned_fact(topic=topic, content=content, category=category)

    def forget_fact(self, topic: str) -> bool:
        """delete_learned_fact uchun qulay alias."""
        return self.delete_learned_fact(target=topic)

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

    def record_autonomous_insight(self, topic: str, content: str) -> int:
        """Agent o'z tahlillari va tajribasidan chiqargan xulosasini saqlaydi."""
        return self.add_autonomous_insight(topic=topic, content=content, source="agent")

    def get_relevant_learned_insights(self, query: str, limit: int = 4) -> list[dict]:
        """
        Berilgan so'rov (query) bo'yicha eng dolzarb o'rganilgan bilimlar va tajribalarni qidirib topadi (Epizodik xotira / RAG).
        """
        if not query or not query.strip():
            return []
        try:
            import re
            raw_words = [w.strip().lower() for w in query.split() if len(w.strip()) >= 3]
            cleaned_words = []
            for w in raw_words:
                clean = re.sub(r"[^\w]", "", w)
                if len(clean) >= 3 and clean not in cleaned_words:
                    cleaned_words.append(clean)

            if not cleaned_words:
                return self.get_all_learned_facts(limit=limit)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                where_clauses = []
                params = []
                for w in cleaned_words[:6]:
                    where_clauses.append("(LOWER(topic) LIKE ? OR LOWER(content) LIKE ?)")
                    like_pattern = f"%{w}%"
                    params.extend([like_pattern, like_pattern])

                sql = f"""
                    SELECT id, category, topic, content, created_at, updated_at
                    FROM learned_memory
                    WHERE {' OR '.join(where_clauses)}
                    ORDER BY id DESC LIMIT ?
                """
                params.append(limit)
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
                if rows:
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
                return self.get_all_learned_facts(limit=min(limit, 2))
        except Exception as e:
            logger.error("Dolzarb bilimlarni qidirishda xatolik: %s", e)
            return []

    def get_autonomous_insights(self, limit: int = 50) -> list[dict]:
        """Agent tomonidan mustaqil o'rganilgan barcha saboqlar va tajribalarni qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, category, topic, content, source, created_at, updated_at
                    FROM learned_memory
                    WHERE category IN ('autonomous_insight', 'verified_insight') OR source = 'agent'
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "category": r[1],
                        "topic": r[2],
                        "content": r[3],
                        "source": r[4] or "agent",
                        "is_verified": (r[1] == "verified_insight"),
                        "created_at": r[5],
                        "updated_at": r[6],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Avtonom saboqlarni olishda xatolik: %s", e)
            return []

    def approve_autonomous_insight(self, insight_id: str | int) -> bool:
        """Mentor tomonidan avtonom saboqni tasdiqlash (MongoDB + SQLite)."""
        ok = False
        target_str = str(insight_id).strip()
        try:
            if mongo_memory_service.is_connected():
                if mongo_memory_service.approve_learned_insight(target_str):
                    ok = True
        except Exception as me:
            logger.debug("MongoDB da tasdiqlashda ogohlantirish: %s", me)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if target_str.isdigit():
                    cursor.execute(
                        "UPDATE learned_memory SET category = 'verified_insight', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (int(target_str),),
                    )
                else:
                    cursor.execute(
                        "UPDATE learned_memory SET category = 'verified_insight', updated_at = CURRENT_TIMESTAMP WHERE LOWER(topic) = LOWER(?)",
                        (target_str,),
                    )
                conn.commit()
                if cursor.rowcount > 0:
                    ok = True
        except Exception as e:
            logger.error("SQLite saboqni tasdiqlashda xatolik: %s", e)
        return ok

    def add_autonomous_insight(self, topic: str, content: str, source: str = "agent", **kwargs) -> int:
        """Avtonom miya tomonidan o'rganilgan yangi saboqni bazaga saqlaydi (Har bir yangi saboq mustaqil saqlanadi)."""
        t = topic.strip()
        c = content.strip()
        if not t or not c:
            return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Agar aynan shu mazmundagi saboq allaqachon mavjud bo'lsa, qayta qo'shmaslik (duplikatdan saqlanish)
                cursor.execute(
                    "SELECT id FROM learned_memory WHERE (LOWER(topic) = LOWER(?) AND LOWER(content) = LOWER(?)) OR LOWER(content) = LOWER(?)",
                    (t, c, c),
                )
                existing = cursor.fetchone()
                if existing:
                    return existing[0]

                # Har bir yangi saboq ALOHIDA MUSTAQIL yozuv sifatida qo'shiladi (eskilari o'chmaydi/yangilanmaydi):
                cursor.execute(
                    "INSERT INTO learned_memory (category, topic, content, source) VALUES (?, ?, ?, ?)",
                    ("autonomous_insight", t, c, source or "agent"),
                )
                conn.commit()
                logger.info("🧠 Yangi avtonom saboq saqlandi: [%s] %s", t[:30], c[:40])
                try:
                    from services.obsidian_brain_service import obsidian_brain_service
                    obsidian_brain_service.export_rule(t, c, source=source or "agent")
                except Exception:
                    pass
                return cursor.lastrowid
        except Exception as e:
            logger.error("Avtonom saboqni saqlashda xatolik: %s", e)
            return 0

    def add_precomputed_answer(self, topic: str, question_pattern: str, answer_text: str, **kwargs) -> int | None:
        """Kelgusida so'ralishi mumkin bo'lgan savollarga oldindan tayyorlangan mukammal javobni saqlaydi."""
        try:
            with self._get_connection() as conn:
                try:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS precomputed_answers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            topic TEXT NOT NULL,
                            question_pattern TEXT NOT NULL,
                            answer_text TEXT NOT NULL,
                            usage_count INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                except Exception:
                    pass
                try:
                    if mongo_memory_service.is_connected():
                        mongo_memory_service.save_precomputed_answer(
                            topic=topic.strip(),
                            question=question_pattern.strip(),
                            answer=answer_text.strip(),
                        )
                except Exception as me:
                    logger.debug("MongoDB ga precomputed answer yozishda ogohlantirish: %s", me)

                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO precomputed_answers (topic, question_pattern, answer_text)
                    VALUES (?, ?, ?)
                    """,
                    (topic.strip(), question_pattern.strip(), answer_text.strip()),
                )
                conn.commit()
                logger.info("Avtonom Miya oldindan javob saqladi: [%s] -> %s", topic, question_pattern[:40])
                return cur.lastrowid
        except Exception as e:
            logger.error("Oldindan tayyorlangan javobni saqlashda xatolik: %s", e)
            return None

    def find_precomputed_answer(self, query: str) -> dict | None:
        """
        Foydalanuvchi savoliga Miya 5 (Avtonom Ong) tomonidan oldindan tayyorlab qo'yilgan
        mukammal yechim mavjudligini tekshiradi (Substring + Kalit so'zlar o'xshashligi + MongoDB zaxirasi).
        """
        if not query or len(query.strip()) < 3:
            return None

        stopwords = {
            "qanday", "qilsa", "bo'ladi", "boladi", "nima", "uchun", "kerak", "qanaqa",
            "qaysi", "haqida", "bilan", "aytib", "bering", "iltimos", "salom", "assalomu",
            "alaykum", "как", "что", "это", "сделать", "почему", "для", "ли", "скажите", "пожалуйста"
        }

        try:
            q_lower = query.lower().strip()
            q_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", q_lower)) - stopwords

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, topic, question_pattern, answer_text FROM precomputed_answers ORDER BY usage_count DESC LIMIT 1000"
                )
                rows = cursor.fetchall()

                best_match = None
                best_score = 0.0

                for r in rows:
                    pat = (r[2] or "").lower().strip()
                    if not pat:
                        continue

                    # 1. Aniq qism-qator (Substring) mosligi: eng yuqori ustuvorlik
                    if len(pat) >= 5 and (pat in q_lower or q_lower in pat):
                        conn.execute("UPDATE precomputed_answers SET usage_count = usage_count + 1 WHERE id = ?", (r[0],))
                        conn.commit()
                        return {
                            "id": r[0],
                            "topic": r[1],
                            "question_pattern": r[2],
                            "answer_text": r[3],
                            "match_type": "exact_substring",
                        }

                    # 2. Kalit so'zlar (Token Overlap) tahlili
                    pat_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", pat)) - stopwords
                    if pat_tokens and q_tokens:
                        common = pat_tokens & q_tokens
                        if len(common) >= 2:
                            score = len(common) / len(pat_tokens)
                            if score > best_score and score >= 0.4:
                                best_score = score
                                best_match = r

                if best_match and best_score >= 0.4:
                    conn.execute("UPDATE precomputed_answers SET usage_count = usage_count + 1 WHERE id = ?", (best_match[0],))
                    conn.commit()
                    return {
                        "id": best_match[0],
                        "topic": best_match[1],
                        "question_pattern": best_match[2],
                        "answer_text": best_match[3],
                        "match_type": f"keyword_overlap_{int(best_score * 100)}%",
                    }

            # 3. Agar SQLite da topilmasa, MongoDB Atlas zaxirasini tekshirish
            mongo_items = mongo_memory_service.get_all_precomputed_answers(limit=50)
            for m in mongo_items:
                pat = (m.get("question_pattern") or "").lower().strip()
                ans = m.get("answer_text") or m.get("answer_code") or ""
                if not pat or not ans:
                    continue
                if len(pat) >= 5 and (pat in q_lower or q_lower in pat):
                    return {
                        "id": str(m.get("_id", "")),
                        "topic": m.get("topic", "Dasturlash"),
                        "question_pattern": pat,
                        "answer_text": ans,
                        "match_type": "mongo_exact",
                    }

        except Exception as e:
            logger.error("Oldindan tayyorlangan javobni qidirishda xatolik: %s", e)
        return None

    def get_all_precomputed_answers(self, limit: int = 50) -> list[dict]:
        """Oldindan tayyorlangan barcha yechimlar ro'yxatini qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, topic, question_pattern, answer_text, usage_count, created_at
                    FROM precomputed_answers
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "topic": r[1],
                        "question_pattern": r[2],
                        "answer_text": r[3],
                        "answer_code": r[3],
                        "usage_count": r[4],
                        "created_at": str(r[5]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Precomputed answers olishda xatolik: %s", e)
            return []

    def delete_precomputed_answer(self, item_id: int | str) -> bool:
        """Oldindan tayyorlangan yechimni bazadan o'chiradi (MongoDB + SQLite)."""
        ok = False
        try:
            if mongo_memory_service.is_connected():
                if mongo_memory_service.delete_precomputed_answer(item_id):
                    ok = True
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                if str(item_id).isdigit():
                    conn.execute("DELETE FROM precomputed_answers WHERE id = ?", (int(item_id),))
                else:
                    conn.execute("DELETE FROM precomputed_answers WHERE question_pattern = ? OR topic = ?", (str(item_id), str(item_id)))
                conn.commit()
                return True
        except Exception as e:
            logger.error("Precomputed answer o'chirishda xatolik: %s", e)
        return ok

    # -----------------------------------------------------------
    # Mentor Lexicon (Mentor tili, qisqartmalari va slengi)
    # -----------------------------------------------------------
    def add_mentor_lexicon(
        self,
        term: str = "",
        meaning: str = "",
        example: str = "",
        confidence: float = 1.0,
        category: str = "slang",
        **kwargs,
    ) -> bool:
        """Mentorning o'ziga xos so'zi yoki qisqartmasini xotiraga yozadi (Dual-Persistence)."""
        clean_term = (term or kwargs.get("phrase", "")).strip().lower()
        clean_meaning = (meaning or kwargs.get("definition", "")).strip()
        if not clean_term or not clean_meaning:
            return False

        # 1. MongoDB ga saqlash
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_mentor_lexicon(
                    clean_term, clean_meaning, example, confidence
                )
        except Exception:
            pass

        # 2. SQLite ga saqlash
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mentor_lexicon (term, meaning, example, confidence, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (clean_term, clean_meaning, example.strip(), confidence),
                )
                conn.commit()
                try:
                    from services.obsidian_brain_service import obsidian_brain_service
                    obsidian_brain_service.export_lexicon(self.get_all_mentor_lexicon(limit=100))
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error("Mentor lug'atini saqlashda xatolik: %s", e)
            return False

    def get_all_mentor_lexicon(self, limit: int = 100) -> list[dict]:
        """Mentorning barcha o'rganilgan so'zlari va qisqartmalari ro'yxati."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, term, meaning, example, confidence, updated_at FROM mentor_lexicon ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                if rows:
                    return [
                        {
                            "id": r[0],
                            "term": r[1],
                            "phrase": r[1],
                            "meaning": r[2],
                            "example": r[3] or "",
                            "confidence": r[4] or 1.0,
                            "updated_at": str(r[5]),
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.debug("Mentor lug'atini SQLite'dan olishda ogohlantirish: %s", e)

        # Fallback to Mongo
        try:
            if mongo_memory_service.is_connected():
                docs = mongo_memory_service.get_all_mentor_lexicon(limit=limit)
                if docs:
                    return [
                        {
                            "id": str(d.get("_id", "")),
                            "term": d.get("term", ""),
                            "phrase": d.get("term", ""),
                            "meaning": d.get("meaning", ""),
                            "example": d.get("example", ""),
                            "confidence": d.get("confidence", 1.0),
                            "updated_at": str(d.get("updated_at", "")),
                        }
                        for d in docs
                    ]
        except Exception:
            pass
        return []

    def delete_mentor_lexicon(self, term: str) -> bool:
        """Mentor lug'atidagi so'zni o'chiradi."""
        clean_term = term.strip().lower()
        if not clean_term:
            return False
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.delete_mentor_lexicon(clean_term)
        except Exception:
            pass
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM mentor_lexicon WHERE LOWER(term) = LOWER(?)", (clean_term,))
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    try:
                        from services.obsidian_brain_service import obsidian_brain_service
                        obsidian_brain_service.export_lexicon(self.get_all_mentor_lexicon(limit=100))
                    except Exception:
                        pass
                return deleted
        except Exception as e:
            logger.error("Mentor lug'atidan o'chirishda xatolik: %s", e)
            return False

    def get_lexicon_prompt_snippet(self, max_terms: int = 30, max_entries: int | None = None) -> str:
        """AI Service prompti uchun mentorning so'zlari lug'ati matni."""
        limit = max_entries if max_entries is not None else max_terms
        terms = self.get_all_mentor_lexicon(limit=limit)
        if not terms:
            return ""
        lines = [f"- '{t['term']}' => {t['meaning']}" for t in terms]
        return "🧠 MENTORNING SHAXSIY LUG'ATI VA QISQARTMALARI (DOIMO INOBATGA OLING):\n" + "\n".join(lines)

    # -----------------------------------------------------------
    # Self-Mistakes & Reflection (O'z xatolaridan saboqlar)
    # -----------------------------------------------------------
    def add_self_mistake(
        self,
        mistake: str = "",
        rule: str = "",
        situation: str = "Tizim tahlili",
        correction: str = "",
        context: str = "",
        **kwargs,
    ) -> bool:
        """AI o'z xatosini tahlil qilib, kelgusi uchun oltin qoida saqlaydi (Dual-Persistence)."""
        clean_rule = (rule or kwargs.get("correction_rule", "")).strip()
        clean_mistake = (mistake or kwargs.get("mistake_pattern", "")).strip()
        if not clean_rule:
            return False

        sit = situation or context or "Tizim tahlili"
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_self_mistake(
                    sit, mistake, correction, clean_rule
                )
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO self_mistakes (situation, mistake, correction, rule)
                    VALUES (?, ?, ?, ?)
                    """,
                    (sit.strip(), mistake.strip(), correction.strip(), clean_rule),
                )
                conn.commit()
                logger.info("🧠 AI o'z xatosidan saboq qayd qildi: %s", clean_rule[:60])
                try:
                    from services.obsidian_brain_service import obsidian_brain_service
                    obsidian_brain_service.export_mistake(
                        mistake_text=mistake.strip(),
                        lesson_learned=correction.strip(),
                        golden_rule=clean_rule,
                    )
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error("Self-mistake saqlashda xatolik: %s", e)
            return False

    def get_recent_self_mistakes(self, limit: int = 20) -> list[dict]:
        """AI o'z xatolaridan chiqargan so'nggi xulosalari."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, situation, mistake, correction, rule, created_at FROM self_mistakes ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                if rows:
                    return [
                        {
                            "id": r[0],
                            "situation": r[1],
                            "mistake": r[2],
                            "mistake_pattern": r[2],
                            "correction": r[3],
                            "rule": r[4],
                            "correction_rule": r[4],
                            "created_at": str(r[5]),
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.debug("Self-mistakes SQLite'dan olishda ogohlantirish: %s", e)

        # Fallback to Mongo
        try:
            if mongo_memory_service.is_connected():
                docs = mongo_memory_service.get_recent_self_mistakes(limit=limit)
                if docs:
                    return [
                        {
                            "id": str(d.get("_id", "")),
                            "situation": d.get("situation", ""),
                            "mistake": d.get("mistake", ""),
                            "mistake_pattern": d.get("mistake", ""),
                            "correction": d.get("correction", ""),
                            "rule": d.get("rule", ""),
                            "correction_rule": d.get("rule", ""),
                            "created_at": str(d.get("created_at", "")),
                        }
                        for d in docs
                    ]
        except Exception:
            pass
        return []

    def get_mistakes_prompt_snippet(self, max_rules: int = 5) -> str:
        """AI Service prompti uchun avvalgi xatolardan olingan oltin qoidalar."""
        mistakes = self.get_recent_self_mistakes(limit=max_rules)
        if not mistakes:
            return ""
        lines = [f"- {m['rule']}" for m in mistakes]
        return "⚠️ O'TMISHDAGI XATOLARDAN OLINGAN SABOQLAR (QAYTA TAKRORLAMANG):\n" + "\n".join(lines)

    def get_curriculum_insights_count_by_topic(self) -> dict[str, int]:
        """Har bir o'quv mavzusi bo'yicha bazada nechta saboq (insight) borligini hisoblaydi (Dynamic Budgeting uchun)."""
        counts = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT topic, COUNT(*) FROM learned_memory GROUP BY topic")
                for row in cursor.fetchall():
                    counts[row[0].strip().lower()] = row[1]
        except Exception:
            pass
        return counts

    # -----------------------------------------------------------
    # Eslatmalar (Reminders) Boshqaruvi
    # -----------------------------------------------------------
    def add_reminder(
        self, chat_id: int, reminder_text: str, remind_at: str, creator_id: int = 0
    ) -> int:
        """Yangi eslatmani bazaga saqlaydi (Dual-Persistence)."""
        clean_text = reminder_text.strip()
        sqlite_id = 0

        # 1. Avval SQLite ga yozish (lastrowid olish uchun)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reminders (chat_id, creator_id, reminder_text, remind_at, is_sent)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (chat_id, creator_id, clean_text, remind_at),
                )
                conn.commit()
                sqlite_id = cursor.lastrowid
        except Exception as e:
            logger.error("Eslatmani saqlashda xatolik: %s", e)

        # 2. MongoDB ga sqlite_id bilan yozish (mark_reminder_sent ishlashi uchun)
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.add_smart_reminder(
                    chat_id=chat_id,
                    creator_id=creator_id,
                    text=clean_text,
                    remind_at=remind_at,
                    sqlite_id=sqlite_id,
                )
        except Exception:
            pass

        return sqlite_id

    def get_active_reminders(self, limit: int = 20) -> list[dict]:
        """Kutilayotgan faol eslatmalar ro'yxatini qaytaradi (Lokal SQLite -> Mongo fallback)."""
        now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, chat_id, creator_id, reminder_text, remind_at, created_at
                    FROM reminders
                    WHERE is_sent = 0 AND remind_at >= ?
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (now_str, limit),
                )
                rows = cursor.fetchall()
                if rows:
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
            logger.debug("Faol eslatmalarni SQLite'dan olishda ogohlantirish: %s", e)

        # Fallback to Mongo if SQLite is empty
        try:
            if mongo_memory_service.is_connected():
                m_rems = mongo_memory_service.get_all_active_reminders(limit=limit)
                if m_rems:
                    return [
                        {
                            "id": str(r.get("sqlite_id") or r.get("_id", "")),
                            "chat_id": r.get("chat_id"),
                            "creator_id": r.get("creator_id", 0),
                            "text": r.get("text") or r.get("reminder_text", ""),
                            "remind_at": r.get("remind_at", ""),
                            "created_at": str(r.get("created_at", "")),
                        }
                        for r in m_rems
                    ]
        except Exception:
            pass
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

    def mark_reminder_sent(self, reminder_id: int | str) -> None:
        """Eslatmani yuborilgan (is_sent = 1) deb belgilaydi."""
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.mark_reminder_sent(reminder_id)
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                if str(reminder_id).isdigit():
                    conn.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (int(reminder_id),))
                    conn.commit()
        except Exception as e:
            logger.error("Eslatmani yuborilgan deb belgilashda xatolik: %s", e)

    def mark_reminder_sent_if_pending(self, reminder_id: int | str) -> bool:
        """Faqat yuborilmagan bo'lsa (is_sent = 0), is_sent = 1 qiladi va True qaytaradi."""
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.mark_reminder_sent(reminder_id)
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if str(reminder_id).isdigit():
                    cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = ? AND is_sent = 0", (int(reminder_id),))
                    conn.commit()
                    return cursor.rowcount > 0
                return True
        except Exception as e:
            logger.error("Eslatmani atomar belgilashda xatolik: %s", e)
            return False

    def delete_reminder(self, reminder_id: int | str) -> bool:
        """Eslatmani bekor qiladi/o'chiradi (MongoDB + SQLite)."""
        ok = False
        target_info = None
        try:
            if mongo_memory_service.is_connected():
                from bson import ObjectId
                t_str = str(reminder_id).strip()
                if ObjectId.is_valid(t_str):
                    target_info = mongo_memory_service._db["brain_mentor.smart_reminders"].find_one({"_id": ObjectId(t_str)})
                elif t_str.isdigit():
                    target_info = mongo_memory_service._db["brain_mentor.smart_reminders"].find_one({"sqlite_id": int(t_str)})
                if mongo_memory_service.delete_smart_reminder(reminder_id):
                    ok = True
        except Exception:
            pass

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if str(reminder_id).isdigit():
                    cursor.execute("DELETE FROM reminders WHERE id = ?", (int(reminder_id),))
                    conn.commit()
                    if cursor.rowcount > 0:
                        ok = True
                elif target_info:
                    sql_id = target_info.get("sqlite_id")
                    txt = target_info.get("text") or target_info.get("reminder_text", "")
                    rat = target_info.get("remind_at", "")
                    if sql_id:
                        cursor.execute("DELETE FROM reminders WHERE id = ?", (int(sql_id),))
                        conn.commit()
                        if cursor.rowcount > 0:
                            ok = True
                    elif txt and rat:
                        cursor.execute("DELETE FROM reminders WHERE reminder_text = ? AND remind_at = ?", (txt, rat))
                        conn.commit()
                        if cursor.rowcount > 0:
                            ok = True
        except Exception as e:
            logger.error("Eslatmani o'chirishda xatolik: %s", e)
        return ok

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
        """O'quvchini qo'shadi yoki yangilaydi (Dual-Persistence: MongoDB + SQLite)."""
        clean_user_id = user_id or 0
        try:
            if mongo_memory_service.is_connected() and clean_user_id:
                mongo_memory_service.upsert_student_profile(
                    user_id=clean_user_id,
                    full_name=full_name,
                    username=username,
                    group_name=group_name,
                    status=status,
                    strengths=strengths,
                    weaknesses=weaknesses,
                    mentor_notes=mentor_notes,
                )
        except Exception as me:
            logger.debug("MongoDB ga o'quvchi yozishda ogohlantirish: %s", me)

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
                    res_id = cursor.lastrowid or 0
                else:
                    cursor.execute(
                        """
                        INSERT INTO students (full_name, username, group_name, status, strengths, weaknesses, mentor_notes, last_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (full_name, username, group_name, status, strengths, weaknesses, mentor_notes),
                    )
                    conn.commit()
                    res_id = cursor.lastrowid or 0

                try:
                    from services.obsidian_brain_service import obsidian_brain_service
                    obsidian_brain_service.export_student({
                        "full_name": full_name,
                        "user_id": user_id,
                        "username": username,
                        "group_name": group_name,
                        "status": status,
                        "strengths": strengths,
                        "weaknesses": weaknesses,
                        "mentor_notes": mentor_notes,
                        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                except Exception:
                    pass

                return res_id
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
        """O'quvchini bazadan o'chiradi (MongoDB + SQLite + Obsidian)."""
        ok = False
        user_id = student_id
        st_name = ""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, full_name FROM students WHERE id = ? OR user_id = ?", (student_id, student_id))
                row = cursor.fetchone()
                if row:
                    user_id = row[0]
                    st_name = row[1] or ""
                cursor.execute("DELETE FROM students WHERE id = ? OR user_id = ?", (student_id, student_id))
                conn.commit()
                if cursor.rowcount > 0:
                    ok = True
        except Exception as e:
            logger.error("O'quvchini SQLite dan o'chirishda xatolik: %s", e)

        try:
            if mongo_memory_service.is_connected() and user_id:
                if mongo_memory_service.delete_student_profile(user_id):
                    ok = True
        except Exception as me:
            logger.debug("MongoDB dan o'quvchi o'chirishda ogohlantirish: %s", me)

        if st_name:
            try:
                from services.obsidian_brain_service import obsidian_brain_service
                obsidian_brain_service.delete_student_note(st_name)
            except Exception:
                pass

        return ok

    # -----------------------------------------------------------
    # Aqlli Lokatsiya Xotirasi (Saved Locations)
    # -----------------------------------------------------------
    def add_saved_location(self, name: str, lat: float, long: float, address: str = "") -> int:
        """Yangi joylashuvni nom bilan saqlaydi (MongoDB + SQLite)."""
        clean = name.lower().strip()
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_location(name=name.strip(), lat=lat, long=long, details=address.strip())
        except Exception as me:
            logger.debug("MongoDB ga lokatsiya yozishda ogohlantirish: %s", me)

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
                lid = cursor.lastrowid
                conn.commit()

                # Obsidian Knowledge Vault bilan sinxronlash
                try:
                    from services.obsidian_brain_service import obsidian_brain_service
                    obsidian_brain_service.export_rule(
                        topic=f"lokatsiya_{clean}",
                        content=f"📍 **{name.strip()} lokatsiyasi**:\n• Kenglik (Lat): `{lat}`\n• Uzunlik (Long): `{long}`\n• 🗺 [Google Maps Havolasi](https://www.google.com/maps?q={lat},{long})" + (f"\n• Manzil: {address.strip()}" if address.strip() else ""),
                        source="mentor"
                    )
                except Exception as oe:
                    logger.debug("Obsidian lokatsiya eksportida ogohlantirish: %s", oe)

                return lid
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
        """Kunlik rejaga yangi vazifa qo'shadi (Dual-Persistence)."""
        # 1. MongoDB Atlas
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.add_daily_plan(date_str=plan_date.strip(), title=title.strip(), plan_time=plan_time.strip())
        except Exception as me:
            logger.debug("MongoDB ga reja yozishda ogohlantirish: %s", me)

        # 2. SQLite kesh
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
        """Muayyan sanadagi barcha rejalarni qaytaradi (MongoDB -> SQLite)."""
        try:
            if mongo_memory_service.is_connected():
                docs = mongo_memory_service.get_daily_plans(date_str=plan_date)
                if docs:
                    return [
                        {
                            "id": str(d.get("_id", "")),
                            "title": d.get("title", ""),
                            "plan_text": d.get("title", ""),
                            "plan_date": d.get("date", plan_date),
                            "plan_time": d.get("plan_time", ""),
                            "is_completed": bool(d.get("is_completed", False)),
                            "status": "completed" if d.get("is_completed", False) else "pending",
                            "priority": "normal",
                            "created_at": str(d.get("created_at", "")),
                        }
                        for d in docs
                    ]
        except Exception as me:
            logger.debug("MongoDB dan rejalarni olishda ogohlantirish: %s", me)

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

    def mark_plan_completed(self, plan_id: int | str, is_completed: bool = True) -> bool:
        """Rejadagi vazifani bajarilgan yoki kutilayotgan deb belgilaydi (Dual-Persistence)."""
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.set_plan_completed(str(plan_id), is_completed=is_completed)
        except Exception as me:
            logger.debug("MongoDB rejasini yangilashda ogohlantirish: %s", me)

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

                # IQ Indeksi va Tahlilini hisoblash (Base: 115 IQ + tajriba/o'rganishlar orqali cheksiz oshib boradi)
                iq_bonus = int((level * 2.5) + (total_learned * 2.0) + (total_students * 1.5) + (total_locations * 2.0) + (completed_plans * 1.5))
                iq_score = 115 + iq_bonus

                if iq_score < 125:
                    iq_status = "Aqlli Yordamchi (Smart AI)"
                elif iq_score < 140:
                    iq_status = "Yuqori Intellekt (High IQ)"
                elif iq_score < 155:
                    iq_status = "Katta Strategik Hamkor (Superior IQ)"
                elif iq_score < 175:
                    iq_status = "Daho Avtonom AI (Genius Level)"
                elif iq_score < 200:
                    iq_status = "Super-Kognitiv Intellekt (Polymath AI)"
                else:
                    iq_status = "Mutlaq Kiber-Intellekt (Superhuman AGI)"

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

                emergency_id = self.get_setting("emergency_contact_id", "")
                emergency_wakeup_enabled = self.get_setting("emergency_wakeup_enabled", "true").lower() == "true"

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
                    "emergency_wakeup_enabled": emergency_wakeup_enabled,
                }
        except Exception as e:
            logger.error("Agent statistikasini hisoblashda xatolik: %s", e)
            return {
                "level": 1,
                "title": "Boshlang'ich AI Yordamchi",
                "total_xp": 0,
                "progress_pct": 0,
                "emergency_contact_id": "",
                "emergency_wakeup_enabled": True,
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

                    # 6. learned_memory (Agent o'rgangan barcha saboqlar va bilimlar bazasi)
                    if "learned_memory" in tables:
                        s_cursor.execute("SELECT category, topic, content, source, created_at, updated_at FROM learned_memory")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO learned_memory (category, topic, content, source, created_at, updated_at)
                            SELECT ?, ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM learned_memory WHERE LOWER(topic) = LOWER(?) AND LOWER(content) = LOWER(?)
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[4], r[5], r[1], r[2]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta bilim/saboq")

                    # 7. precomputed_answers (Keshdagi tayyor yechimlar)
                    if "precomputed_answers" in tables:
                        s_cursor.execute("SELECT topic, question_pattern, answer_text, usage_count, created_at FROM precomputed_answers")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO precomputed_answers (topic, question_pattern, answer_text, usage_count, created_at)
                            SELECT ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM precomputed_answers WHERE LOWER(question_pattern) = LOWER(?)
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[4], r[1]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta kesh yechim")

                    # 8. saved_locations (Shaxsiy lokatsiyalar)
                    if "saved_locations" in tables:
                        s_cursor.execute("SELECT name, name_clean, lat, long, address, created_at FROM saved_locations")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO saved_locations (name, name_clean, lat, long, address, created_at)
                            SELECT ?, ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM saved_locations WHERE LOWER(name) = LOWER(?)
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[4], r[5], r[0]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta lokatsiya")

                    # 9. daily_plans (Kunlik rejalar)
                    if "daily_plans" in tables:
                        s_cursor.execute("SELECT title, plan_date, plan_time, is_completed, priority, created_at FROM daily_plans")
                        rows = s_cursor.fetchall()
                        target_conn.executemany(
                            """
                            INSERT INTO daily_plans (title, plan_date, plan_time, is_completed, priority, created_at)
                            SELECT ?, ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM daily_plans WHERE plan_date = ? AND title = ?
                            )
                            """,
                            [(r[0], r[1], r[2], r[3], r[4], r[5], r[1], r[0]) for r in rows],
                        )
                        imported_stats.append(f"{len(rows)} ta reja")

                    target_conn.commit()

            msg = "Muvaffaqiyatli birlashtirildi: " + ", ".join(imported_stats)
            logger.info("Baza birlashtirildi (%s): %s", source.name, msg)
            return True, msg
        except Exception as e:
            logger.error("Baza birlashtirishda xatolik: %s", e)
            return False, str(e)

    # -----------------------------------------------------------
    # Active Inquiries (Borib so'rab, aniqlashtirib kelish)
    # -----------------------------------------------------------
    def create_active_inquiry(
        self,
        target_user_id: int,
        target_name: str,
        target_username: str,
        question_text: str,
        expected_info: str,
        mentor_chat_id: str = "",
    ) -> int:
        """Yangi kutilayotgan so'rov (inquiry) vazifasini yaratadi."""
        inq_id = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Avvalgi eski pending holatlarni yangisiga almashtirish
                cursor.execute(
                    "UPDATE active_inquiries SET status = 'superseded' WHERE target_user_id = ? AND status = 'pending'",
                    (target_user_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO active_inquiries (
                        target_user_id, target_username, target_name, question_text, expected_info, mentor_chat_id, status, attempts
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0)
                    """,
                    (target_user_id, target_username or "", target_name or "", question_text, expected_info, str(mentor_chat_id or "")),
                )
                conn.commit()
                inq_id = cursor.lastrowid or 0
        except Exception as e:
            logger.error("Active inquiry yaratishda xatolik: %s", e)

        # MongoDB bilan sinxronlash
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_active_inquiry({
                    "inquiry_id": inq_id,
                    "target_user_id": target_user_id,
                    "target_username": target_username,
                    "target_name": target_name,
                    "question_text": question_text,
                    "expected_info": expected_info,
                    "mentor_chat_id": str(mentor_chat_id or ""),
                    "status": "pending",
                    "attempts": 0,
                })
        except Exception as me:
            logger.debug("MongoDB active_inquiry sinxronlashda ogohlantirish: %s", me)

        return inq_id

    def get_pending_inquiry_for_user(self, target_user_id: int) -> dict | None:
        """Foydalanuvchiga tegishli faol kutilayotgan so'rovni qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, target_user_id, target_username, target_name, question_text, expected_info, mentor_chat_id, status, attempts, created_at
                    FROM active_inquiries
                    WHERE target_user_id = ? AND status = 'pending'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (target_user_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "target_user_id": row[1],
                        "target_username": row[2],
                        "target_name": row[3],
                        "question_text": row[4],
                        "expected_info": row[5],
                        "mentor_chat_id": row[6],
                        "status": row[7],
                        "attempts": row[8],
                        "created_at": row[9],
                    }
        except Exception as e:
            logger.error("Pending inquiry olishda xatolik: %s", e)
        return None

    def mark_inquiry_status(self, inquiry_id: int, status: str, result_summary: str = "") -> bool:
        """So'rov holatini (answered, expired, cancelled) yangilaydi."""
        ok = False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE active_inquiries
                    SET status = ?, result_summary = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, result_summary, inquiry_id),
                )
                conn.commit()
                ok = cursor.rowcount > 0
        except Exception as e:
            logger.error("Inquiry statusini yangilashda xatolik: %s", e)

        # MongoDB yangilash
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.update_active_inquiry_status(inquiry_id, status, result_summary)
        except Exception as me:
            logger.debug("MongoDB inquiry status yangilashda ogohlantirish: %s", me)

        return ok

    def increment_inquiry_attempts(self, inquiry_id: int) -> int:
        """So'rov uchun urinishlar sonini oshiradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE active_inquiries SET attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (inquiry_id,),
                )
                cursor.execute("SELECT attempts FROM active_inquiries WHERE id = ?", (inquiry_id,))
                row = cursor.fetchone()
                conn.commit()
                return row[0] if row else 1
        except Exception as e:
            logger.error("Inquiry attempts oshirishda xatolik: %s", e)
            return 1

    # -----------------------------------------------------------
    # 3-Mexanizm: O'quvchining Dinamik Xatolar Xaritasi (Weaknesses)
    # -----------------------------------------------------------
    def record_student_topic_struggle(self, student_id: int, topic: str, question: str = "") -> None:
        """O'quvchi ma'lum dasturlash mavzusida qiynalganini qayd etadi (error_count ni oshiradi)."""
        if not student_id or not topic:
            return
        t_clean = topic.strip().lower()
        q_clean = (question or "").strip()[:300]
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO student_weaknesses (student_id, topic, error_count, last_question, last_seen)
                    VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(student_id, topic) DO UPDATE SET
                        error_count = error_count + 1,
                        last_question = excluded.last_question,
                        last_seen = CURRENT_TIMESTAMP
                    """,
                    (student_id, t_clean, q_clean),
                )
                conn.commit()
        except Exception as e:
            logger.error("Student weakness yozishda xatolik: %s", e)

        # MongoDB bilan sinxronlash
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_student_weakness(student_id, t_clean, q_clean)
        except Exception as me:
            logger.debug("MongoDB student_weakness sinxronlashda ogohlantirish: %s", me)

    def get_student_weaknesses(self, student_id: int) -> list[dict]:
        """O'quvchining eng ko'p qiynalgan zaif mavzulari ro'yxatini qaytaradi."""
        if not student_id:
            return []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT topic, error_count, last_question, last_seen
                    FROM student_weaknesses
                    WHERE student_id = ?
                    ORDER BY error_count DESC, last_seen DESC
                    LIMIT 5
                    """,
                    (student_id,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "topic": r[0],
                        "error_count": r[1],
                        "last_question": r[2],
                        "last_seen": str(r[3]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Student weaknesses olishda xatolik: %s", e)
            return []

    def get_top_struggling_topics(self, limit: int = 5) -> list[dict]:
        """Barcha o'quvchilar bo'yicha eng ko'p xato qilinayotgan global mavzularni qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT topic, SUM(error_count) as total_errors, COUNT(DISTINCT student_id) as student_count
                    FROM student_weaknesses
                    GROUP BY topic
                    ORDER BY total_errors DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "topic": r[0],
                        "total_errors": r[1],
                        "student_count": r[2],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("Top struggling topics olishda xatolik: %s", e)
            return []

    # -----------------------------------------------------------
    # Miya 5: Silent Profiler & User Dossiers
    # -----------------------------------------------------------
    def is_user_dossier_exists(self, user_id: int) -> bool:
        """Foydalanuvchi oldin tahlil qilingan yoki yo'qligini tekshiradi (0.001s)."""
        if not user_id:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM user_dossiers WHERE user_id = ? LIMIT 1", (user_id,))
                if cursor.fetchone() is not None:
                    return True
        except Exception as e:
            logger.error("is_user_dossier_exists xatolik: %s", e)

        # Fallback to MongoDB (Render restartdan keyin ham bilish uchun)
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                return mongo_memory_service.is_user_dossier_exists(user_id)
        except Exception:
            pass

        return False

    def save_user_dossier(
        self,
        user_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        bio: str = "",
        channel_username: str = "",
        channel_summary: str = "",
        photo_count: int = 0,
        has_stories: bool = False,
        dossier_text: str = "",
    ) -> bool:
        """Foydalanuvchining to'liq dosyesini saqlaydi (Dual: SQLite + MongoDB)."""
        if not user_id or not dossier_text:
            return False
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO user_dossiers (
                        user_id, username, first_name, last_name, phone, bio,
                        channel_username, channel_summary, photo_count, has_stories,
                        dossier_text, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_name = excluded.last_name,
                        phone = excluded.phone,
                        bio = excluded.bio,
                        channel_username = excluded.channel_username,
                        channel_summary = excluded.channel_summary,
                        photo_count = excluded.photo_count,
                        has_stories = excluded.has_stories,
                        dossier_text = excluded.dossier_text,
                        analyzed_at = CURRENT_TIMESTAMP
                    """,
                    (
                        user_id, username or "", first_name or "", last_name or "", phone or "",
                        bio or "", channel_username or "", channel_summary or "", photo_count,
                        1 if has_stories else 0, dossier_text
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error("save_user_dossier SQLite xatolik: %s", e)

        # MongoDB ga sinxronlash
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_user_dossier(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    bio=bio,
                    channel_username=channel_username,
                    channel_summary=channel_summary,
                    photo_count=photo_count,
                    has_stories=has_stories,
                    dossier_text=dossier_text,
                )
        except Exception as me:
            logger.debug("MongoDB user_dossier sinxronlashda ogohlantirish: %s", me)

        # Obsidian Knowledge Vault bilan sinxronlash
        try:
            from services.obsidian_brain_service import obsidian_brain_service
            obsidian_brain_service.export_dossier(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                bio=bio,
                dossier_text=dossier_text,
            )
        except Exception as oe:
            logger.debug("Obsidian user_dossier sinxronlashda ogohlantirish: %s", oe)

        return True

    def get_user_dossier(self, user_id: int) -> dict | None:
        """Foydalanuvchi dosyesini oladi."""
        if not user_id:
            return None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, first_name, last_name, phone, bio,
                           channel_username, channel_summary, photo_count, has_stories,
                           dossier_text, analyzed_at
                    FROM user_dossiers
                    WHERE user_id = ?
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1],
                        "first_name": row[2],
                        "last_name": row[3],
                        "phone": row[4],
                        "bio": row[5],
                        "channel_username": row[6],
                        "channel_summary": row[7],
                        "photo_count": row[8],
                        "has_stories": bool(row[9]),
                        "dossier_text": row[10],
                        "analyzed_at": str(row[11]),
                    }
        except Exception as e:
            logger.error("get_user_dossier xatolik: %s", e)
        return None

    def get_all_user_dossiers(self, query: str = "", limit: int = 100) -> list[dict]:
        """Tahlil qilingan so'nggi dosyelarni qaytaradi (qidiruv filtri bilan)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if query and query.strip():
                    q_clean = f"%{query.strip()}%"
                    cursor.execute(
                        """
                        SELECT user_id, username, first_name, last_name, phone, bio,
                               channel_username, channel_summary, photo_count, has_stories,
                               dossier_text, analyzed_at
                        FROM user_dossiers
                        WHERE first_name LIKE ? OR last_name LIKE ? OR username LIKE ? OR phone LIKE ? OR bio LIKE ? OR dossier_text LIKE ?
                        ORDER BY analyzed_at DESC
                        LIMIT ?
                        """,
                        (q_clean, q_clean, q_clean, q_clean, q_clean, q_clean, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT user_id, username, first_name, last_name, phone, bio,
                               channel_username, channel_summary, photo_count, has_stories,
                               dossier_text, analyzed_at
                        FROM user_dossiers
                        ORDER BY analyzed_at DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                rows = cursor.fetchall()
                if rows:
                    return [
                        {
                            "user_id": r[0],
                            "username": r[1],
                            "first_name": r[2],
                            "last_name": r[3],
                            "phone": r[4],
                            "bio": r[5],
                            "channel_username": r[6],
                            "channel_summary": r[7],
                            "photo_count": r[8],
                            "has_stories": bool(r[9]),
                            "dossier_text": r[10],
                            "analyzed_at": str(r[11]),
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error("get_all_user_dossiers xatolik: %s", e)

        # Fallback to MongoDB
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                return mongo_memory_service.get_all_user_dossiers(query=query, limit=limit)
        except Exception:
            pass

        return []

    def get_dossier_count(self) -> int:
        """Jami tahlil qilingan foydalanuvchilar sonini qaytaradi."""
        count = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM user_dossiers")
                row = cursor.fetchone()
                count = row[0] if row else 0
        except Exception:
            pass

        if count > 0:
            return count

        # Fallback to MongoDB
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                return mongo_memory_service.get_dossier_count()
        except Exception:
            pass

        return count

    # -----------------------------------------------------------
    # Pedagogical Outcome Tracker (Implicit RLHF)
    # -----------------------------------------------------------
    def record_pedagogical_outcome(
        self,
        student_id: int,
        topic: str,
        question: str,
        answer_snippet: str,
        outcome: str,
        student_reaction: str = "",
    ) -> None:
        """O'quvchi javobiga bildirilgan reaksiyani (success / confusion) qayd etadi."""
        if not student_id or not outcome:
            return
        t_clean = (topic or "general").strip().lower()
        q_clean = (question or "").strip()[:300]
        a_clean = (answer_snippet or "").strip()[:400]
        r_clean = (student_reaction or "").strip()[:200]
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO pedagogical_outcomes (student_id, topic, question, answer_snippet, outcome, student_reaction)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (student_id, t_clean, q_clean, a_clean, outcome, r_clean),
                )
                conn.commit()
        except Exception as e:
            logger.error("record_pedagogical_outcome xatolik: %s", e)

        # MongoDB sinxronlash
        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_pedagogical_outcome(student_id, t_clean, q_clean, a_clean, outcome, r_clean)
        except Exception as me:
            logger.debug("MongoDB save_pedagogical_outcome sinxronlashda ogohlantirish: %s", me)

    def save_high_yield_pedagogy(self, topic: str, winning_analogy: str) -> None:
        """O'quvchilar tomonidan eng yaxshi tushunilgan analogiya yoki tushuntirish uslubini saqlaydi."""
        if not topic or not winning_analogy:
            return
        t_clean = topic.strip().lower()
        a_clean = winning_analogy.strip()[:600]
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO high_yield_pedagogy (topic, winning_analogy, success_count, last_updated)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(topic) DO UPDATE SET
                        winning_analogy = excluded.winning_analogy,
                        success_count = success_count + 1,
                        last_updated = CURRENT_TIMESTAMP
                    """,
                    (t_clean, a_clean),
                )
                conn.commit()
        except Exception as e:
            logger.error("save_high_yield_pedagogy xatolik: %s", e)

        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_high_yield_pedagogy(t_clean, a_clean)
        except Exception as me:
            logger.debug("MongoDB save_high_yield_pedagogy sinxronlashda ogohlantirish: %s", me)

    def get_top_pedagogy_for_topic(self, topic: str) -> str | None:
        """Mavzu bo'yicha eng yuqori muvaffaqiyatli tushuntirish analogiyasini qaytaradi."""
        if not topic:
            return None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT winning_analogy FROM high_yield_pedagogy WHERE topic = ? ORDER BY success_count DESC LIMIT 1",
                    (topic.strip().lower(),),
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logger.error("get_top_pedagogy_for_topic xatolik: %s", e)
        return None

    # -----------------------------------------------------------
    # Miya 5: Telegram Bot Ecosystem Observer
    # -----------------------------------------------------------
    def record_bot_pattern(self, bot_username: str, pattern_type: str, observation_summary: str) -> None:
        """Boshqa Telegram botlaridan o'rganilgan UI/UX patternni saqlaydi."""
        if not bot_username or not observation_summary:
            return
        b_clean = bot_username.strip().lstrip("@")
        p_clean = pattern_type.strip()[:100]
        s_clean = observation_summary.strip()[:600]
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO bot_interaction_patterns (bot_username, pattern_type, observation_summary)
                    VALUES (?, ?, ?)
                    """,
                    (b_clean, p_clean, s_clean),
                )
                conn.commit()
        except Exception as e:
            logger.error("record_bot_pattern xatolik: %s", e)

        try:
            from services.mongo_memory_service import mongo_memory_service
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_bot_pattern(b_clean, p_clean, s_clean)
        except Exception as me:
            logger.debug("MongoDB save_bot_pattern sinxronlashda ogohlantirish: %s", me)

    def get_recent_bot_patterns(self, limit: int = 10) -> list[dict]:
        """O'rganilgan eng so'nggi bot patternlarini qaytaradi."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT bot_username, pattern_type, observation_summary, created_at FROM bot_interaction_patterns ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "bot_username": r[0],
                        "pattern_type": r[1],
                        "observation_summary": r[2],
                        "created_at": str(r[3]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("get_recent_bot_patterns xatolik: %s", e)
            return []

    def get_memory_storage_info(self) -> dict:
        """Xotira hajmi: MongoDB Atlas va SQLite ma'lumotlar bazalarining aniq hajmi va qolgan bo'sh joyini beradi."""
        from services.mongo_memory_service import mongo_memory_service

        sqlite_size_mb = 0.0
        try:
            if hasattr(self, "db_path") and self.db_path.exists():
                sqlite_size_mb = round(self.db_path.stat().st_size / (1024 * 1024), 2)
        except Exception:
            pass

        mongo_info = mongo_memory_service.get_storage_stats()
        agent_stats = self.get_agent_stats()

        return {
            "sqlite_file_mb": sqlite_size_mb,
            "mongo": mongo_info,
            "total_messages": agent_stats.get("total_messages", 0),
            "total_students": agent_stats.get("total_students", 0),
            "total_learned_facts": agent_stats.get("total_learned_facts", 0),
            "total_locations": agent_stats.get("total_locations", 0),
            "level": agent_stats.get("level", 1),
            "iq_score": agent_stats.get("iq_score", 140),
            "title": agent_stats.get("title", "Kichik AI Yordamchi"),
            "cognitive_metrics": agent_stats.get("cognitive_metrics", {}),
            "total_xp": agent_stats.get("total_xp", 0),
            "progress_pct": agent_stats.get("progress_pct", 0),
        }

    # =========================================================================
    # Multi-User Obuna va Shaxsiy Guruh Boshqaruvi
    # =========================================================================
    def is_super_admin(self, user_id: int | None) -> bool:
        """Faqat tizim egasi (@mentor_cc / ID: 8105823872) ekanligini tekshiradi."""
        if not user_id:
            return False
        return user_id == config.mentor_user_id or user_id == 8105823872

    def get_subscription(self, user_id: int) -> dict | None:
        """Foydalanuvchi obunasini oladi (Super Admin bo'lsa doim cheksiz aktiv)."""
        if self.is_super_admin(user_id):
            return {
                "user_id": user_id,
                "username": "mentor_cc",
                "full_name": "Super Admin",
                "business_name": "Coddy IT Academy",
                "profession": "Bosh Mentor & Tizim Egasi",
                "system_prompt": "",
                "group_id": config.escalation_chat,
                "active": 1,
                "expires_at": "2099-12-31 23:59:59",
                "role": "super_admin",
                "is_expired": False,
            }
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, full_name, phone, business_name,
                           profession, system_prompt, group_id, active, expires_at, role, created_at,
                           session_string, session_active
                    FROM user_subscriptions WHERE user_id = ?
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                if not row:
                    if mongo_memory_service.is_connected():
                        m_sub = mongo_memory_service.get_user_subscription(user_id)
                        if m_sub:
                            return m_sub
                    return None

                exp_str = str(row[9]) if row[9] else ""
                is_expired = False
                if exp_str:
                    try:
                        exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                        now = datetime.now(ZoneInfo("Asia/Tashkent"))
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=ZoneInfo("Asia/Tashkent"))
                        is_expired = exp_dt < now
                    except Exception:
                        pass

                return {
                    "user_id": row[0],
                    "username": row[1] or "",
                    "full_name": row[2] or "",
                    "phone": row[3] or "",
                    "business_name": row[4] or "Mening Boshqaruvim",
                    "profession": row[5] or "Tadbirkor / Ekspert",
                    "system_prompt": row[6] or "",
                    "group_id": row[7] or 0,
                    "active": int(row[8] or 0),
                    "expires_at": exp_str,
                    "role": row[10] or "client",
                    "created_at": str(row[11]) if row[11] else "",
                    "is_expired": is_expired,
                    "session_string": row[12] or "",
                    "session_active": int(row[13] or 0),
                }
        except Exception as e:
            logger.error("Obunani o'qishda xatolik [%s]: %s", user_id, e)
            if mongo_memory_service.is_connected():
                return mongo_memory_service.get_user_subscription(user_id)
            return None

    def is_subscription_active(self, user_id: int) -> bool:
        """Foydalanuvchida faol (muddati o'tmagan) obuna borligini tekshiradi."""
        if self.is_super_admin(user_id):
            return True
        sub = self.get_subscription(user_id)
        if not sub:
            return False
        return bool(sub.get("active") and not sub.get("is_expired"))

    def upsert_subscription(
        self,
        user_id: int,
        username: str = "",
        full_name: str = "",
        days: int = 30,
        business_name: str = "",
        profession: str = "",
        system_prompt: str = "",
        role: str = "client",
        is_edit: bool = False,
    ) -> dict:
        """Yangi obuna ochadi yoki mavjud mijoz ma'lumotlarini yangilaydi."""
        from datetime import timedelta
        tashkent_tz = ZoneInfo("Asia/Tashkent")
        now = datetime.now(tashkent_tz)
        start_dt = now
        existing = self.get_subscription(user_id)

        if is_edit and existing and existing.get("expires_at"):
            # Tahrirlash rejimida: agar kun qo'shilmasa (days <= 0), mavjud muddatni saqlaymiz
            if days <= 0:
                expires_at = existing["expires_at"]
            else:
                try:
                    cur_exp = datetime.fromisoformat(existing["expires_at"].replace("Z", "+00:00"))
                    if cur_exp.tzinfo is None:
                        cur_exp = cur_exp.replace(tzinfo=tashkent_tz)
                    start_dt = max(now, cur_exp)
                except Exception:
                    start_dt = now
                expires_at = (start_dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            # Yangi obuna ochish yoki muddat uzaytirish
            if existing and existing.get("expires_at") and not existing.get("is_expired"):
                try:
                    cur_exp = datetime.fromisoformat(existing["expires_at"].replace("Z", "+00:00"))
                    if cur_exp.tzinfo is None:
                        cur_exp = cur_exp.replace(tzinfo=tashkent_tz)
                    if cur_exp > now:
                        start_dt = cur_exp
                except Exception:
                    pass
            days_to_add = max(1, days)
            expires_at = (start_dt + timedelta(days=days_to_add)).strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO user_subscriptions (
                        user_id, username, full_name, business_name, profession,
                        system_prompt, active, expires_at, role, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = CASE WHEN excluded.username != '' THEN excluded.username ELSE user_subscriptions.username END,
                        full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE user_subscriptions.full_name END,
                        business_name = CASE WHEN excluded.business_name != '' THEN excluded.business_name ELSE user_subscriptions.business_name END,
                        profession = excluded.profession,
                        system_prompt = excluded.system_prompt,
                        active = 1,
                        expires_at = excluded.expires_at,
                        role = excluded.role,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        user_id,
                        (username or "").lstrip("@"),
                        full_name or "",
                        business_name or "Mening Boshqaruvim",
                        profession or "",
                        system_prompt or "",
                        expires_at,
                        role,
                    )
                )
                conn.commit()

            sub_data = self.get_subscription(user_id) or {}
            if mongo_memory_service.is_connected() and sub_data:
                mongo_memory_service.upsert_user_subscription(sub_data)
            return sub_data
        except Exception as e:
            logger.error("Obuna yaratishda xatolik [%s]: %s", user_id, e)
            return {}

    def link_user_group(self, user_id: int, group_id: int) -> bool:
        """Foydalanuvchiga uning shaxsiy Vazifalar guruhini biriktiradi."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE user_subscriptions
                    SET group_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (group_id, user_id)
                )
                conn.commit()
            if mongo_memory_service.is_connected():
                mongo_memory_service.link_user_group(user_id, group_id)
            logger.info("Foydalanuvchiga shaxsiy guruh biriktirildi: user_id=%s, group_id=%s", user_id, group_id)
            return True
        except Exception as e:
            logger.error("Guruhni biriktirishda xatolik: %s", e)
            return False

    def save_session_string(self, user_id: int, session_string: str) -> bool:
        """Mijozning Telethon string session kodini saqlaydi."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE user_subscriptions SET session_string = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (session_string or "", user_id)
                )
                conn.commit()
            # MongoDB ga ham sync
            if mongo_memory_service.is_connected():
                try:
                    mongo_memory_service._db["system_core.user_subscriptions"].update_one(
                        {"user_id": user_id},
                        {"$set": {"session_string": session_string or "", "updated_at": __import__("datetime").datetime.now()}},
                        upsert=True,
                    )
                except Exception:
                    pass
            logger.info("Mijoz sessiya kodi saqlandi: user_id=%s", user_id)
            return True
        except Exception as e:
            logger.error("Sessiya kodini saqlashda xatolik [%s]: %s", user_id, e)
            return False

    def set_session_active(self, user_id: int, active: bool) -> bool:
        """Mijozning session holatini yangilaydi (ishlamoqda / to'xtagan)."""
        try:
            val = 1 if active else 0
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE user_subscriptions SET session_active = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (val, user_id)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error("Session holatini o'zgartirishda xatolik [%s]: %s", user_id, e)
            return False

    def get_subscription_by_group(self, group_id: int) -> dict | None:
        """Guruh ID bo'yicha uning egasi (obunachi)ni topadi."""
        if str(group_id) in (str(config.escalation_chat), "-1005388159517", "-5388159517"):
            return self.get_subscription(config.mentor_user_id or 8105823872)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM user_subscriptions WHERE group_id = ? AND active = 1", (group_id,))
                row = cursor.fetchone()
                if row:
                    return self.get_subscription(row[0])
        except Exception as e:
            logger.error("Guruh bo'yicha obunachini qidirishda xatolik: %s", e)
        return None

    def revoke_subscription(self, user_id: int) -> bool:
        """Foydalanuvchi obunasini bekor qiladi / to'xtatadi."""
        try:
            with self._get_connection() as conn:
                conn.execute("UPDATE user_subscriptions SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
                conn.commit()
            if mongo_memory_service.is_connected():
                mongo_memory_service.revoke_user_subscription(user_id)
            return True
        except Exception as e:
            logger.error("Obunani bekor qilishda xatolik: %s", e)
            return False

    def delete_subscription(self, user_id: int) -> bool:
        """Foydalanuvchi obunasini butunlay o'chiradi."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM user_subscriptions WHERE user_id = ?", (user_id,))
                conn.commit()
            if mongo_memory_service.is_connected():
                mongo_memory_service.delete_user_subscription(user_id)
            return True
        except Exception as e:
            logger.error("Obunani o'chirishda xatolik: %s", e)
            return False

    def get_all_subscriptions(self) -> list[dict]:
        """Super Admin paneli uchun barcha obunachilarni qaytaradi."""
        subs = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, full_name, business_name, profession,
                           system_prompt, group_id, active, expires_at, role, created_at,
                           session_string, session_active
                    FROM user_subscriptions ORDER BY created_at DESC
                    """
                )
                for r in cursor.fetchall():
                    subs.append({
                        "user_id": r[0],
                        "username": r[1] or "",
                        "full_name": r[2] or "",
                        "business_name": r[3] or "",
                        "profession": r[4] or "",
                        "system_prompt": r[5] or "",
                        "group_id": r[6] or 0,
                        "active": int(r[7] or 0),
                        "expires_at": str(r[8]) if r[8] else "",
                        "role": r[9] or "client",
                        "created_at": str(r[10]) if r[10] else "",
                        "session_string": r[11] or "",
                        "session_active": int(r[12] or 0),
                    })
        except Exception as e:
            logger.error("Barcha obunachilarni olishda xatolik: %s", e)

        # Agar SQLite bo'sh bo'lsa (masalan, Render restart keyin), MongoDB'dan o'qi
        if not subs and mongo_memory_service.is_connected():
            try:
                logger.info("📋 SQLite bo'sh — MongoDB'dan user_subscriptions o'qilmoqda...")
                for doc in mongo_memory_service._db["system_core.user_subscriptions"].find():
                    uid = doc.get("user_id")
                    if uid:
                        subs.append({
                            "user_id": uid,
                            "username": doc.get("username", ""),
                            "full_name": doc.get("full_name", ""),
                            "business_name": doc.get("business_name", ""),
                            "profession": doc.get("profession", ""),
                            "system_prompt": doc.get("system_prompt", ""),
                            "group_id": doc.get("group_id") or 0,
                            "active": int(doc.get("active", 1)),
                            "expires_at": str(doc.get("expires_at") or ""),
                            "role": doc.get("role", "client"),
                            "created_at": str(doc.get("created_at") or ""),
                        })
                logger.info("✅ MongoDB'dan %d ta obunachi yuklandi", len(subs))
            except Exception as me:
                logger.error("MongoDB'dan obunachilarni olishda xatolik: %s", me)

        return subs



# Global xotira instansiyasi
memory_service = SQLiteMemoryService()
