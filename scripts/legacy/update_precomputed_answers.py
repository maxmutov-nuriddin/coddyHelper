with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

# Update save_precomputed_answer
replacement_save = """
    def save_precomputed_answer(
        self, topic: str, question_pattern: str, answer_text: str, owner_id: int = 0
    ) -> bool:
        \"\"\"Yangi tayyor javobni saqlaydi.\"\"\"
        try:
            if mongo_memory_service.is_connected():
                mongo_memory_service.save_precomputed_answer(topic, question_pattern, answer_text, owner_id)
        except Exception as me:
            logger.debug("MongoDB ga precomputed answer yozish xatosi: %s", me)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    \"\"\"
                    INSERT INTO precomputed_answers (topic, question_pattern, answer_text, owner_id)
                    VALUES (?, ?, ?, ?)
                    \"\"\",
                    (topic, question_pattern, answer_text, owner_id),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error("save_precomputed_answer xatosi (SQLite): %s", e)
            return False
"""
import re
content = re.sub(r'    def save_precomputed_answer\(.*?return False', replacement_save, content, flags=re.DOTALL)

# Update get_all_precomputed_answers
replacement_get = """
    def get_all_precomputed_answers(self, limit: int = 50, owner_id: int = 0) -> list[dict]:
        \"\"\"Oldindan tayyorlangan barcha yechimlar ro'yxatini qaytaradi.\"\"\"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if owner_id and not self.is_super_admin(owner_id):
                    cursor.execute(
                        \"\"\"
                        SELECT id, topic, question_pattern, answer_text, usage_count, created_at
                        FROM precomputed_answers
                        WHERE owner_id = ? OR owner_id = 0
                        ORDER BY id DESC LIMIT ?
                        \"\"\",
                        (owner_id, limit),
                    )
                else:
                    cursor.execute(
                        \"\"\"
                        SELECT id, topic, question_pattern, answer_text, usage_count, created_at
                        FROM precomputed_answers
                        ORDER BY id DESC LIMIT ?
                        \"\"\",
                        (limit,),
                    )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "topic": r[1],
                        "question_pattern": r[2],
                        "answer_text": r[3],
                        "usage_count": r[4],
                        "created_at": r[5],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("get_all_precomputed_answers xatosi (SQLite): %s", e)
            return []
"""
content = re.sub(r'    def get_all_precomputed_answers\(.*?return \[\]', replacement_get, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/memory_service.py", "w") as f:
    f.write(content)
print("Updated precomputed_answers methods")
