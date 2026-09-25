with open("/Applications/Project/coddyHelper/web_app.py", "r") as f:
    content = f.read()

replacement1 = """
    async def handle_api_get_reminders(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        user_info = get_current_user(request)
        uid = 0 if user_info["is_super_admin"] else user_info["user_id"]
        reminders = memory_service.get_active_reminders(50, creator_id=uid)
        return web.json_response({"ok": True, "reminders": reminders})
"""
import re
content = re.sub(r'    async def handle_api_get_reminders\(request: web\.Request\):.*?return web\.json_response\(\{"ok": True, "reminders": reminders\}\)', replacement1, content, flags=re.DOTALL)

replacement2 = """
                "active_reminders_count": memory_service.get_active_reminders_count(creator_id=(0 if user_info["is_super_admin"] else user_info["user_id"])),
"""
content = content.replace('                "active_reminders_count": memory_service.get_active_reminders_count(),\n', replacement2)

with open("/Applications/Project/coddyHelper/web_app.py", "w") as f:
    f.write(content)
print("Updated web_app reminders")
