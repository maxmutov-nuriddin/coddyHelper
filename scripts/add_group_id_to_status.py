with open("/Applications/Project/coddyHelper/web_app.py", "r") as f:
    content = f.read()

replacement1 = """
        telegram_me = _telegram_me_cache["me"]
        telegram_authorized = _telegram_me_cache["authorized"]

        user_info = get_current_user(request)
        current_group_id = 0
        if user_info and user_info.get("subscription"):
            current_group_id = user_info["subscription"].get("group_id", 0)

        active_ai = (
"""
content = content.replace('        telegram_me = _telegram_me_cache["me"]\n        telegram_authorized = _telegram_me_cache["authorized"]\n\n        active_ai = (', replacement1)

replacement2 = """
                "telegram_authorized": telegram_authorized,
                "telegram_me": telegram_me,
                "current_group_id": current_group_id,
"""
content = content.replace('                "telegram_authorized": telegram_authorized,\n                "telegram_me": telegram_me,\n', replacement2)

with open("/Applications/Project/coddyHelper/web_app.py", "w") as f:
    f.write(content)

print("Updated status API")
