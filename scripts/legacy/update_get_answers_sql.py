with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def get_all_precomputed_answers(self, limit: int = 50, owner_id: int = 0) -> list[dict]:
        \"\"\"Oldindan tayyorlangan barcha yechimlar ro'yxatini qaytaradi.\"\"\"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if owner_id:
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
                        WHERE owner_id = 0
                        ORDER BY id DESC LIMIT ?
                        \"\"\",
                        (limit,),
                    )
"""
import re
content = re.sub(r'    def get_all_precomputed_answers\(self, limit: int = 50, owner_id: int = 0\) -> list\[dict\]:.*?\(limit,\),\n                    \)', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/memory_service.py", "w") as f:
    f.write(content)
print("Updated")
