import re

with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "r") as f:
    content = f.read()

# Let's find def save_precomputed_answer and replace everything up to def delete_precomputed_answer
replacement = """
    def save_precomputed_answer(
        self, topic: str, question_pattern: str, answer_text: str, owner_id: int = 0
    ) -> bool:
        if not self.is_connected() or not question_pattern or not answer_text:
            return False
        try:
            doc = {
                "topic": topic,
                "question_pattern": question_pattern,
                "answer_text": answer_text,
                "owner_id": owner_id,
                "usage_count": 0,
                "created_at": datetime.utcnow()
            }
            self._db["brain_knowledge.precomputed_answers"].update_one(
                {"question_pattern": question_pattern, "owner_id": owner_id},
                {"$setOnInsert": doc},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_precomputed_answer xatolik: %s", e)
            return False

    def delete_precomputed_answer"""

content = re.sub(r'    def save_precomputed_answer\([\s\S]*?def delete_precomputed_answer', replacement, content)

with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "w") as f:
    f.write(content)

print("Fixed mongo_memory_service.py final")
