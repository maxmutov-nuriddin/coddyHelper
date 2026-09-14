"""
AI integratsiyasi (Groq Multi-Key va Google Gemini qo'llab-quvvatlanadi)
"""

import asyncio
import base64
import inspect
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from config import config, is_escalation_chat
from prompts import SYSTEM_PROMPT, ADMIN_SYSTEM_PROMPT
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

ESCALATE_PATTERN = re.compile(r"<<<ESCALATE>>>(.*?)<<<END_ESCALATE>>>", re.DOTALL)


def is_russian_text(text: str) -> bool:
    """Matn rus tilida ekanini aniqlaydi."""
    if not text:
        return False
    ru_chars = len(re.findall(r"[\u0400-\u04FF]", text))
    if ru_chars >= 2:
        return True
    return bool(re.search(r"\b(?:привет|здравствуйте|спасибо|пожалуйста|как|что|где|когда|почему|ошибка|помогите|подскажите|урок|занятие)\b", text, re.I))


def check_fast_faq(text: str) -> str | None:
    """Eng ko'p uchraydigan standart dasturlash xatolari va salomlashuvlarga 0.01 soniyada tayyor yechim beradi."""
    t = text.strip()
    if not t:
        return None

    # 0. Standart salomlashuvlar (0.001s da xushmuomala javob)
    clean_t = t.lower().rstrip("!?.,~ ")
    uzbek_greetings = {
        "salom", "assalomu alaykum", "assalom alaykum", "assalomu alekum", "assalomu aleykum",
        "assalom", "assalomaleykum", "assalomualaykum", "assalomualeykum", "salom aleykum",
        "salomaleykum", "salom alekum", "salom alaykum", "salom ustoz", "assalomu alaykum ustoz",
        "assalomu aleykum ustoz", "salom mentor", "qalaysiz", "yaxshimisiz", "tormisiz"
    }
    russian_greetings = {
        "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро", "хай"
    }
    english_greetings = {
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening"
    }
    if clean_t in uzbek_greetings:
        return "Assalomu alaykum! Yaxshimisiz? Dasturlash yoki dars masalalarida qanday yordam bera olaman?"
    if clean_t in russian_greetings:
        return "Здравствуйте! Чем могу помочь по урокам или программированию?"
    if clean_t in english_greetings:
        return "Hello! How can I help you with programming or lessons?"

    # 0.1 Minnatdorchilik (Rahmat / Spasibo)
    uzbek_thanks = {
        "rahmat", "raxmat", "katta rahmat", "katta raxmat", "tashakkur", "spasibo",
        "спасибо", "спасибо большое", "благодарю", "thanks", "thank you", "thx"
    }
    if clean_t in uzbek_thanks:
        return "Arzimaydi, salomat bo'ling! Yana savollaringiz bo'lsa bemalol yozing 😊"

    # 0.2 Ustozlarning telefon raqami yoki shaxsiy Telegrami so'ralganda
    contact_keywords = [
        "nomeri", "nomerini", "telefon raqam", "telefon raqami", "raqamini", "tel raqam",
        "tglari yomi", "tglari bormi", "telegrami bormi", "telegramini ber",
        "nomerini ber", "kontaktini ber", "kontaktini", "nomerin", "nomeri bosa"
    ]
    if any(k in clean_t for k in contact_keywords):
        return (
            "Ustozlarning shaxsiy telefon raqamlari berilmaydi. "
            "Barcha tashkiliy masalalar, yangi darslar va ma'lumotlar uchun "
            "CoddyCamp ma'muriyatiga murojaat qilishingiz mumkin:\n"
            "👉 @coddycamp_sergeli\n\n"
            "Dasturlash yoki dars vazifalari bo'yicha savollaringiz bo'lsa, bemalol shu yerda bering!"
        )

    # 0.3 "Sen kimsan?" / "Kim bu?" / "Кто ты?" / "Who are you?"
    who_are_you_uz = {
        "sen kimsan", "kim bu", "kimsan", "siz kimsiz", "sen kim", "vazifang nima", "kim siz",
        "botmisan", "ai misan", "kim bu ozi", "kim bu o'zi"
    }
    who_are_you_ru = {
        "кто ты", "ты кто", "кто вы", "вы кто", "что ты умеешь", "ты бот", "кто это"
    }
    who_are_you_en = {
        "who are you", "what are you", "who is this", "are you a bot", "are you ai"
    }
    if clean_t in who_are_you_uz:
        return (
            "Assalomu alaykum! Men CoddyCamp dasturlash mentori (Teacher / Nuriddin aka) tomonidan yaratilgan kichik AI yordamchisiman. "
            "Ustoz band boʻlganlarida sizga tezkor koʻmak berib turaman.\n\n"
            "Dasturlash kodlari yoki LMS topshiriqlari boʻyicha har qanday savollaringiz boʻlsa, bemalol soʻrashingiz mumkin! "
            "Agar oʻzim yordam bera olmagan murakkab savollar boʻlsa, ustozning oʻzlariga yetkazib qoʻyaman 😊"
        )
    if clean_t in who_are_you_ru:
        return (
            "Здравствуйте! Я ИИ-помощник, созданный преподавателем программирования CoddyCamp (Нуриддин ака). "
            "Я помогаю с ответами, когда учитель занят.\n\n"
            "Если у вас есть любые вопросы по программному коду или заданиям LMS — смело обращайтесь! "
            "А если вопрос окажется слишком сложным, я обязательно передам его лично учителю 😊"
        )
    if clean_t in who_are_you_en:
        return (
            "Hello! I am an AI assistant created by CoddyCamp coding mentor (Teacher / Nuriddin). "
            "I provide quick assistance while the mentor is busy.\n\n"
            "Feel free to ask any questions regarding programming code or LMS assignments! "
            "If there are complex questions I cannot resolve, I will forward them directly to the teacher 😊"
        )

    is_ru = is_russian_text(t)

    # 1. ModuleNotFoundError
    mod_match = re.search(r"ModuleNotFoundError:\s*No module named\s*['\"]([^'\"]+)['\"]", t, re.IGNORECASE)
    if mod_match:
        pkg = mod_match.group(1)
        pip_pkg = pkg
        pkg_map = {
            "telebot": "pyTelegramBotAPI",
            "cv2": "opencv-python",
            "bs4": "beautifulsoup4",
            "dotenv": "python-dotenv",
            "pil": "pillow",
            "aiogram": "aiogram",
            "telethon": "telethon",
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
            "django": "django",
            "flask": "flask",
            "pygame": "pygame",
            "numpy": "numpy",
            "pandas": "pandas",
            "requests": "requests",
            "sqlalchemy": "sqlalchemy",
            "pydantic": "pydantic",
        }
        pip_pkg = pkg_map.get(pkg.lower(), pkg)

        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** Библиотека `{pkg}` не установлена.\n\n"
                f"🛠 **Решение:** Выполните в терминале команду:\n"
                f"```bash\npip install {pip_pkg}\n```\n"
                f"_Если вы используете виртуальное окружение (venv), сначала активируйте его._"
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `{pkg}` kutubxonasi o'rnatilmagan.\n\n"
            f"🛠 **Yechim:** Terminalga quyidagi buyruqni yozing:\n"
            f"```bash\npip install {pip_pkg}\n```\n"
            f"_Agar virtual muhit (venv) ishlatayotgan bo'lsangiz, avval venv ni faollashtiring._"
        )

    # 2. 'pip' is not recognized / pip topilmadi
    if ("'pip' is not recognized" in t.lower()) or ("pip topilmadi" in t.lower()) or ("pip: command not found" in t.lower()):
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** Система не распознает команду `pip` (Python не добавлен в PATH).\n\n"
                "🛠 **Решение (2 способа):**\n"
                "1. **Быстрый способ:** Запустите установку через python модуль:\n"
                "```bash\npython -m pip install <название_библиотеки>\n```\n"
                "2. **Основное решение:** При установке Python обязательно поставьте галочку **'Add Python to PATH'**."
            )
        return (
            "🔍 **Aniqlangan xatolik:** Tizim `pip` buyrug'ini taniy olmayapti (Python PATH muhitiga qo'shilmagan).\n\n"
            "🛠 **Yechim (2 xil usul):**\n"
            "1. **Tezkor usul:** Terminalda quyidagicha yozing:\n"
            "```bash\npython -m pip install <kutubxona_nomi>\n```\n"
            "2. **Asosiy yechim:** Python ni qayta o'rnatayotganda pastdagi **'Add Python to PATH'** katagiga belgi qo'ying."
        )

    # 3. IndentationError / TabError
    if "indentationerror" in t.lower() or "taberror" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `IndentationError` — Нарушены отступы (пробелы/табуляция) в коде.\n\n"
                "🛠 **Решение (Подсказка):**\n"
                "• В Python строки внутри блоков `if`, `for`, `def`, `while` должны иметь одинаковый отступ — ровно **4 пробела (или 1 Tab)**.\n"
                "• Проверьте указанную строку и выровняйте все отступы одинаково."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `IndentationError` — Qator boshidagi bo'shliqlar (probellar) xato ketgan.\n\n"
            "🛠 **Yechim (Maslahat):**\n"
            "• Python'da `if`, `for`, `def`, `while` dan keyingi qatorlar aniq **4 ta probel (yoki 1 ta Tab)** bilan ichkariga surilishi shart.\n"
            "• Barcha qatorlardagi bo'shliqlarni bir xil qilib to'g'rilab chiqing."
        )

    # 4. SyntaxError
    syntax_match = re.search(r"SyntaxError:\s*(.+)", t, re.IGNORECASE)
    if syntax_match:
        s_detail = syntax_match.group(1).strip()
        if "unexpected eof" in s_detail.lower():
            hint_uz = "Qator oxirida qavs `()`, jingalak qavs `{}` yoki qo'shtirnoq `\"` yopilmay qolgan."
            hint_ru = "В конце строки не закрыта скобка `()`, `{}` или кавычка `\"`."
        elif "unmatched" in s_detail.lower() or "closing parenthesis" in s_detail.lower():
            hint_uz = "Ortiqcha yoki mos kelmaydigan qavs yopilgan. Qavslar juftligini tekshiring."
            hint_ru = "Лишняя или несоответствующая закрывающая скобка. Проверьте парность скобок."
        else:
            hint_uz = "Ko'rsatilgan qatorda `:` (ikki nuqta) qolib ketmaganini yoki sintaksis belgilari to'g'ri ekanini tekshiring."
            hint_ru = "Проверьте, не пропущено ли двоеточие `:` в конце строки (после if, for, def) и правильность знаков."

        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `SyntaxError: {s_detail}`\n\n"
                f"🛠 **Решение (Подсказка):** {hint_ru}"
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `SyntaxError: {s_detail}`\n\n"
            f"🛠 **Yechim (Maslahat):** {hint_uz}"
        )

    # 5. NameError
    name_match = re.search(r"NameError:\s*name\s*['\"]([^'\"]+)['\"]\s*is not defined", t, re.IGNORECASE)
    if name_match:
        var_name = name_match.group(1)
        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `NameError: name '{var_name}' is not defined` — Переменная или функция `{var_name}` не объявлена.\n\n"
                f"🛠 **Решение (Подсказка):**\n"
                f"• Проверьте регистр букв (Python различает большие и маленькие буквы).\n"
                f"• Убедитесь, что переменная `{var_name}` создана ВЫШЕ строки, где вы ее используете."
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `NameError: name '{var_name}' is not defined` — `{var_name}` nomli o'zgaruvchi yoki funksiya topilmadi.\n\n"
            f"🛠 **Yechim (Maslahat):**\n"
            f"• Katta-kichik harflar to'g'ri yozilganini tekshiring (Python ularni farqlaydi).\n"
            f"• `{var_name}` o'zgaruvchisi ishlatilishidan TEPADA yaratilganiga ishonch hosil qiling."
        )

    # 6. TypeError
    type_match = re.search(r"TypeError:\s*(.+)", t, re.IGNORECASE)
    if type_match:
        t_detail = type_match.group(1).strip()
        if "concatenate str" in t_detail.lower():
            hint_uz = "Matn (`str`) bilan sonni (`int`) to'g'ridan-to'g'ri `+` bilan qo'shib bo'lmaydi. Sonni `str(son)` ga o'giring yoki `f\"{matn}{son}\"` ishlating."
            hint_ru = "Нельзя объединять строку (`str`) и число (`int`) через `+`. Преобразуйте число: `str(число)` или используйте `f\"{строка}{число}\"`."
        elif "nonetype" in t_detail.lower():
            hint_uz = "O'zgaruvchi qiymati bo'sh (`None`), lekin undan metod yoki qiymat chaqirilyapti. Avval `if ozgaruvchi is not None:` deb tekshiring."
            hint_ru = "Значение переменной равно `None`, но у нее вызывается метод или свойство. Добавьте проверку `if переменная is not None:`."
        else:
            hint_uz = "Mos kelmaydigan ma'lumot turlari yoki noto'g'ri parametrlar uzatilgan. Qiymatlar turini `type(...)` orqali tekshiring."
            hint_ru = "Переданы несовместимые типы данных. Проверьте типы значений с помощью `type(...)`."

        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `TypeError: {t_detail}`\n\n"
                f"🛠 **Решение (Подсказка):** {hint_ru}"
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `TypeError: {t_detail}`\n\n"
            f"🛠 **Yechim (Maslahat):** {hint_uz}"
        )

    # 7. AttributeError
    attr_match = re.search(r"AttributeError:\s*['\"]?(\w+)['\"]?\s*object has no attribute\s*['\"]([^'\"]+)['\"]", t, re.IGNORECASE)
    if attr_match:
        obj_name = attr_match.group(1)
        attr_name = attr_match.group(2)
        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `AttributeError: '{obj_name}' object has no attribute '{attr_name}'` — У объекта `{obj_name}` нет метода или свойства `{attr_name}`.\n\n"
                f"🛠 **Решение (Подсказка):** Проверьте правильность написания метода `{attr_name}` и убедитесь, что тип объекта действительно тот, который вы ожидаете (`print(type({obj_name}))`)."
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `AttributeError: '{obj_name}' object has no attribute '{attr_name}'` — `{obj_name}` obyektida `{attr_name}` nomli metod yoki xususiyat mavjud emas.\n\n"
            f"🛠 **Yechim (Maslahat):** Metod nomi to'g'ri yozilganini va obyekt kutilgan turda ekanini tekshiring (`print(type({obj_name}))`)."
        )

    # 8. ZeroDivisionError
    if "zerodivisionerror" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `ZeroDivisionError: division by zero` — Деление на ноль невозможно.\n\n"
                "🛠 **Решение (Подсказка):** Перед делением добавьте проверку: `if делитель != 0:`."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `ZeroDivisionError: division by zero` — Sonni 0 ga bo'lish mumkin emas.\n\n"
            "🛠 **Yechim (Maslahat):** Bo'lish amalini bajarishdan oldin maxraj 0 ga teng emasligini tekshiring: `if maxraj != 0:`."
        )

    # 9. FileNotFoundError
    fn_match = re.search(r"FileNotFoundError:\s*\[Errno 2\]\s*No such file or directory:\s*['\"]([^'\"]+)['\"]", t, re.IGNORECASE)
    if fn_match:
        fname = fn_match.group(1)
        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `FileNotFoundError` — Файл `{fname}` не найден.\n\n"
                f"🛠 **Решение (Подсказка):** Убедитесь, что файл существует и скрипт запускается из правильной папки. Попробуйте указать полный (абсолютный) путь к файлу."
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `FileNotFoundError` — `{fname}` nomli fayl topilmadi.\n\n"
            f"🛠 **Yechim (Maslahat):** Fayl nomi to'g'riligini va dastur o'sha fayl turgan papkadan ishga tushirilayotganini tekshiring yoki faylning to'liq manzilini ko'rsating."
        )

    # 10. RecursionError
    if "recursionerror" in t.lower() or "maximum recursion depth" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `RecursionError: maximum recursion depth exceeded` — Бесконечная рекурсия.\n\n"
                "🛠 **Решение (Подсказка):** Функция бесконечно вызывает саму себя. Проверьте базовое условие выхода (base condition, например: `if n <= 1: return ...`)."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `RecursionError: maximum recursion depth exceeded` — Cheksiz rekursiya yuzaga keldi.\n\n"
            "🛠 **Yechim (Maslahat):** Funksiya o'zini to'xtovsiz chaqirmoqda. Rekursiyadan chiqish shartini (`if n <= 1: return ...`) to'g'ri qo'yganingizni tekshiring."
        )

    # 11. UnboundLocalError
    if "unboundlocalerror" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `UnboundLocalError` — Локальная переменная использована до того, как ей было присвоено значение.\n\n"
                "🛠 **Решение (Подсказка):** Если вы хотите изменить глобальную переменную внутри функции, добавьте `global <переменная>` в начале функции."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `UnboundLocalError` — Funksiya ichida o'zgaruvchiga qiymat berilishidan oldin unga murojaat qilingan.\n\n"
            "🛠 **Yechim (Maslahat):** Agar global o'zgaruvchini funksiya ichida o'zgartirmoqchi bo'lsangiz, funksiya boshiga `global <ozgaruvchi>` deb yozing."
        )

    # 12. ValueError (invalid literal for int)
    if "invalid literal for int() with base 10" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `ValueError: invalid literal for int() with base 10` — Невозможно преобразовать нечисловую строку в целое число `int()`.\n\n"
                "🛠 **Решение (Подсказка):** Проверьте, что вводимая строка содержит только цифры (`if s.isdigit():`), либо используйте блок `try...except ValueError`."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `ValueError: invalid literal for int() with base 10` — Harf yoki noaniq belgini `int()` orqali songa aylantirib bo'lmaydi.\n\n"
            "🛠 **Yechim (Maslahat):** Kiritilgan matn faqat raqamlardan iborat ekanini tekshiring (`if matn.isdigit():`) yoki `try...except ValueError` blokidan foydalaning."
        )

    # 13. Telegram Conflict (terminated by other getUpdates)
    if "conflict: terminated by other getupdates request" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** Telegram Bot Token Conflict — Бот запущен одновременно в двух местах!\n\n"
                "🛠 **Решение:**\n"
                "1. Закройте все остальные терминалы или вкладки VS Code, где запущен этот бот (Ctrl + C).\n"
                "2. Запустите бота только в одном месте."
            )
        return (
            "🔍 **Aniqlangan xatolik:** Telegram Bot Token Conflict — Bot bir vaqtning o'zida ikkita joyda ishlab turibdi!\n\n"
            "🛠 **Yechim:**\n"
            "1. Bot ochilgan boshqa barcha terminallar yoki VS Code oynalarini to'xtating (Ctrl + C).\n"
            "2. Faqat bitta joyda botni qayta ishga tushiring. Shunda ziddiyat yo'qoladi."
        )

    # 14. IndexError: list index out of range
    if "indexerror: list index out of range" in t.lower() or "indexerror" in t.lower():
        if is_ru:
            return (
                "🔍 **Обнаруженная ошибка:** `IndexError: list index out of range` — Обращение к несуществующему индексу списка.\n\n"
                "🛠 **Решение (Подсказка):**\n"
                "• Например, если в списке 3 элемента, их индексы: `0, 1, 2`. Вы обращаетесь к индексу 3 или больше.\n"
                "• Перед вызовом элемента проверьте длину списка: `if len(список) > index:`."
            )
        return (
            "🔍 **Aniqlangan xatolik:** `IndexError: list index out of range` — Ro'yxatda mavjud bo'lmagan indeksga murojaat qilingan.\n\n"
            "🛠 **Yechim:**\n"
            "• Masalan, ro'yxatda 3 ta element bo'lsa, uning indekslari: `0, 1, 2`. Siz `3` yoki undan katta indeksni chaqiryapsiz.\n"
            "• Element chaqirishdan oldin ro'yxat uzunligini tekshiring: `if len(royxat) > index:`"
        )

    # 15. KeyError
    key_match = re.search(r"KeyError:\s*['\"]?([^'\"]+)['\"]?", t, re.IGNORECASE)
    if key_match:
        k_name = key_match.group(1)
        if is_ru:
            return (
                f"🔍 **Обнаруженная ошибка:** `KeyError: '{k_name}'` — В словаре (dict) отсутствует ключ `{k_name}`.\n\n"
                f"🛠 **Решение (Подсказка):** Используйте безопасный метод `.get()`:\n"
                f"```python\nзначение = словарь.get('{k_name}', None)\n```"
            )
        return (
            f"🔍 **Aniqlangan xatolik:** `KeyError: '{k_name}'` — Lug'atda (dictionary) `{k_name}` nomli kalit mavjud emas.\n\n"
            f"🛠 **Yechim:** Xavfsiz usuldan foydalaning:\n"
            f"```python\nqiymat = lugat.get('{k_name}', None)\n```"
        )

    return None


