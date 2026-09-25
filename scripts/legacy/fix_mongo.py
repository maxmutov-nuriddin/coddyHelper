with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "r") as f:
    content = f.read()

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
            # Avoid duplicates
            self.precomputed_answers.update_one(
                {"question_pattern": question_pattern, "owner_id": owner_id},
                {"$setOnInsert": doc},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_precomputed_answer xatolik: %s", e)
            return False
"""
import re
content = re.sub(r'    def save_precomputed_answer\([\s\S]*?return False\s*', replacement, content, count=1)

replacement_get = """
    def get_all_precomputed_answers(self, limit: int = 100, owner_id: int = 0) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            query = {}
            if owner_id:
                query["owner_id"] = owner_id
            cursor = self.precomputed_answers.find(query).sort("created_at", -1).limit(limit)
"""
content = re.sub(r'    def get_all_precomputed_answers\(self, limit: int = 100\) -> list\[dict\]:\s*if not self.is_connected\(\):\s*return \[\]\s*try:\s*cursor = self.precomputed_answers.find\(\).sort\("created_at", -1\).limit\(limit\)', replacement_get, content)


with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "w") as f:
    f.write(content)

print("Fixed mongo_memory_service.py")
