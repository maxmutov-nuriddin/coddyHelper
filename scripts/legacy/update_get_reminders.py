with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def get_active_reminders(self, limit: int = 20, creator_id: int = 0) -> list[dict]:
        \"\"\"Kutilayotgan faol eslatmalar ro'yxatini qaytaradi (Lokal SQLite -> Mongo fallback).\"\"\"
        now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if creator_id and not self.is_super_admin(creator_id):
                    cursor.execute(
                        \"\"\"
                        SELECT id, chat_id, creator_id, reminder_text, remind_at, created_at
                        FROM reminders
                        WHERE is_sent = 0 AND remind_at >= ? AND creator_id = ?
                        ORDER BY remind_at ASC
                        LIMIT ?
                        \"\"\",
                        (now_str, creator_id, limit),
                    )
                else:
                    cursor.execute(
                        \"\"\"
                        SELECT id, chat_id, creator_id, reminder_text, remind_at, created_at
                        FROM reminders
                        WHERE is_sent = 0 AND remind_at >= ?
                        ORDER BY remind_at ASC
                        LIMIT ?
                        \"\"\",
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
                m_rems = mongo_memory_service.get_all_active_reminders(limit=limit, creator_id=creator_id)
                if m_rems:
                    return [
"""
import re
content = re.sub(r'    def get_active_reminders\(self, limit: int = 20\) -> list\[dict\]:.*?if m_rems:\n                    return \[', replacement, content, flags=re.DOTALL)

# And update get_active_reminders_count
replacement_count = """
    def get_active_reminders_count(self, creator_id: int = 0) -> int:
        \"\"\"Hali yuborilmagan eslatmalar sonini qaytaradi.\"\"\"
        try:
            with self._get_connection() as conn:
                if creator_id and not self.is_super_admin(creator_id):
                    res = conn.execute("SELECT count(*) FROM reminders WHERE is_sent = 0 AND creator_id = ?", (creator_id,)).fetchone()
                else:
                    res = conn.execute("SELECT count(*) FROM reminders WHERE is_sent = 0").fetchone()
                return res[0] if res else 0
        except Exception:
            return 0
"""
content = re.sub(r'    def get_active_reminders_count\(self\) -> int:.*?return 0', replacement_count, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/memory_service.py", "w") as f:
    f.write(content)
print("Updated memory_service reminders")
