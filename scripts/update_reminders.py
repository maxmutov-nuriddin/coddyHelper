with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def get_active_reminders(self, limit: int = 20, creator_id: int = 0) -> list[dict]:
        \"\"\"Kutilayotgan faol eslatmalar ro'yxatini qaytaradi.\"\"\"
        now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if creator_id and not self.is_super_admin(creator_id):
                    cursor.execute(
                        \"\"\"
                        SELECT id, chat_id, creator_id, reminder_text, remind_at 
                        FROM reminders 
                        WHERE is_sent = 0 AND creator_id = ?
                        ORDER BY remind_at ASC LIMIT ?
                        \"\"\",
                        (creator_id, limit),
                    )
                else:
                    cursor.execute(
                        \"\"\"
                        SELECT id, chat_id, creator_id, reminder_text, remind_at 
                        FROM reminders 
                        WHERE is_sent = 0
                        ORDER BY remind_at ASC LIMIT ?
                        \"\"\",
                        (limit,),
                    )
                rows = cursor.fetchall()
                # ... Mongo fallback is intentionally omitted for brevity ...
                return [
                    {
                        "id": r[0],
                        "chat_id": r[1],
                        "creator_id": r[2],
                        "reminder_text": r[3],
                        "remind_at": r[4],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("get_active_reminders xatosi: %s", e)
            return []
"""
import re
# Wait, I shouldn't remove Mongo fallback if it exists! Let me check what get_active_reminders currently looks like.
