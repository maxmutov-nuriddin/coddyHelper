import re

with open("/Applications/Project/coddyHelper/web_app.py", "r") as f:
    content = f.read()

endpoint_code = """
    async def handle_api_update_my_group_id(request: web.Request):
        if not is_authenticated(request):
            return web.json_response({"ok": False, "error": "Ruxsat berilmagan!"}, status=403)
        user_info = get_current_user(request)
        try:
            data = await request.json()
            group_id = int(data.get("group_id", 0))
            # Agar super admin bo'lsa va maxsus user_id yuborgan bo'lsa
            target_user_id = int(data.get("user_id", 0))
            if user_info["is_super_admin"] and target_user_id:
                uid = target_user_id
            else:
                uid = user_info["user_id"]
                
            if not uid:
                return web.json_response({"ok": False, "error": "Foydalanuvchi aniqlanmadi"}, status=400)
                
            memory_service.link_user_group(uid, group_id)
            return web.json_response({"ok": True, "group_id": group_id, "user_id": uid})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
"""

content = content.replace('async def handle_api_upsert_subscription(request: web.Request):', endpoint_code + '\n    async def handle_api_upsert_subscription(request: web.Request):')
content = content.replace('app.router.add_post("/api/subscriptions", handle_api_upsert_subscription)', 'app.router.add_post("/api/update-group-id", handle_api_update_my_group_id)\n    app.router.add_post("/api/subscriptions", handle_api_upsert_subscription)')

with open("/Applications/Project/coddyHelper/web_app.py", "w") as f:
    f.write(content)

print("Endpoint added")
