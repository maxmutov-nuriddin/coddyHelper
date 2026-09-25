with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "r") as f:
    content = f.read()

replacement = """
    def get_all_active_reminders(self, limit: int = 50, creator_id: int = 0) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            query = {"is_sent": 0}
            if creator_id:
                # We need to assume memory_service handles super admin logic before calling mongo fallback
                query["creator_id"] = creator_id
            cursor = self.reminders.find(query).sort("remind_at", 1).limit(limit)
"""
import re
content = re.sub(r'    def get_all_active_reminders\(self, limit: int = 50\) -> list\[dict\]:.*?cursor = self\.reminders\.find\(query\)\.sort\("remind_at", 1\)\.limit\(limit\)', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/services/mongo_memory_service.py", "w") as f:
    f.write(content)
print("Updated mongo reminders")
