"""
Tarif rejalari konfiguratsiyasi.
Har bir plan qaysi funksiyalarga ruxsat berishini belgilaydi.
"""

PLANS = {
    "pro": {
        "label": "Pro",
        "emoji": "⚡",
        "price_monthly": 99_000,
        "price_yearly": 890_000,
        "currency": "UZS",
        "features": {
            # Agent asosiy funksiyalar
            "auto_reply_enabled": True,
            "group_reply_enabled": True,
            "voice_reply_enabled": True,
            "web_search_enabled": True,
            "auto_answer_calls": True,
            "smart_reactions": True,
            "escalate_to_owner": True,
            # Sozlamalar
            "owner_pause_seconds": True,
            "debounce_seconds": True,
            "private_quiet_window": True,
            "reply_language": True,
            "accept_media": True,
            "group_reply_mode": True,
            # Panel tablar
            "tab_reminders": True,
            "tab_knowledge": True,
            "tab_security": True,
            "tab_agent_iq": False,  # Ultra
            # Ultra funksiyalar — Pro da yopiq
            "auto_delete_dangerous_files": False,
            "silent_mode": False,
            "vazifalar_status": False,
            "gemini_backup": False,
            "autonomous_brain": False,
            "auto_profiler": False,
            "emergency_wakeup": False,
        },
    },
    "ultra": {
        "label": "Ultra",
        "emoji": "🚀",
        "price_monthly": 179_000,
        "price_yearly": 1_590_000,
        "currency": "UZS",
        "features": {
            # Pro dagi hamma narsa + qo'shimcha
            "auto_reply_enabled": True,
            "group_reply_enabled": True,
            "voice_reply_enabled": True,
            "web_search_enabled": True,
            "auto_answer_calls": True,
            "smart_reactions": True,
            "escalate_to_owner": True,
            "owner_pause_seconds": True,
            "debounce_seconds": True,
            "private_quiet_window": True,
            "reply_language": True,
            "accept_media": True,
            "group_reply_mode": True,
            "tab_reminders": True,
            "tab_knowledge": True,
            "tab_security": True,
            # Ultra exclusive
            "tab_agent_iq": True,
            "auto_delete_dangerous_files": True,
            "silent_mode": True,
            "vazifalar_status": True,
            "gemini_backup": True,
            "autonomous_brain": True,
            "auto_profiler": True,
            "emergency_wakeup": True,
        },
    },
}


def get_plan_features(plan: str) -> dict:
    """Tarif rejasining funksiyalar ro'yxatini qaytaradi."""
    return PLANS.get(plan, PLANS["pro"])["features"]


def is_feature_allowed(plan: str, feature: str) -> bool:
    """Berilgan plan uchun funksiya ruxsat etilganligini tekshiradi."""
    return get_plan_features(plan).get(feature, True)


def get_plan_info(plan: str) -> dict:
    """Plan to'liq ma'lumotini qaytaradi."""
    p = PLANS.get(plan, PLANS["pro"])
    return {
        "plan": plan,
        "label": p["label"],
        "emoji": p["emoji"],
        "price_monthly": p["price_monthly"],
        "price_yearly": p["price_yearly"],
        "currency": p["currency"],
    }
