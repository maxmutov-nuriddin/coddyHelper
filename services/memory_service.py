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