def redact_sensitive_data(text: str) -> str:
    """API kalitlari, tokenlar va maxfiy ma'lumotlarni chatga chiqib ketishidan tozalaydi."""
    if not text:
        return ""
    # Groq API kalitlari
    text = re.sub(r"gsk_[A-Za-z0-9_]{20,}", "[MAXFIY_KALIT]", text)
    # Gemini API kalitlari
    text = re.sub(r"AIzaSy[A-Za-z0-9_\-]{30,}", "[MAXFIY_KALIT]", text)
    # Telegram Bot tokenlari
    text = re.sub(r"\b\d{8,11}:[A-Za-z0-9_-]{32,}\b", "[MAXFIY_TOKEN]", text)
    # Maxfiy sessiya qatorlari
    text = re.sub(r"1[A-Za-z0-9+/=]{100,}", "[MAXFIY_SESSIYA]", text)
    return text


def optimize_image_for_vision(image_bytes: bytes, max_dim: int = 960, quality: int = 80) -> bytes:
    """
    Katta hajmdagi skrinshot va rasmlarni Groq token limitlariga (7000 ITPM) moslash uchun
    sifatini buzmagan holda o'lchamini ixchamlashtiradi va JPEG siqadi.
    """
    if not image_bytes:
        return image_bytes
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > max_dim:
            if w > h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=quality, optimize=True)
        compressed = out_buf.getvalue()
        logger.info(
            "Rasm AI Vision uchun optimizatsiya qilindi: %d bayt -> %d bayt (o'lchami: %dx%d)",
            len(image_bytes), len(compressed), img.size[0], img.size[1]
        )
        return compressed
    except Exception as e:
        logger.warning("Rasmni siqishda ogohlantirish: %s", e)
        return image_bytes


