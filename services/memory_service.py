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
                conn.commit()
        except Exception as e:
            logger.error("SQLite xotirasini ishga tushirishda xatolik: %s", e)

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


# Global xotira instansiyasi
memory_service = SQLiteMemoryService()
