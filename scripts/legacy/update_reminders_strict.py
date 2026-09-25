with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def get_active_reminders(self, limit: int = 20, creator_id: int = 0) -> list[dict]:
        \"\"\"Kutilayotgan faol eslatmalar ro'yxatini qaytaradi (Lokal SQLite -> Mongo fallback).\"\"\"
        now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if creator_id:
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
"""
import re
content = re.sub(r'    def get_active_reminders\(self, limit: int = 20, creator_id: int = 0\) -> list\[dict\]:.*?\(now_str, limit\),\n                    \)', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/memory_service.py", "w") as f:
    f.write(content)
print("Updated strict")
