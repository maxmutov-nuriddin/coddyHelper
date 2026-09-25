with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "r") as f:
    content = f.read()

replacement_get = """
    def get_all_precomputed_answers(self, limit: int = 100, owner_id: int = 0) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            query = {}
            if owner_id:
                query["owner_id"] = owner_id
            return list(self._db["brain_knowledge.precomputed_answers"].find(query).limit(limit))
"""
import re
content = re.sub(r'    def get_all_precomputed_answers\([\s\S]*?return list\(self\._db\["brain_knowledge.precomputed_answers"\]\.find\(\)\.limit\(limit\)\)', replacement_get, content)

with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "w") as f:
    f.write(content)

print("Fixed mongo_memory_service.py get_all")
