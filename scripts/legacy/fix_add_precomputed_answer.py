with open("/Applications/Project/coddyHelper/services/memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def add_precomputed_answer(self, topic: str, question_pattern: str, answer_text: str, owner_id: int = 0, **kwargs) -> int | None:
        \"\"\"Kelgusida so'ralishi mumkin bo'lgan savollarga oldindan tayyorlangan mukammal javobni saqlaydi.\"\"\"
        try:
            with self._get_connection() as conn:
                try:
                    if mongo_memory_service.is_connected():
                        mongo_memory_service.save_precomputed_answer(
                            topic=topic.strip(),
                            question_pattern=question_pattern.strip(),
                            answer_text=answer_text.strip(),
                            owner_id=owner_id
                        )
                except Exception as me:
                    logger.debug("MongoDB ga precomputed answer yozishda ogohlantirish: %s", me)

                cur = conn.cursor()
                cur.execute(
                    \"\"\"
                    INSERT INTO precomputed_answers (topic, question_pattern, answer_text, owner_id)
                    VALUES (?, ?, ?, ?)
                    \"\"\",
                    (topic.strip(), question_pattern.strip(), answer_text.strip(), owner_id),
                )
                conn.commit()
                logger.info("Avtonom Miya oldindan javob saqladi: [%s] -> %s (owner: %s)", topic, question_pattern[:40], owner_id)
                return cur.lastrowid
        except Exception as e:
            logger.error("Oldindan tayyorlangan javobni saqlashda xatolik: %s", e)
            return None
"""
import re
content = re.sub(r'    def add_precomputed_answer\(self, topic: str, question_pattern: str, answer_text: str, \*\*kwargs\) -> int \| None:.*?return None', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/memory_service.py", "w") as f:
    f.write(content)
print("Fixed add_precomputed_answer")