def extract_smart_reminder(text: str, current_tashkent_time: str | None = None) -> dict | None:
    """
    O'zbek tilidagi har qanday eslatma so'rovidan (nisbiy vaqt, sana, soat, minut, daqiqa)
    vazifa va aniq YYYY-MM-DD HH:MM:SS vaqtini 0.001 soniyada, AI siz, 100% aniqlikda ajratib oladi.
    Masalan:
      '2 soatdan song elsat' -> {'reminder_text': 'Rejalashtirilgan eslatma', 'remind_at': '...'}
      '2 soatdan keyin dars boshlash' -> {'reminder_text': 'dars boshlash', 'remind_at': '...'}
      '15 minutdan keyin kitob' -> {'reminder_text': 'kitob', 'remind_at': '...'}
      '1 soat 30 minutdan keyin' -> {'reminder_text': 'Rejalashtirilgan eslatma', 'remind_at': '...'}
      'bugun 20:00 da dars' -> {'reminder_text': 'dars', 'remind_at': '...'}
      'ertaga 10:00 da imtihon' -> {'reminder_text': 'imtihon', 'remind_at': '...'}
      '25 09 2026 15:00 da dars' -> {'reminder_text': 'dars', 'remind_at': '...'}
    """
    t = text.strip()
    if not t:
        return None

    # Hozirgi Toshkent vaqtini aniqlash
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    if current_tashkent_time:
        try:
            now = datetime.strptime(current_tashkent_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tashkent_tz)
        except Exception:
            now = datetime.now(tashkent_tz)
    else:
        now = datetime.now(tashkent_tz)

    target_dt = None
    matched_span = None

    # 0. O'zbekcha so'z bilan yozilgan sonlarni raqamga o'girish (ikki soat -> 2 soat)
    uz_num_map = [
        (r"\bo['’‘`]?n\s+besh\b", "15"),
        (r"\byigirma\s+besh\b", "25"),
        (r"\bo['’‘`]?ttiz\b", "30"),
        (r"\bqirq\s+besh\b", "45"),
        (r"\bbir\b", "1"),
        (r"\bikki\b", "2"),
        (r"\buch\b", "3"),
        (r"\bto['’‘`]?rt\b", "4"),
        (r"\bbesh\b", "5"),
        (r"\bolti\b", "6"),
        (r"\byetti\b", "7"),
        (r"\bsakkiz\b", "8"),
        (r"\bto['’‘`]?qqiz\b", "9"),
        (r"\bo['’‘`]?n\b", "10"),
        (r"\byigirma\b", "20"),
        (r"\bqirq\b", "40"),
        (r"\bellik\b", "50"),
    ]
    t_norm = t
    for pat, rep in uz_num_map:
        t_norm = re.sub(pat, rep, t_norm, flags=re.IGNORECASE)

    # =========================================================
    # 1. Aniq sana: DD MM YYYY, DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
    # =========================================================
    date_patterns = [
        r'(?:^|\s)(?P<day>\d{1,2})[\s\.\/\-](?P<month>\d{1,2})[\s\.\/\-](?P<year>\d{4})(?:\s+(?:da|kuni))?(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})(?:\s*da)?)?',
        r'(?:^|\s)(?P<year>\d{4})[\s\.\/\-](?P<month>\d{1,2})[\s\.\/\-](?P<day>\d{1,2})(?:\s+(?:da|kuni))?(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})(?:\s*da)?)?',
    ]
    for pat in date_patterns:
        m = re.search(pat, t_norm, re.IGNORECASE)
        if m:
            gd = m.groupdict()
            try:
                year = int(gd['year'])
                month = int(gd['month'])
                day = int(gd['day'])
                h = int(gd['hour']) if gd.get('hour') else 10
                mi = int(gd['min']) if gd.get('min') else 0
                target_dt = datetime(year, month, day, h, mi, 0, tzinfo=tashkent_tz)
                matched_span = m.span()
                break
            except Exception:
                pass

    # =========================================================
    # 2. Nisbiy vaqt: Kun, Soat va Daqiqa/Minut kombinatsiyalari
    # Masalan:
    # "2 soatdan song", "2 soatdan keyin", "2 soat 30 minutdan keyin"
    # "1 soat 15 daqiqadan so'ng", "45 minutdan keyin", "yarim soatdan song"
    # "10 daqiqadan keyin", "2 soat", "15 minut", "1 kundan keyin"
    # =========================================================
    if not target_dt:
        # A) Yarim soat
        m_yarim = re.search(r'(?:^|\s)(?:yarim\s+soat)(?:(?:\s*dan)?\s*(?:keyin|so[\'’‘`]?ng|o[\'’‘`]?tgach|o[\'’‘`]?tib))?', t_norm, re.IGNORECASE)
        if m_yarim:
            target_dt = now + timedelta(minutes=30)
            matched_span = m_yarim.span()
        else:
            # B) Kun, umumiy soat va/yoki minut
            rel_pat = re.compile(
                r'(?:^|\s)(?:cherez\s+)?'
                r'(?:(?P<days>\d+)\s*(?:kun|den)(?:[a-z]*\s*(?:u|va))?\s*)?'
                r'(?:(?P<hours>\d+(?:[\.,]\d+)?)\s*(?:soat|chas(?:a|ov)?)(?:[a-z]*\s*(?:u|va))?\s*)?'
                r'(?:(?P<mins>\d+)\s*(?:daqiqa|minut|min|m)(?:[a-z]*\s*)?)?'
                r'(?:(?:\s*dan)?\s*(?:keyin|so[\'’‘`]?ng|o[\'’‘`]?tgach|o[\'’‘`]?tib|spustya))?',
                re.IGNORECASE
            )
            for m in rel_pat.finditer(t_norm):
                days_str = m.group('days')
                hours_str = m.group('hours')
                mins_str = m.group('mins')
                if days_str or hours_str or mins_str:
                    total_minutes = 0.0
                    if days_str:
                        total_minutes += int(days_str) * 24 * 60
                    if hours_str:
                        h_val = float(hours_str.replace(',', '.'))
                        total_minutes += h_val * 60
                    if mins_str:
                        total_minutes += int(mins_str)
                    
                    if total_minutes > 0:
                        target_dt = now + timedelta(minutes=total_minutes)
                        matched_span = m.span()
                        break

    # =========================================================
    # 3. Bugun / Ertaga / Indinga + Aniq soat
    # Masalan: "bugun 20:00 da", "ertaga 10:30 da", "ertaga soat 14 da"
    # =========================================================
    if not target_dt:
        day_pat = re.compile(
            r'(?:^|\s)(?P<day_word>bugun|ertaga|indinga)'
            r'(?:\s+(?:kuni))?'
            r'(?:\s+(?:soat\s+)?(?P<hour>\d{1,2})(?:[:\.\-](?P<min>\d{2}))?(?:\s*da)?)?',
            re.IGNORECASE
        )
        m = day_pat.search(t_norm)
        if m:
            day_word = m.group('day_word').lower()
            hour_str = m.group('hour')
            min_str = m.group('min')

            days_add = 0
            if day_word == 'bugun':
                days_add = 0
            elif day_word == 'ertaga':
                days_add = 1
            elif day_word == 'indinga':
                days_add = 2

            base_date = (now + timedelta(days=days_add)).date()
            h = int(hour_str) if hour_str else 10
            mi = int(min_str) if min_str else 0

            target_candidate = datetime(base_date.year, base_date.month, base_date.day, h, mi, 0, tzinfo=tashkent_tz)
            if day_word == 'bugun' and target_candidate < now:
                target_candidate = target_candidate + timedelta(days=1)

            target_dt = target_candidate
            matched_span = m.span()

    # =========================================================
    # 4. Faqat Soat ko'rsatilgan holat: "soat 18:00 da", "18:30 da"
    # =========================================================
    if not target_dt:
        clock_pat = re.compile(
            r'(?:^|\s)(?:soat\s+)?(?P<hour>\d{1,2})[:\.\-](?P<min>\d{2})\s*(?:da)?',
            re.IGNORECASE
        )
        m = clock_pat.search(t_norm)
        if m:
            h = int(m.group('hour'))
            mi = int(m.group('min'))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                target_candidate = datetime(now.year, now.month, now.day, h, mi, 0, tzinfo=tashkent_tz)
                if target_candidate <= now:
                    target_candidate += timedelta(days=1)
                target_dt = target_candidate
                matched_span = m.span()

    if not target_dt:
        return None

    remind_at = target_dt.strftime('%Y-%m-%d %H:%M:%S')

    # =========================================================
    # 5. Vazifa matnini tozalash (task cleaning)
    # =========================================================
    if matched_span:
        clean_text = t_norm[:matched_span[0]] + ' ' + t_norm[matched_span[1]:]
    else:
        clean_text = t_norm

    stop_words = [
        r'\belsat\b',
        r'\beslat\b',
        r'\beslatgin\b',
        r'\beslatvor\b',
        r'\beslatib\s+q[oʻ\'’‘`]?y(?:gin)?\b',
        r'\beslatib\s+turgin\b',
        r'\beslatma\b',
        r'\beslatish\b',
        r'\bkeyin\b',
        r'\bso[\'’‘`]?ng\b',
        r'\bo[\'’‘`]?tgach\b',
        r'\bo[\'’‘`]?tib\b',
        r'\bsoat\b',
        r'\bdan\b',
        r'\bda\b',
        r'\bkuni\b',
        r'\bdeb\b',
    ]
    for sw in stop_words:
        clean_text = re.sub(sw, ' ', clean_text, flags=re.IGNORECASE)

    clean_text = re.sub(r'\s+', ' ', clean_text).strip(' -:,\t\n')

    if not clean_text or len(clean_text) < 2:
        clean_text = "Rejalashtirilgan eslatma"

    return {
        "reminder_text": clean_text,
        "remind_at": remind_at
    }


