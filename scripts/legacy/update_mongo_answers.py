with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def save_precomputed_answer(self, topic: str, question_pattern: str, answer_text: str, owner_id: int = 0) -> bool:
        if not self.is_connected():
            return False
        try:
            self.precomputed_answers.insert_one(
                {
                    "topic": topic,
                    "question_pattern": question_pattern,
                    "answer_text": answer_text,
                    "owner_id": owner_id,
                    "usage_count": 0,
                    "created_at": datetime.utcnow(),
                }
            )
            return True
        except Exception as e:
            logger.error("Mongo ga precomputed answer saqlashda xato: %s", e)
            return False
"""
import re
content = re.sub(r'    def save_precomputed_answer\(self, topic: str, question_pattern: str, answer_text: str\) -> bool:.*?return False', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "w") as f:
    f.write(content)
print("Updated mongo precomputed answers")
