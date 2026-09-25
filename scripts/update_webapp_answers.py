with open("/Applications/Project/coddyHelper/web_app.py", "r") as f:
    content = f.read()

replacement = """
    async def handle_api_get_precomputed_answers(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        user_info = get_current_user(request)
        uid = 0 if user_info["is_super_admin"] else user_info["user_id"]
        items = memory_service.get_all_precomputed_answers(limit=60, owner_id=uid)
        return web.json_response({"ok": True, "items": items})
"""
import re
content = re.sub(r'    async def handle_api_get_precomputed_answers\(request: web\.Request\):.*?return web\.json_response\(\{"ok": True, "items": items\}\)', replacement, content, flags=re.DOTALL)

with open("/Applications/Project/coddyHelper/web_app.py", "w") as f:
    f.write(content)
print("Updated web_app precomputed answers")