extract_explicit_reminder = extract_smart_reminder


class AIResult(str):
    """Matn sifatida ishlaydi, shuningdek qo'shimcha .escalation ma'lumotiga ega."""
    escalation: str | None

    def __new__(cls, text: str, escalation: str | None = None):
        obj = super().__new__(cls, text)
        obj.escalation = escalation
        return obj


class AIService:
    def __init__(self):
        self._groq_clients: list[Any] = []
        self._groq_idx: int = 0
        self._gemini_client: Any = None
        self._metrics: dict[str, Any] = {
            "active_model": config.groq_model,
            "last_provider": "Groq",
            "last_model": config.groq_model,
            "last_updated": None,
            "total_requests": 0,
            "total_tokens": 0,
            "last_request": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "duration_ms": 0,
                "timestamp": None,
            },
            "rate_limits": {
                "remaining_tokens": 12000,
                "limit_tokens": 12000,
                "used_tokens_pct": 0.0,
                "remaining_requests": 30,
                "limit_requests": 30,
                "reset_tokens": "0s",
                "reset_requests": "0s",
            },
            "cascade_status": {
                "qwen/qwen3.8-27b": {"role": "Asosiy (27B)", "state": "active", "context": "128k", "tpm": "30k", "rpm": 30},
                "openai/gpt-oss-120b": {"role": "Zaxira 1 (120B)", "state": "standby", "context": "128k", "tpm": "120k", "rpm": 30},
                "openai/gpt-oss-20b": {"role": "Zaxira 2 (20B)", "state": "standby", "context": "128k", "tpm": "30k", "rpm": 30},
                "Google Gemini": {"role": "Temir Zaxira (1M)", "state": "standby", "context": "1M", "tpm": "1M", "rpm": 15},
            },
        }
        self._setup_clients()

    def restart(self) -> None:
        """AI Service holatini to'liq tozalaydi, kalitlarni qayta ulaydi va barcha statuslarni tiklaydi."""
        self._groq_idx = 0
        if "cascade_status" in self._metrics:
            for m in self._metrics["cascade_status"].values():
                if m.get("role", "").startswith("Asosiy"):
                    m["state"] = "active"
                else:
                    m["state"] = "standby"
                m.pop("last_error", None)
        self._setup_clients()
        logger.info("🔄 AIService to'liq qayta yuklandi va ulanishlar yangilandi.")

    def _record_groq_metrics(self, model_name: str, response: Any, headers: Any = None, duration_ms: int = 0) -> None:
        """Groq API so'rovidan qaytgan tokenlar va x-ratelimit HTTP sarlavhalarini hisobga oladi."""
        try:
            self._metrics["last_provider"] = "Groq"
            self._metrics["active_model"] = model_name
            actual_model = getattr(response, "model", model_name) or model_name
            self._metrics["last_model"] = actual_model
            now_iso = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
            self._metrics["last_updated"] = now_iso
            self._metrics["total_requests"] = self._metrics.get("total_requests", 0) + 1

            p_tok = 0
            c_tok = 0
            t_tok = 0
            if hasattr(response, "usage") and response.usage:
                p_tok = getattr(response.usage, "prompt_tokens", 0) or 0
                c_tok = getattr(response.usage, "completion_tokens", 0) or 0
                t_tok = getattr(response.usage, "total_tokens", 0) or (p_tok + c_tok)

            self._metrics["total_tokens"] = self._metrics.get("total_tokens", 0) + t_tok
            self._metrics["last_request"] = {
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": t_tok,
                "duration_ms": duration_ms,
                "timestamp": now_iso,
            }

            if headers:
                def _get_h(k: str) -> str:
                    if hasattr(headers, "get"):
                        val = headers.get(k) or headers.get(k.lower())
                        return str(val).strip() if val is not None else ""
                    return ""

                rem_t_str = _get_h("x-ratelimit-remaining-tokens")
                lim_t_str = _get_h("x-ratelimit-limit-tokens")
                rem_r_str = _get_h("x-ratelimit-remaining-requests")
                lim_r_str = _get_h("x-ratelimit-limit-requests")
                rst_t_str = _get_h("x-ratelimit-reset-tokens")
                rst_r_str = _get_h("x-ratelimit-reset-requests")

                rem_t = int(rem_t_str) if rem_t_str.isdigit() else self._metrics["rate_limits"]["remaining_tokens"]
                lim_t = int(lim_t_str) if lim_t_str.isdigit() else self._metrics["rate_limits"]["limit_tokens"]
                rem_r = int(rem_r_str) if rem_r_str.isdigit() else self._metrics["rate_limits"]["remaining_requests"]
                lim_r = int(lim_r_str) if lim_r_str.isdigit() else self._metrics["rate_limits"]["limit_requests"]

                used_pct = 0.0
                if lim_t > 0:
                    used_pct = round(max(0.0, min(100.0, (lim_t - rem_t) / lim_t * 100)), 1)

                self._metrics["rate_limits"] = {
                    "remaining_tokens": rem_t,
                    "limit_tokens": lim_t,
                    "used_tokens_pct": used_pct,
                    "remaining_requests": rem_r,
                    "limit_requests": lim_r,
                    "reset_tokens": rst_t_str or "0s",
                    "reset_requests": rst_r_str or "0s",
                }

            cascade = self._metrics.setdefault("cascade_status", {})
            for m_key in cascade:
                if m_key == model_name:
                    cascade[m_key]["state"] = "active"
                elif cascade[m_key].get("state") != "rate_limited":
                    cascade[m_key]["state"] = "standby"
        except Exception as err:
            logger.warning("AI metrikalarini yangilashda ogohlantirish: %s", err)

    def _record_model_rate_limited(self, model_name: str, error_msg: str = "") -> None:
        """Model limitga uchraganida uning holatini yangilaydi."""
        try:
            cascade = self._metrics.setdefault("cascade_status", {})
            if model_name in cascade:
                cascade[model_name]["state"] = "rate_limited"
                cascade[model_name]["last_error"] = str(error_msg)[:120]
        except Exception:
            pass

    def _record_gemini_metrics(self, prompt_len: int, completion_len: int, duration_ms: int = 0) -> None:
        """Google Gemini zaxira tizimi ishlaganda metrikalarni yangilaydi."""
        try:
            self._metrics["last_provider"] = "Google Gemini"
            self._metrics["active_model"] = "Google Gemini"
            self._metrics["last_model"] = config.gemini_model
            now_iso = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
            self._metrics["last_updated"] = now_iso
            self._metrics["total_requests"] = self._metrics.get("total_requests", 0) + 1

            p_tok = int(prompt_len / 3.5)
            c_tok = int(completion_len / 3.5)
            t_tok = p_tok + c_tok
            self._metrics["total_tokens"] = self._metrics.get("total_tokens", 0) + t_tok
            self._metrics["last_request"] = {
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": t_tok,
                "duration_ms": duration_ms,
                "timestamp": now_iso,
            }
            cascade = self._metrics.setdefault("cascade_status", {})
            if "Google Gemini" in cascade:
                cascade["Google Gemini"]["state"] = "active"
        except Exception as err:
            logger.warning("Gemini metrikalarini yangilashda ogohlantirish: %s", err)

    def get_metrics(self) -> dict[str, Any]:
        """Tizimning joriy AI modeli, TPM/RPM limitlari va so'rovlar sarfi statistikasini qaytaradi."""
        return {
            "ok": True,
            "active_model": self._metrics.get("active_model", config.groq_model),
            "last_provider": self._metrics.get("last_provider", "Groq"),
            "last_model": self._metrics.get("last_model", config.groq_model),
            "last_updated": self._metrics.get("last_updated"),
            "total_requests": self._metrics.get("total_requests", 0),
            "total_tokens": self._metrics.get("total_tokens", 0),
            "last_request": self._metrics.get("last_request", {}),
            "rate_limits": self._metrics.get("rate_limits", {}),
            "cascade_status": self._metrics.get("cascade_status", {}),
            "available_groq_keys": len(self._groq_clients),
        }

    async def _call_groq_with_metrics(
        self,
        client: Any,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Groq API so'rovini bajaradi va avtomatik metrikalarni yig'adi."""
        t0 = time.time()
        if hasattr(client.chat.completions, "with_raw_response"):
            raw_resp = await asyncio.wait_for(
                client.chat.completions.with_raw_response.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=18.0,
            )
            duration_ms = int((time.time() - t0) * 1000)
            parse_res = raw_resp.parse()
            if inspect.isawaitable(parse_res):
                response = await parse_res
            else:
                response = parse_res
            self._record_groq_metrics(model_name, response, headers=raw_resp.headers, duration_ms=duration_ms)
            return response
        else:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=18.0,
            )
            duration_ms = int((time.time() - t0) * 1000)
            self._record_groq_metrics(model_name, response, headers=None, duration_ms=duration_ms)
            return response

    def _setup_clients(self) -> None:
        """Mavjud provayderlarni aniqlaydi va kalitlar zaxirasini sozlaydi."""
        # 1. Groq kalitlarini ulash (Multi-key pool)
        keys = config.groq_api_keys or ([config.groq_api_key] if config.groq_api_key else [])
        self._groq_clients = []

        if keys:
            try:
                from groq import AsyncGroq
                for k in keys:
                    if k:
                        self._groq_clients.append(AsyncGroq(api_key=k, timeout=15.0, max_retries=1))
                logger.info(
                    "⚡ Groq AI muvaffaqiyatli ulandi (%d ta API kalit, Asosiy model: %s, Vision: %s)",
                    len(self._groq_clients),
                    config.groq_model,
                    config.groq_vision_model,
                )
            except Exception as e:
                logger.error("Groq mijozlarini yaratishda xatolik: %s", e)

        # 2. Google Gemini zaxira mijozini sozlash
        if config.gemini_api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=config.gemini_api_key)
                logger.info("Google Gemini ulandi.")
            except Exception:
                pass

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        """Xabarlar to'plamining taxminiy tokenlar sonini hisoblaydi (1 token ~ 3.5 belgi)."""
        total_chars = 0
        for m in messages:
            c = m.get("content", "")
            if isinstance(c, str):
                total_chars += len(c)
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])
        return int(total_chars / 3.5)

    async def _generate_with_groq_pod(
        self,
        c_gen,
        c_rev,
        c_syn,
        messages: list[dict],
        effective_prompt: str,
        sys_prompt: str,
        is_admin_mode: bool,
        model_name: str | None = None,
    ) -> str:
        """
        3 talik komanda (Pod Klaster) orqali chuqur tahlil qilingan xatosiz javob generatsiya qilish:
        1-Agent: Draft / Coder (Dastlabki yechim)
        2-Agent: Senior Reviewer (Xatolik va kamchiliklarni sinchkovlik bilan tekshirish)
        3-Agent: Master Mentor (Yakuniy mukammal, toza, 100% to'g'ri javobni sayqallash)
        """
        target_model = model_name or config.groq_model
        # 1. Generator
        calc_max_tokens = 1000 if "20b" in target_model.lower() else (2000 if is_admin_mode else 1500)
        res_gen = await self._call_groq_with_metrics(
            c_gen,
            model_name=target_model,
            messages=messages,
            temperature=0.6 if is_admin_mode else 0.4,
            max_tokens=calc_max_tokens,
        )
        draft = res_gen.choices[0].message.content.strip()

        # Agar javobda Telegram ACTION buyrug'i bo'lsa (qidirish, topish va h.k.), darhol qaytarish
        if "<<<ACTION:" in draft:
            return draft

        # Agar qisqa javob bo'lsa yoki salomlashuv bo'lsa, ortiqcha cho'zmasdan qaytarish
        if len(draft.split()) < 30:
            return draft

        # 2. Reviewer
        try:
            if is_admin_mode:
                rev_prompt = (
                    f"Siz CoddyCamp IT akademiyasining Katta Texnik Maslahatchisi va Senior Co-Pilot tahlilchisisiz.\n"
                    f"Mentor (Nuriddin aka) so'rovi: «{effective_prompt[:800]}»\n\n"
                    f"Taklif qilingan dastlabki yechim:\n```\n{draft[:2000]}\n```\n\n"
                    f"Vazifangiz: Ushbu yechimni sinchiklab tekshiring:\n"
                    f"1. Mentor savoliga to'laqonli, eng to'g'ri, chuqur va amaliy foydali javob berilganmi?\n"
                    f"2. Agar dasturlash kodi bo'lsa, sintaksis yoki mantiqiy xatolar bormi?\n"
                    f"3. Yechimni qanday qilib yanada mukammal qilish mumkin? Qisqa punktlarda ayting (hammasi a'lo bo'lsa, 'HAMMASI TO'G'RI' deb yozing)."
                )
                rev_sys = "Siz Senior Co-Pilot va Katta Texnik Maslahatchisiz. Mentorga berilayotgan tahlil sifatini oshirasiz."
            else:
                rev_prompt = (
                    f"Siz CoddyCamp IT akademiyasining Senior Code Reviewer mutaxassisisiz.\n"
                    f"Foydalanuvchi so'rovi: «{effective_prompt[:800]}»\n\n"
                    f"Dasturchi taklif qilgan dastlabki yechim:\n```\n{draft[:2000]}\n```\n\n"
                    f"Vazifangiz: Ushbu yechimni sinchiklab tekshiring:\n"
                    f"1. Kodda sintaksis, mantiqiy xatolar yoki cheksiz sikllar (infinite loops) bormi?\n"
                    f"2. Savolga to'liq, to'g'ri va eng maqbul yo'l bilan javob berilganmi?\n"
                    f"3. Nimalarni to'g'rilash yoki yaxshilash kerak? Qisqa punktlarda ayting (agar hammasi mukammal bo'lsa, 'KOD TO'G'RI' deb yozing)."
                )
                rev_sys = "Siz Senior Code Reviewer mutaxassisisiz. Kod xatolarini tekshirasiz."
            res_rev = await asyncio.wait_for(
                c_rev.chat.completions.create(
                    model=target_model,
                    messages=[
                        {"role": "system", "content": rev_sys},
                        {"role": "user", "content": rev_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=800,
                ),
                timeout=12.0,
            )
            review = res_rev.choices[0].message.content.strip()
        except Exception as rev_err:
            logger.debug("Reviewer qadamida ogohlantirish (draft qaytariladi): %s", rev_err)
            return draft

        # 3. Master Mentor Synthesizer
        try:
            syn_messages = [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{effective_prompt}\n\n"
                        f"[Ichki tahlil - Dastlabki yechim]:\n{draft}\n\n"
                        f"[Ichki tahlil - Senior Reviewer xulosasi]:\n{review}\n\n"
                        f"Ko'rsatma: Ikkala tahlilni birlashtirib, foydalanuvchiga eng mukammal, toza, 100% to'g'ri va samimiy yakuniy javobni taqdim eting. "
                        f"Ichki tahlil jarayonini (review so'zlarini) ko'rsatmasdan, to'g'ridan-to'g'ri tayyor mukammal javobni bering."
                    ),
                },
            ]
            res_syn = await self._call_groq_with_metrics(
                c_syn,
                model_name=target_model,
                messages=syn_messages,
                temperature=0.5 if is_admin_mode else 0.3,
                max_tokens=3000 if is_admin_mode else 2000,
            )
            final_reply = res_syn.choices[0].message.content.strip()
            return final_reply if final_reply else draft
        except Exception as syn_err:
            logger.debug("Synthesizer qadamida ogohlantirish (draft qaytariladi): %s", syn_err)
            return draft

    async def _generate_with_groq(
        self,
        chat_id: int,
        effective_prompt: str,
        image_bytes: bytes | None = None,
        is_admin_mode: bool = False,
    ) -> str:
        history = memory_service.get_history(chat_id)
        if image_bytes:
            opt_image = optimize_image_for_vision(image_bytes, max_dim=960, quality=80)
            img_b64 = base64.b64encode(opt_image).decode("utf-8")
            prompt_text = (
                effective_prompt
                if effective_prompt
                else "Ushbu rasm/skrinshotdagi LMS vazifasi yoki kod xatoligini tahlil qilib, to'g'ri yechim va yo'nalish ber."
            )
            # Vision uchun ixcham tizim prompti (Groq 7000 ITPM limitiga sig'ish uchun)
            vision_sys = (
                "Siz CoddyCamp IT dasturlash mentori AIsiz. "
                "Foydalanuvchi yuborgan rasm, kod xatosi yoki LMS topshirig'ini OCR orqali o'qib, "
                "aniq, qisqa va tushunarli yechim bering."
            )
            messages = [{"role": "system", "content": vision_sys}]
            for msg in history[-2:]:
                role = "user" if msg.role == "user" else "assistant"
                messages.append({"role": role, "content": msg.content[:300]})

            user_content = [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                },
            ]
            messages.append({"role": "user", "content": user_content})
            model_to_use = config.groq_vision_model
        else:
            sys_prompt = self._build_system_prompt(is_admin_mode)
            messages = [{"role": "system", "content": sys_prompt}]

            prev_assistant = ""
            recent_history = history[-6:] if not is_admin_mode else history[-8:]
            for msg in recent_history:
                content_clean = msg.content.strip()
                if msg.role == "model":
                    # Agar ketma-ket bir xil assistant javobi bo'lsa, takrorlamaslik
                    if content_clean == prev_assistant:
                        continue
                    prev_assistant = content_clean
                role = "user" if msg.role == "user" else "assistant"
                # Tokenlar hajmi 413 limitiga urilmasligi uchun eski xabarlarni ixchamlashtirish
                compact_content = content_clean[:600] + ("..." if len(content_clean) > 600 else "")
                messages.append({"role": role, "content": compact_content})

            messages.append({"role": "user", "content": effective_prompt})

        # 3 talik komanda (Pod Klaster) orqali murakkab savollarga xatosiz javob berish
        is_complex = (
            not image_bytes
            and len(self._groq_clients) >= 3
            and (
                any(k in effective_prompt.lower() for k in (
                    "kod", "xato", "error", "exception", "yoz", "tuz", "funksiya", "function",
                    "def ", "class ", "for ", "if ", "while", "import ", "tushuntir", "qanday",
                    "masala", "vazifa", "lms", "python", "javascript", "sql", "bug", "yordam",
                    "ishlamayapti", "chiqmayapti", "tekshir", "tahlil"
                ))
                or len(effective_prompt.split()) >= 6
            )
        )

        if image_bytes:
            candidate_models = [config.groq_vision_model]
        else:
            candidate_models = []
            # Yuqori TPM va 128k kontekstli barqaror modellar
            preferred = [
                config.groq_model,
                "qwen/qwen3.8-27b",
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
            ]
            for m in preferred:
                if m and m not in candidate_models:
                    candidate_models.append(m)

        last_error = None

        # -----------------------------------------------------------
        # Tokenlar byudjetini oldindan hisoblash va boshqarish (Token Budgeting):
        # -----------------------------------------------------------
        active_messages = list(messages)
        est_tokens = self._estimate_tokens(active_messages)

        # 1. Proactive Halving: Agar so'rov 4,500 tokendan oshsa, limitga yetmasdan oldin xotirani 2 ga bo'lish
        if est_tokens > 4500 and len(active_messages) > 3:
            logger.info("⚡ So'rov hajmi katta (%d token). Xotira 2 ga bo'linib, eng muhim qismlarga qisqartirildi.", est_tokens)
            # Tizim prompti (messages[0]) + oxirgi 2 ta xabar + joriy so'rov (messages[-1])
            active_messages = [active_messages[0]] + active_messages[-3:]
            est_tokens = self._estimate_tokens(active_messages)

        # Kaskadli zaxira modellar bo'yicha ketma-ket urinish:
        for model_to_use in candidate_models:
            # Kichik 20b modelning 8k TPM limitiga urilmaslik uchun: agar so'rov 4,000 tokendan katta bo'lsa,
            # uni darhol 128k lik katta modellarga yo'naltirish
            if "20b" in model_to_use.lower() and est_tokens > 4000:
                logger.info("Model [%s] 8k TPM limitiga to'qnashmasligi uchun o'tkazib yuborildi (%d token).", model_to_use, est_tokens)
                continue

            # 1. 3 talik komanda (Pod Klaster) orqali ushbu modelda sinash
            if is_complex:
                idx1 = self._groq_idx % len(self._groq_clients)
                idx2 = (self._groq_idx + 1) % len(self._groq_clients)
                idx3 = (self._groq_idx + 2) % len(self._groq_clients)
                self._groq_idx = (self._groq_idx + 3) % len(self._groq_clients)

                team_num = (idx1 // 3) + 1
                logger.info(
                    "⚡ 3 talik komanda (Pod #%d) ishga tushirildi: Model [%s], [Kalit %d, %d, %d]",
                    team_num, model_to_use, idx1 + 1, idx2 + 1, idx3 + 1,
                )
                try:
                    pod_result = await self._generate_with_groq_pod(
                        self._groq_clients[idx1],
                        self._groq_clients[idx2],
                        self._groq_clients[idx3],
                        active_messages,
                        effective_prompt,
                        sys_prompt,
                        is_admin_mode,
                        model_name=model_to_use,
                    )
                    if pod_result and pod_result.strip():
                        return pod_result
                except Exception as pod_err:
                    logger.warning("Pod klasterida xatolik (%s): %s, bitta kalitli rejimga o'tilmoqda", model_to_use, pod_err)
                    last_error = pod_err

            # 2. Ushbu model bo'yicha kalitlarni ketma-ket tekshirish (maksimal 3 ta kalit sinovi)
            model_success = False
            calc_max_tokens = 1000 if "20b" in model_to_use.lower() else (2500 if is_admin_mode else 1800)
            max_attempts = min(3, len(self._groq_clients))
            for _ in range(max_attempts):
                client = self._groq_clients[self._groq_idx]
                self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
                try:
                    response = await self._call_groq_with_metrics(
                        client,
                        model_name=model_to_use,
                        messages=active_messages,
                        temperature=0.6 if is_admin_mode else 0.4,
                        max_tokens=calc_max_tokens,
                    )
                    msg_obj = response.choices[0].message
                    content_str = (getattr(msg_obj, "content", "") or "").strip()
                    if not content_str and hasattr(msg_obj, "reasoning") and msg_obj.reasoning:
                        content_str = msg_obj.reasoning.strip()
                    if content_str:
                        return content_str
                except Exception as e:
                    logger.warning("Groq kalitida xatolik (model: %s): %s", model_to_use, e)
                    last_error = e
                    if "429" in str(e) or "rate_limit_exceeded" in str(e) or "413" in str(e):
                        self._record_model_rate_limited(model_to_use, str(e))

                    # Reactive Halving: Agar 413 yoki token limiti oshishi yuz bersa,
                    # xotirani ikkiga bo'lib (faqat oxirgi savol qoldirilib) va max_tokens ni 2 ga qisqartirib darhol qayta urinish
                    if ("413" in str(e) or "rate_limit_exceeded" in str(e)) and len(active_messages) > 2:
                        logger.warning("⚠️ 413 token limiti! Xotira 2 ga bo'linib (faqat joriy so'rov) qayta urinilmoqda...")
                        active_messages = [active_messages[0], active_messages[-1]]
                        calc_max_tokens = max(512, calc_max_tokens // 2)
                        try:
                            retry_resp = await self._call_groq_with_metrics(
                                client,
                                model_name=model_to_use,
                                messages=active_messages,
                                temperature=0.6 if is_admin_mode else 0.4,
                                max_tokens=calc_max_tokens,
                            )
                            msg_obj = retry_resp.choices[0].message
                            content_str = (getattr(msg_obj, "content", "") or "").strip()
                            if not content_str and hasattr(msg_obj, "reasoning") and msg_obj.reasoning:
                                content_str = msg_obj.reasoning.strip()
                            if content_str:
                                return content_str
                        except Exception as r_err:
                            logger.warning("Qisqartirilgan xotira bilan qayta urinishda ham xatolik: %s", r_err)
                            last_error = r_err

            # Agar bu modelda barcha kalitlar muvaffaqiyatsiz bo'lsa (masalan limit to'lsa)
            logger.warning("⚠️ Model [%s] bo'yicha limit yoki xatolik yuz berdi. Keyingi zaxira modelga o'tilmoqda...", model_to_use)

        # Agar rasm hajmi tufayli 413 (rate_limit_exceeded) bo'lsa, yanada ixcham (640px) qilib qayta urinib ko'rish
        if image_bytes and last_error and ("rate_limit_exceeded" in str(last_error) or "413" in str(last_error)):
            logger.warning("Rasm hajmi oshdi (413), 640px ga yanada kichraytirib qayta urinilmoqda...")
            try:
                tiny_image = optimize_image_for_vision(image_bytes, max_dim=640, quality=65)
                tiny_b64 = base64.b64encode(tiny_image).decode("utf-8")
                messages[-1]["content"][1]["image_url"]["url"] = f"data:image/jpeg;base64,{tiny_b64}"
                for client in self._groq_clients:
                    try:
                        response = await client.chat.completions.create(
                            model=config.groq_vision_model,
                            messages=messages,
                            temperature=0.3,
                            max_tokens=1024,
                        )
                        return response.choices[0].message.content.strip()
                    except Exception:
                        continue
            except Exception as retry_err:
                logger.warning("Qayta urinishda xatolik: %s", retry_err)

        if last_error:
            raise last_error
        return "Javob olinmadi."

    def _build_system_prompt(self, is_admin_mode: bool) -> str:
        """Tizim promptini bilimlar bazasi va tanlangan mentorlik uslubi (persona) bilan boyitadi."""
        sys_prompt = ADMIN_SYSTEM_PROMPT if is_admin_mode else SYSTEM_PROMPT
        knowledge_context = memory_service.get_knowledge_context()
        if knowledge_context:
            sys_prompt = f"{sys_prompt}\n\n{knowledge_context}"

        if not is_admin_mode:
            # 1. O'quv markazining rasmiy o'quv dasturi va mavzular chegarasi (Curriculum Boundary)
            curriculum_topics = memory_service.get_curriculum_topics()
            if curriculum_topics:
                topics_str = ", ".join(curriculum_topics)
                curriculum_block = (
                    f"# CODDYCAMP RASMIY O'QUV DASTURI VA TEXNOLOGIYALAR STEKI (CURRICULUM BOUNDARY):\n"
                    f"Bizning o'quv markazimizda FAQAT quyidagi tasdiqlangan texnologiyalar va yo'nalishlar o'qitiladi:\n"
                    f"[{topics_str}]\n\n"
                    f"QAT'IY QOIDALAR (O'QUVCHILAR UCHUN):\n"
                    f"1. O'quvchi umumiy dasturlash mavzusi yoki tushunchasi haqida so'rasa (masalan: 'for sikli', 'while', 'massiv/array', 'funksiya', 'backend', 'ma\\'lumotlar bazasi'), "
                    f"uni DOIMO va so'zsiz markazimizning rasmiy steki — JavaScript / React / Node.js / Express / MongoDB bo'yicha tushuntiring!\n"
                    f"2. Boshqa markazda o'qitilmaydigan tillarga (masalan: Python, C++, C#, PHP, Java, Ruby, Go) o'zingizdan o'zingiz aslo chalg'imang va misollarni ularda keltirmang.\n"
                    f"3. Agar o'quvchi markazda o'tilmaydigan boshqa til haqida ataylab so'rasa (masalan: 'C++ da qanday bo'ladi?'), "
                    f"xushmuomalalik bilan markazimizda zamonaviy Web dasturlash (Frontend: React/Next.js, Backend: Node.js/Express, Dizayn: Figma) hamda yoshlar uchun Scratch/Pictoblox o'qitilishini eslatib, "
                    f"asosiy e'tiborni markazimiz o'quv dasturidagi texnologiyalarga qaratishni tavsiya qiling."
                )
                sys_prompt = f"{sys_prompt}\n\n{curriculum_block}"

            persona = memory_service.get_setting("ai_persona", "socratic")
            code_mode = memory_service.get_setting("ai_code_mode", "full_code")
            extras = []
            if persona == "socratic":
                extras.append("• METODIKA: Sokratik ta'lim uslubi. O'quvchiga darhol tayyor kod yechimini bermasdan, avvalo uning xatosini tushuntirib, to'g'ri fikrlashga va yechimni o'zi topishiga yo'l ko'rsating.")
            elif persona == "tech_lead":
                extras.append("• METODIKA: Tech Lead uslubi. O'ta aniq, professional va to'g'ridan-to'g'ri texnik yechim va sintaksisni bering.")
            elif persona == "friendly":
                extras.append("• METODIKA: Do'stona va sabrli mentor uslubi. Sodda va iliq tilda, yangi boshlovchi ham oson tushunadigan qilib bosqichma-bosqich tushuntiring.")

            if code_mode == "hints_only":
                extras.append("• KOD REJIMI: Diqqat, to'liq tayyor kod yechimini bermang! Faqat qaysi qatorda yoki mantiqda xatolik borligini tushuntirib, maslahat (hint) bering.")
            elif code_mode == "full_code":
                extras.append("• KOD REJIMI: Koddagi xatoni tushuntirib, to'g'ri va ishlaydigan to'liq kod variantini taqdim eting.")

            if extras:
                sys_prompt = f"{sys_prompt}\n\n# JORIY USLUB VA MENTOR KO'RSATMALARI:\n" + "\n".join(extras)

        return sys_prompt

    def _generate_with_genai(self, prompt: str, history_context: str, is_admin_mode: bool = False) -> str:
        """Google GenAI orqali javob generatsiya qilish (fallback)."""
        from google.genai import types

        full_content = prompt
        if history_context:
            full_content = f"Avvalgi suhbat konteksti:\n{history_context}\n\nFoydalanuvchining yangi xabari:\n{prompt}"

        sys_prompt = self._build_system_prompt(is_admin_mode)
        response = self._gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=full_content,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.6,
            ),
        )
        return response.text.strip() if response.text else ""

    async def generate_reply(
        self,
        chat_id: int,
        user_message: str,
        reply_to_context: str | None = None,
        image_bytes: bytes | None = None,
        file_name: str | None = None,
        file_text: str | None = None,
        is_admin_mode: bool | None = None,
    ) -> AIResult:
        """
        Xabarni tahlil qilib AI javobini qaytaradi (matn, fayl yoki rasm/skrinshot bilan).
        """
        if not self._groq_clients and not self._gemini_client:
            self._setup_clients()
            if not self._groq_clients and not self._gemini_client:
                return AIResult("⚠️ **Xatolik:** Hech qanday AI provayderi sozlanmagan. Iltimos `.env` faylini tekshiring.")

        # Vazifalar (Admin) guruhi yoki Mentor ekanini aniqlash
        if is_admin_mode is None:
            is_admin_mode = is_escalation_chat(chat_id) or (chat_id in (config.mentor_user_id, 8105823872))

        # Standart xatoliklarga (FAQ) 0.01 soniyada tezkor javob berish
        if not is_admin_mode and not file_text and not image_bytes:
            fast_faq = check_fast_faq(user_message)
            if fast_faq:
                logger.info("Fast FAQ mos keldi [%s], tezkor javob berildi.", chat_id)
                memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
                memory_service.add_message(chat_id=chat_id, role="model", content=fast_faq)
                return AIResult(fast_faq)

        # Javob berilayotgan kontekst
        effective_prompt = user_message
        if file_name and file_text:
            effective_prompt = f"[Yuklangan fayl: {file_name}]\n```\n{file_text[:6000]}\n```\n\n{effective_prompt}"

        if reply_to_context:
            effective_prompt = f"[Javob berilayotgan xabar: \"{reply_to_context}\"]\n{effective_prompt}"

        # Web Search & Rasmiy IT Dokumentatsiyalardan qidiruv (Real-time docs)
        web_search_enabled = memory_service.get_setting("web_search_enabled", "true").lower() == "true"
        if web_search_enabled and not image_bytes and user_message:
            clean_text = user_message.lower()
            from services.search_service import get_web_search_context, is_programming_query

            should_search = False
            if is_admin_mode:
                # Mentor (Vazifalar): mutlaq erkin, har qanday mavzuda
                search_triggers = [
                    "qidir", "search", "internet", "google", "top", "yangilik",
                    "versiya", "nima yangi", "ob-havo", "kurs", "dokumentatsiya",
                    "docs", "kutubxona", "yangi funksiya", "qanday ishlaydi"
                ]
                if any(tr in clean_text for tr in search_triggers) or (len(user_message.split()) >= 3 and "?" in user_message):
                    should_search = True
            else:
                # O'quvchilar: Chegaradan chiqmasdan - FAQAT dasturlash/IT bo'lsa
                if is_programming_query(user_message):
                    student_triggers = [
                        "kutubxona", "library", "versiya", "version", "yangi",
                        "dokumentatsiya", "docs", "documentation", "qanday ishlaydi",
                        "error", "xatolik", "o'rnatish", "install", "pip", "npm",
                        "qanday qilsa", "metod", "funksiya", "nimaga kerak"
                    ]
                    if any(st in clean_text for st in student_triggers):
                        should_search = True

            if should_search:
                try:
                    search_ctx = await get_web_search_context(user_message, is_admin=is_admin_mode)
                    if search_ctx:
                        effective_prompt = f"{search_ctx}\n\n[Foydalanuvchi so'rovi]:\n{effective_prompt}"
                        logger.info("Web Search natijalari AI promptiga qo'shildi [%s]", chat_id)
                except Exception as s_err:
                    logger.warning("Web search qo'shishda ogohlantirish: %s", s_err)

        try:
            answer = None
            # 1-ustuvorlik: Groq (Multi-key Cluster)
            if self._groq_clients:
                try:
                    answer = await asyncio.wait_for(
                        self._generate_with_groq(
                            chat_id, effective_prompt, image_bytes=image_bytes, is_admin_mode=is_admin_mode
                        ),
                        timeout=22.0,
                    )
                except Exception as groq_err:
                    logger.warning(
                        "⚠️ Groq klasterida xatolik yoki limit oshdi (%s). Google Gemini zaxira tizimiga o'tilmoqda...",
                        groq_err,
                    )
                    answer = None

            # 2-ustuvorlik: Google Gemini (Zaxira tizim - 1 million token limit)
            if not answer and self._gemini_client:
                try:
                    logger.info("⚡ Google Gemini zaxira tizimi ishga tushirildi...")
                    history = memory_service.get_history(chat_id)
                    recent_history = history[-6:] if not is_admin_mode else history[-8:]
                    history_lines = [
                        f"{'Foydalanuvchi' if m.role == 'user' else 'AI'}: {m.content[:500]}"
                        for m in recent_history
                    ]
                    history_context = "\n".join(history_lines)

                    loop = asyncio.get_running_loop()
                    t_gem = time.time()
                    answer = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self._generate_with_genai, effective_prompt, history_context, is_admin_mode
                        ),
                        timeout=15.0,
                    )
                    d_ms = int((time.time() - t_gem) * 1000)
                    self._record_gemini_metrics(
                        len(effective_prompt) + len(history_context),
                        len(answer) if answer else 0,
                        duration_ms=d_ms,
                    )
                    logger.info("✅ Google Gemini zaxira tizimi orqali muvaffaqiyatli javob olindi.")
                except Exception as gemini_err:
                    logger.error("Gemini zaxira tizimida ham xatolik: %s", gemini_err)

            if not answer:
                answer = "Kechirasiz, ushbu xabarga aniq javob shakllantirib bo'lmadi."

            # Eskalyatsiya blokini ajratish
            escalation_info = None
            match = ESCALATE_PATTERN.search(answer)
            if match:
                escalation_info = match.group(1).strip()
                answer = ESCALATE_PATTERN.sub("", answer).strip()

            # Maxfiy ma'lumotlarni tozalash (Data Leak Prevention)
            answer = redact_sensitive_data(answer)
            if escalation_info:
                escalation_info = redact_sensitive_data(escalation_info)

            # Faqatgina bir xil kunda, davom etayotgan suhbatda va foydalanuvchi o'zi salom bermagan bo'lsa:
            # Qayta-qayta sun'iy "Assalomu alaykum" yoki "Salom" deb salom berishni tozalash.
            # Agar bu yangi kun (ertasi kuni) yoki oradan 6+ soat o'tgan yangi sessiya bo'lsa, salomlashish tabiiy va to'g'ri,
            # shuning uchun kunning birinchi xabarida salom toza saqlab qolinadi!
            is_new_day = memory_service.is_new_session_or_day(chat_id)
            if not is_new_day and not re.search(r"\b(?:salom|assalom|qalaysiz|yaxshimisiz|privet|здравств|привет)", user_message, re.I):
                cleaned_start = re.sub(
                    r"^(?:assalomu\s+alaykum[!.,]?\s*(?:yaxshimisiz[\?!.,]?\s*)?|salom[!.,]?\s*|здравствуйте[!.,]?\s*|привет[!.,]?\s*)",
                    "",
                    answer,
                    flags=re.I,
                ).strip()
                if cleaned_start:
                    answer = cleaned_start[0].upper() + cleaned_start[1:]

            # Xotiraga tozalangan javobni saqlash
            memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
            memory_service.add_message(chat_id=chat_id, role="model", content=answer)

            return AIResult(answer, escalation=escalation_info)

        except Exception as e:
            logger.exception("AI so'rovida xatolik yuz berdi: %s", e)
            if is_admin_mode:
                return AIResult(f"⚠️ **AI xizmatida xatolik:** {str(e)}")
            if is_russian_text(user_message):
                return AIResult("⚠️ Извините, в данный момент серверы ИИ временно перегружены. Пожалуйста, повторите попытку через минуту.")
            return AIResult("⚠️ Kechirasiz, ayni paytda AI serverlarida yuklama yuqori. Iltimos, bir ozdan so'ng qayta urinib ko'ring.")

    async def explain_topic(self, topic: str) -> str:
        """
        Dars mavzusini hayotiy misol (analogiya), kod va mini-mashq bilan tushuntirib beradi.
        """
        prompt = (
            f"Siz CoddyCamp dasturlash akademiyasi Katta Mentorisiz.\n"
            f"O'quvchiga quyidagi dasturlash mavzusini eng qiziqarli va tushunarli uslubda tushuntiring:\n"
            f"Mavzu: \"{topic}\"\n\n"
            "Javob formati aynan quyidagicha bo'lsin:\n"
            f"📚 **Mavzu: {topic.title()}**\n\n"
            "💡 **Hayotiy o'xshatish (Analogiya):** (Oddiy, o'quvchi tushunadigan qiziqarli hayotiy o'xshatish, 2-3 jumla)\n\n"
            "💻 **Kod namunasi:**\n```python\n# 4-6 qatorli toza, izohli sodda kod\n```\n\n"
            "🎯 **O'quvchi uchun mini-mashq (Challenge):** (O'quvchi darhol mustaqil yozib ko'rishi uchun 1 ta amaliy topshiriq)\n\n"
            "Javobni ortiqcha cho'zmasdan, chiroyli va lo'nda formatda yozing."
        )

        if not self._groq_clients:
            self._setup_clients()

        models_to_try = []
        for m in [config.groq_model, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            for _ in range(len(self._groq_clients)):
                client = self._groq_clients[self._groq_idx]
                self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.4,
                        max_tokens=1200,
                    )
                    ans = response.choices[0].message.content.strip()
                    return redact_sensitive_data(ans)
                except Exception as e:
                    logger.warning("Mavzu tushuntirishda xatolik (%s): %s", model_name, e)

        return "⚠️ Mavzuni tushuntirishda xatolik yuz berdi. Iltimos qayta urinib ko'ring."

    async def analyze_absence_report(
        self,
        message_text: str,
        sender_name: str = "",
        common_groups: list[str] | None = None,
    ) -> dict[str, str]:
        """
        O'quvchining darsga kelolmasligi / dars qoldirishi haqidagi xabarini
        AI orqali tahlil qilib, toza ma'lumotlar strukturasiga ajratadi.
        """
        groups_str = ", ".join(common_groups) if common_groups else "Aniqlanmagan"
        s_profile_name = sender_name if sender_name else "Nomalum"
        prompt = (
            f"Siz ta'lim markazi (CoddyCamp) davomat nazoratchisisiz.\n"
            f"Quyidagi xabarni o'quvchi yuborgan:\n"
            f"Telegram profili: {s_profile_name}\n"
            f"A'zo bo'lgan ehtimoliy guruhlari: {groups_str}\n"
            f"Xabar: \"{message_text}\"\n\n"
            "Vazifangiz xabarni tahlil qilib, FAQAT quyidagi JSON formatda javob berish:\n"
            "{\n"
            '  "student_name": "O\'quvchining ismi (agar xabarda ismi yozilgan bo\'lsa o\'sha, bo\'lmasa profil ismi)",\n'
            '  "group_name": "Guruh nomi (xabarda aytilgan yoki ehtimoliy guruhlar ro\'yxatidagi nom, topilmasa \'Aniqlanmadi\')",\n'
            '  "date_time": "Qachon darsga kelolmasligi yoki kechikishi (masalan: \'Bugun\', \'Ertaga\', \'1 soatga kech\')",\n'
            '  "reason": "Sababi lo\'nda va aniq (masalan: \'Mazasi yo\'qligi / kasallik\', \'Oilaviy sabab\', \'Tirbandlik\')"\n'
            "}\n"
            "DIQQAT: Faqat toza JSON formatida javob bering, kod bloki (```json) ham, ortiqcha so'z ham yozmang."
        )

        if not self._groq_clients:
            self._setup_clients()

        models_to_try = []
        for m in [config.groq_model, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            for _ in range(len(self._groq_clients)):
                client = self._groq_clients[self._groq_idx]
                self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
                try:
                    res = await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=300,
                    )
                    content = res.choices[0].message.content.strip()
                    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL).strip()
                    data = json.loads(clean_json)
                    return {
                        "student_name": str(data.get("student_name") or sender_name or "Noma'lum").strip(),
                        "group_name": str(data.get("group_name") or (common_groups[0] if common_groups else "Aniqlanmadi")).strip(),
                        "date_time": str(data.get("date_time") or "Bugun").strip(),
                        "reason": str(data.get("reason") or "Sababi keltirilmagan").strip(),
                    }
                except Exception as e:
                    logger.warning("Davomat tahlilida xatolik (%s): %s", model_name, e)

        # Fallback (AI ishlamasa xavfsiz regex/shablon tahlili)
        fallback_reason = "Mazasi yo'qligi / betoblik" if any(w in message_text.lower() for w in ("kasal", "maza", "tob", "заболел")) else "Darsga kela olmaslik"
        fallback_time = "Ertaga" if any(w in message_text.lower() for w in ("erta", "завтра")) else "Bugun"
        return {
            "student_name": sender_name or "Noma'lum",
            "group_name": common_groups[0] if common_groups else "Aniqlanmadi",
            "date_time": fallback_time,
            "reason": fallback_reason,
        }

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Groq Whisper (whisper-large-v3) orqali ovozli xabarni o'zbek/rus tilida matnga o'giradi.
        """
        if not self._groq_clients:
            self._setup_clients()
            if not self._groq_clients:
                raise RuntimeError("Ovozni tahlil qilish uchun Groq klasteri mavjud emas.")

        last_error = None
        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                transcription = await client.audio.transcriptions.create(
                    file=("voice.ogg", audio_bytes),
                    model="whisper-large-v3",
                    response_format="text",
                )
                text = str(transcription).strip()
                logger.info("Ovozli xabar matnga aylantirildi: %s", text[:80])
                return text
            except Exception as e:
                logger.warning("Groq Whisper'da xatolik, zaxira kalitga o'tilmoqda: %s", e)
                last_error = e

        if last_error:
            raise last_error
        return ""

    async def generate_mentor_report(self, questions: list[str]) -> str:
        """
        O'quvchilarning so'nggi savollari va xatolarini tahlil qilib, mentor uchun hisobot tayyorlaydi.
        """
        if not questions:
            return "ℹ️ Hozircha tahlil qilish uchun o'quvchilar savollari tarixi yetarli emas."

        questions_text = "\n".join([f"- {q}" for q in questions[:50]])
        prompt = (
            "Quyida CoddyCamp o'quvchilari tomonidan dasturlash bo'yicha berilgan so'nggi savollar va xatoliklar ro'yxati keltirilgan:\n\n"
            f"{questions_text}\n\n"
            "Siz CoddyCamp IT akademiyasi Katta Metodisti va Bosh Mentori sifatida ushbu savollarni chuqur tahlil qilib, dars beruvchi mentor (Nuriddin aka) uchun qisqa, lo'nda va nihoyatda foydali ANALITIK HISOBOT tayyorlang.\n\n"
            "Hisobot formati quyidagicha bo'lsin:\n"
            "📊 **CoddyCamp Mentor Analitikasi (O'quvchilar xatoliklari hisoboti)**\n\n"
            "1. 📌 **Eng ko'p qiynalgan mavzular (Top 3):** (qaysi mavzularda eng ko'p savol tushgan)\n"
            "2. ⚠️ **Asosiy xatoliklar (Common Bugs):** (o'quvchilar kodida eng ko'p uchragan xatolar)\n"
            "3. 💡 **Keyingi dars uchun tavsiya:** (mentor darsda aynan qaysi tushunchani chuqurroq tushuntirib, qanday amaliy mashq berishi kerak)\n\n"
            "Javobni professional, ixcham va tushunarli formatda bering."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=1500,
                )
                return redact_sensitive_data(response.choices[0].message.content.strip())
            except Exception as e:
                logger.warning("Mentor hisobotini tuzishda xatolik: %s", e)

        return "⚠️ Hisobotni shakllantirishda xatolik yuz berdi."

    async def parse_reminder_text(self, text: str, current_tashkent_time: str) -> dict | None:
        """
        O'zbek tilidagi eslatma matnidan vazifa va aniq YYYY-MM-DD HH:MM:SS vaqtini ajratib oladi.
        """
        # 1. Tezkor aqlli (nisbiy va aniq) sana va vaqt tahlili (0.0001s da aniqlash)
        smart = extract_smart_reminder(text, current_tashkent_time=current_tashkent_time)
        if smart:
            return smart

        prompt = (
            f"Hozirgi sana va vaqt (Toshkent vaqti): {current_tashkent_time}\n\n"
            f"Foydalanuvchi quyidagi eslatma so'rovini yozdi:\n\"{text}\"\n\n"
            "Vazifangiz: ushbu so'rovdan eslatma matnini (vazifani) va eslatish kerak bo'lgan aniq sana/vaqtni hisoblab chiqib, FAQAT quyidagi JSON formatida qaytaring:\n"
            "{\n"
            '  "reminder_text": "Vazifa mazmuni",\n'
            '  "remind_at": "YYYY-MM-DD HH:MM:SS"\n'
            "}\n"
            "Qoidalar:\n"
            "- 'remind_at' qiymati aniq 24 soatlik formatda (YYYY-MM-DD HH:MM:SS) bo'lishi shart.\n"
            "- Agar aniq sana kiritilsa (masalan: '25 09 2026', '25.09.2026', '25 sentyabr 15:00'), o'sha sana va soatni oling (masalan: '2026-09-25 15:00:00').\n"
            "- Agar soat ko'rsatilmagan bo'lsa, o'sha kun soat 10:00:00 ni oling.\n"
            "- Agar '30 daqiqadan keyin' desa, hozirgi vaqtga 30 daqiqa qo'shing.\n"
            "- Agar 'ertaga soat 10:00 da' desa, ertangi kun sanasi va 10:00:00 ni oling.\n"
            "- Agar 'bugun 18:30 da' desa, bugungi sana va 18:30:00 ni oling.\n"
            "- Agar vaqt aniq tushunarsiz bo'lsa, 'remind_at': null qiling.\n"
            "- FAQAT valid JSON qaytaring, boshqa hech qanday so'z yozmang."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=250,
                )
                raw_json = response.choices[0].message.content.strip()
                if "```" in raw_json:
                    raw_json = re.sub(r"```(?:json)?", "", raw_json).strip()
                start_idx = raw_json.find("{")
                end_idx = raw_json.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_json = raw_json[start_idx : end_idx + 1]
                try:
                    data = json.loads(raw_json)
                except Exception:
                    import ast
                    data = ast.literal_eval(raw_json)
                if isinstance(data, dict):
                    rem_text = data.get("reminder_text") or data.get("task")
                    rem_at = data.get("remind_at")
                    if rem_text and rem_at:
                        return {"reminder_text": str(rem_text), "remind_at": str(rem_at)}
            except Exception as e:
                logger.warning("Eslatma vaqtini tahlil qilishda xatolik: %s", e)

        return None

    async def analyze_github_link(self, github_url: str) -> str:
        """
        GitHub repozitoriy yoki fayl havolasini o'qib, professional Code-Review hisobotini tayyorlaydi.
        """
        import aiohttp
        match = re.search(r"github\.com/([^/\s?#]+)/([^/\s?#]+)", github_url)
        if not match:
            return "⚠️ Noto'g'ri GitHub havolasi. Masalan: `https://github.com/foydalanuvchi/loyiha`"

        owner = match.group(1)
        repo = match.group(2).rstrip(".git")

        headers = {
            "User-Agent": "coddyHelper-AI-Agent",
            "Accept": "application/vnd.github.v3+json",
        }

        repo_info = ""
        files_content = []

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                # 1. Repozitoriy ma'lumotlari
                repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
                async with session.get(repo_api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        repo_data = await resp.json()
                        desc = repo_data.get("description") or "Tavsif berilmagan"
                        lang = repo_data.get("language") or "Noma'lum"
                        repo_info = f"Loyiha: {owner}/{repo}\nAsosiy til: {lang}\nTavsif: {desc}\n"

                # 2. Repozitoriy fayllari ro'yxati
                contents_api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
                async with session.get(contents_api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        contents = await resp.json()
                        key_files = []
                        if isinstance(contents, list):
                            for item in contents:
                                name = item.get("name", "")
                                ext = Path(name).suffix.lower()
                                if ext in (
                                    ".py", ".js", ".ts", ".html",
                                    ".sql", ".java", ".cpp", ".c",
                                ) or name.lower() in ("readme.md", "app.py", "main.py"):
                                    key_files.append((name, item.get("download_url")))
                                if len(key_files) >= 4:
                                    break

                        # Fayllar kodini yuklab olish
                        for fname, d_url in key_files:
                            if d_url:
                                async with session.get(
                                    d_url, timeout=aiohttp.ClientTimeout(total=10)
                                ) as f_resp:
                                    if f_resp.status == 200:
                                        code_txt = await f_resp.text()
                                        files_content.append(f"--- Fayl: {fname} ---\n{code_txt[:3000]}")
        except Exception as net_err:
            logger.warning("GitHub API so'rovida xatolik: %s", net_err)

        if not files_content:
            files_summary = repo_info if repo_info else f"Loyiha: {owner}/{repo}"
        else:
            files_summary = f"{repo_info}\n" + "\n\n".join(files_content)

        prompt = (
            f"Quyida GitHub repozitoriysi ({owner}/{repo}) kodi va tuzilmasi keltirilgan:\n\n"
            f"{files_summary[:8000]}\n\n"
            "Siz Katta Dasturchi va CoddyCamp Mentori sifatida ushbu o'quvchi loyihasi bo'yicha professional CODE REVIEW tayyorlang.\n\n"
            "Hisobot formati quyidagicha bo'lsin:\n"
            f"🔍 **GitHub Code Review: {owner}/{repo}**\n\n"
            "⭐️ **Umumiy baho:** [1 dan 10 gacha ball]\n"
            "🧹 **Clean Code va PEP8 tahlili:** (kod tozaligi, o'zgaruvchi nomlari, arxitektura)\n"
            "🐛 **Aniqlangan xatolar / Kamchiliklar:** (mantiqiy xatolar, xavfsizlik, xatoliklarni ushlash)\n"
            "🚀 **Yaxshilash uchun tavsiyalar (Top 3):** (loyihani yaxshilash uchun aniq 3 ta maslahat)\n\n"
            "Javobni lo'nda, professional va o'quvchiga tushunarli tarzda bering."
        )

        if not self._groq_clients:
            self._setup_clients()

        for _ in range(len(self._groq_clients)):
            client = self._groq_clients[self._groq_idx]
            self._groq_idx = (self._groq_idx + 1) % len(self._groq_clients)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=1500,
                )
                return redact_sensitive_data(response.choices[0].message.content.strip())
            except Exception as e:
                logger.warning("GitHub tahlilida xatolik: %s", e)

        return "⚠️ GitHub repozitoriysini tahlil qilishda xatolik yuz berdi."


# Global AI xizmati instansiyasi
ai_service = AIService()
