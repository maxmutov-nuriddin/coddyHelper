"""
services/agent_tools.py
CoddyCamp Avtonom Agent Vositalari Markazi (Agent Tool Registry).
OpenAI / Groq Native Tool Calling spetsifikatsiyasi bo'yicha barcha asboblar va ularning ijrochilari.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger("coddy.agent_tools")

# 1. Native Tool Calling JSON Schemas (Groq / OpenAI Format)
AGENT_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "find_sick_students",
            "description": "Lichkalar va chatlar ichidan yaqin orada yoki bugun darsga kela olmasligini, kasal yoki betob ekanligini bildirgan barcha o'quvchilarni tahlil qilib topish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Tekshiriladigan oxirgi suhbatlar soni (standart: 40)",
                        "default": 40,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_contact",
            "description": "O'quvchi, kontakt, guruh yoki foydalanuvchini ismi, familiyasi yoki username (@) bo'yicha topish va uning profili/ma'lumotlarini olish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_query": {
                        "type": "string",
                        "description": "Qidirilayotgan shaxsning ismi, familiyasi yoki username'i",
                    }
                },
                "required": ["name_or_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "O'quvchiga, shaxsga, botga, guruhga yoki CoddyCamp ma'muriyatiga (@coddycamp_sergeli) Telegram orqali xabar yetkazish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Qabul qiluvchi: username (@coddycamp_sergeli, @user), chat nomi yoki telefon/ID",
                    },
                    "message": {
                        "type": "string",
                        "description": "Yuboriladigan xabar matni (chiroyli formatda)",
                    },
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_reminder",
            "description": "Belgilangan vaqtda o'quvchiga yoki mentorga eslatma/vazifa rejalashtirish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Kimga eslatma yuborilishi (username yoki ism)",
                    },
                    "message": {
                        "type": "string",
                        "description": "Eslatma matni",
                    },
                    "time_str": {
                        "type": "string",
                        "description": "Vaqt (masalan: 'tomorrow 10:00', 'ertaga 14:00', '15 minutes')",
                    },
                },
                "required": ["recipient", "message", "time_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mute_user",
            "description": "Faqat AI javob bermasligi uchun foydalanuvchini ignore qilish (Telegramda bloklanmaydi, shaxsiy yozishma ochiq qoladi).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Foydalanuvchi username'i (@user), ismi yoki Telegram ID si",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Ignore qilish sababi",
                        "default": "Mentor buyrug'i bilan ignore qilindi",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "block_user",
            "description": "Foydalanuvchini Telegram hisobingizda butunlay bloklash (Qora ro'yxatga kiritish) va AI unga javob bermaydigan qilish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Foydalanuvchi username'i (@user), ismi yoki Telegram ID si",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Telegramda bloklash sababi",
                        "default": "Mentor buyrug'i bilan bloklandi",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unmute_unblock_user",
            "description": "Foydalanuvchini Telegram blokidan ham, AI ignore ro'yxatidan ham to'liq chiqarish (barcha cheklovlarni bekor qilish).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Foydalanuvchi username'i (@user), ismi yoki Telegram ID si",
                    }
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_chat",
            "description": "Aniq guruh yoki suhbat ichidan xabarlarni qidirish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_target": {
                        "type": "string",
                        "description": "Guruh nomi, chat username yoki ID",
                    },
                    "query": {
                        "type": "string",
                        "description": "Qidirilayotgan so'z yoki ibora",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Qidiruv natijalari soni",
                        "default": 5,
                    },
                },
                "required": ["chat_target", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_telegram",
            "description": "Barcha Telegram suhbatlari bo'ylab xabarlarni global qidirish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Qidiruv so'zi",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Natijalar soni",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_info",
            "description": "Guruh yoki kanal haqidagi to'liq ma'lumotlar (a'zolar, tavsif, statistika)ni olish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_query": {
                        "type": "string",
                        "description": "Guruh nomi yoki username",
                    }
                },
                "required": ["group_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_senders",
            "description": "Oxirgi yozganlar ro'yxati, kelgan yangi va o'qilmagan xabarlarni ko'rish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Xabarlar soni",
                        "default": 10,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explore_bot",
            "description": "Telegram botini avtonom tarzda /start bosib, barcha tugmalari va bo'limlarini o'rganib chiqish va tahlil qilish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_username": {
                        "type": "string",
                        "description": "Bot username (@bot_nomi)",
                    }
                },
                "required": ["bot_username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_bot_button",
            "description": "Botdagi inline yoki klaviatura tugmasini bosish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_username": {
                        "type": "string",
                        "description": "Bot nomi yoki username",
                    },
                    "button_text": {
                        "type": "string",
                        "description": "Bosilishi kerak bo'lgan tugma nomi",
                    },
                },
                "required": ["bot_username", "button_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_search",
            "description": "Telegram va Internet (Google) orqali mavzuni chuqur tahlil qilib, eng to'g'ri ma'lumotlarni topib kelish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Qidiruv mavzusi",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "learn_fact",
            "description": "Yangi qoida, talab yoki faktni xotiraga saqlab qolish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Mavzu nomi",
                    },
                    "fact": {
                        "type": "string",
                        "description": "Qoida yoki ma'lumot matni",
                    },
                },
                "required": ["topic", "fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learned_facts",
            "description": "Agent xotirasidagi barcha o'rganilgan qoidalar va bilimlarni olish.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# 2. Tool Execution Engine (Ijro mexanizmi)
async def execute_tool_call(tool_name: str, arguments: Dict[str, Any], client, **kwargs) -> Dict[str, Any]:
    """
    LLM chaqirgan tool_name va argumentlarni tegishli Python asbobiga yo'naltiradi va
    ReAct tsikli uchun toza, strukturalangan javob qaytaradi.
    """
    from services.memory_service import memory_service
    from services import telegram_agent_service as tas

    reply_user_id = kwargs.get("reply_user_id")

    try:
        # 1. find_sick_students
        if tool_name == "find_sick_students":
            limit = int(arguments.get("limit", 40))
            res = await tas.find_sick_students_in_chats(client, limit=limit)
            return res

        # 2. find_contact
        elif tool_name == "find_contact":
            name_or_query = str(arguments.get("name_or_query", "")).strip()
            if not name_or_query:
                return {"ok": False, "error": "Qidiruv uchun ism yoki username kiritilmadi."}
            res = await tas.find_student_or_contact(client, name_or_query)
            return res

        # 3. send_telegram_message
        elif tool_name == "send_telegram_message":
            rec = str(arguments.get("recipient", "")).strip()
            msg = str(arguments.get("message", "")).strip()
            if not rec or not msg:
                return {"ok": False, "error": "Qabul qiluvchi yoki xabar matni bo'sh."}
            res = await tas.send_telegram_message(client, rec, msg)
            return res

        # 4. schedule_reminder
        elif tool_name == "schedule_reminder":
            rec = str(arguments.get("recipient", "")).strip()
            msg = str(arguments.get("message", "")).strip()
            time_str = str(arguments.get("time_str", "")).strip()
            res = await tas.schedule_telegram_message(client, rec, msg, time_str)
            return res

        # 5. mute_user (Ignore - Telegramda bloklanmaydi)
        elif tool_name == "mute_user":
            target = str(arguments.get("target", "")).strip()
            reason = str(arguments.get("reason", "Mentor buyrug'i bilan ignore qilindi")).strip()
            user_info = await tas.resolve_target_user(client, target, reply_user_id=reply_user_id)
            if not user_info.get("ok"):
                return {"ok": False, "error": user_info.get("error")}
            t_id = user_info["user_id"]
            t_uname = user_info.get("username", "")
            t_name = user_info.get("name", "Foydalanuvchi")
            memory_service.ignore_user(t_id, username=t_uname, reason=reason)
            return {
                "ok": True,
                "action": "muted",
                "user_id": t_id,
                "name": t_name,
                "username": t_uname,
                "blocked_in_telegram": False,
                "message": f"Foydalanuvchi {t_name} ({t_uname or t_id}) muvaffaqiyatli ignore qilindi. Telegramda bloklanmadi.",
            }

        # 6. block_user (Telegramda ham bloklash)
        elif tool_name == "block_user":
            target = str(arguments.get("target", "")).strip()
            reason = str(arguments.get("reason", "Mentor buyrug'i bilan bloklandi")).strip()
            user_info = await tas.resolve_target_user(client, target, reply_user_id=reply_user_id)
            if not user_info.get("ok"):
                return {"ok": False, "error": user_info.get("error")}
            t_id = user_info["user_id"]
            t_uname = user_info.get("username", "")
            t_name = user_info.get("name", "Foydalanuvchi")
            tg_ok = await tas.block_telegram_user(client, user_info.get("entity") or t_id)
            memory_service.ignore_user(t_id, username=t_uname, reason=reason)
            return {
                "ok": True,
                "action": "blocked",
                "user_id": t_id,
                "name": t_name,
                "username": t_uname,
                "blocked_in_telegram": tg_ok,
                "message": f"Foydalanuvchi {t_name} ({t_uname or t_id}) Telegramda ham, AI da ham butunlay bloklandi.",
            }

        # 7. unmute_unblock_user
        elif tool_name == "unmute_unblock_user":
            target = str(arguments.get("target", "")).strip()
            user_info = await tas.resolve_target_user(client, target, reply_user_id=reply_user_id)
            if not user_info.get("ok"):
                return {"ok": False, "error": user_info.get("error")}
            t_id = user_info["user_id"]
            memory_service.unignore_user(t_id)
            memory_service.clear_user_quota(t_id)
            await tas.unblock_telegram_user(client, user_info.get("entity") or t_id)
            return {
                "ok": True,
                "action": "unblocked",
                "user_id": t_id,
                "name": user_info.get("name"),
                "message": f"Foydalanuvchi {user_info.get('name')} barcha cheklovlardan (blok/ignordan) chiqarildi.",
            }

        # 8. search_chat
        elif tool_name == "search_chat":
            chat = str(arguments.get("chat_target", "")).strip()
            q = str(arguments.get("query", "")).strip()
            lim = int(arguments.get("limit", 5))
            res = await tas.search_chat_messages(client, chat, q, limit=lim)
            return {"ok": True, "results": res}

        # 9. search_telegram
        elif tool_name == "search_telegram":
            q = str(arguments.get("query", "")).strip()
            lim = int(arguments.get("limit", 5))
            res = await tas.search_telegram_messages(client, q, limit=lim)
            return {"ok": True, "results": res}

        # 10. get_group_info
        elif tool_name == "get_group_info":
            g = str(arguments.get("group_query", "")).strip()
            res = await tas.get_group_info(client, g)
            return res

        # 11. get_recent_senders
        elif tool_name == "get_recent_senders":
            lim = int(arguments.get("limit", 10))
            res = await tas.get_recent_incoming_senders(client, limit=lim)
            return {"ok": True, "senders": res}

        # 12. explore_bot
        elif tool_name == "explore_bot":
            b = str(arguments.get("bot_username", "")).strip()
            res = await tas.explore_telegram_bot(client, b)
            return res

        # 13. click_bot_button
        elif tool_name == "click_bot_button":
            b = str(arguments.get("bot_username", "")).strip()
            btn = str(arguments.get("button_text", "")).strip()
            res = await tas.click_chat_button(client, b, btn)
            return res

        # 14. deep_search
        elif tool_name == "deep_search":
            q = str(arguments.get("query", "")).strip()
            from services.search_service import search_web
            web_res = await search_web(q, max_results=3)
            tg_res = await tas.search_telegram_messages(client, q, limit=3)
            return {"ok": True, "web": web_res, "telegram": tg_res}

        # 15. learn_fact
        elif tool_name == "learn_fact":
            top = str(arguments.get("topic", "")).strip()
            fct = str(arguments.get("fact", "")).strip()
            memory_service.learn_fact(top, fct)
            return {"ok": True, "message": f"Yangi bilim muvaffaqiyatli o'rganildi va saqlandi: «{top}»"}

        # 16. get_learned_facts
        elif tool_name == "get_learned_facts":
            facts = memory_service.get_learned_facts()
            return {"ok": True, "facts": facts}

        else:
            return {"ok": False, "error": f"Noma'lum asbob (Unknown tool): {tool_name}"}

    except Exception as err:
        logger.error("Tool '%s' ijrosida xatolik: %s", tool_name, err, exc_info=True)
        return {"ok": False, "error": f"Tool xatoligi: {err}"}
