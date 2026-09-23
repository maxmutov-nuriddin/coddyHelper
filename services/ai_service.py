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
from prompts import SYSTEM_PROMPT, ADMIN_SYSTEM_PROMPT, ADMINISTRATION_SYSTEM_PROMPT
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

ESCALATE_PATTERN = re.compile(
    r"<+ESCALATE>+([\s\S]*?)<+END_ESCALATE>+|"
    r"<+ESCALATE>+([\s\S]*?)(?:\n\n|\Z)",
    re.DOTALL | re.IGNORECASE
)


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


def detect_programming_topic(text: str) -> str | None:
    """
    Foydalanuvchi xabaridan dasturlash mavzusini aniqlaydi.
    Mavzular: loops, functions, data_structures, oop, syntax_indentation, exceptions, file_io.
    """
    if not text:
        return None
    t = text.lower()

    if re.search(r"(indentationerror|taberror|syntaxerror|\bprobel|\btab\b|\botstup|\bотступ|\bsintaksis)", t):
        return "syntax_indentation"

    if re.search(r"(for\s+tsikl|while\s+tsikl|for\s+loop|while\s+loop|\btsikl|\bsikl|\bloop|\bцикл|range\s*\(|cheksiz\s+tsikl|\bfor\s+\w+\s+in\b|\bwhile\s+)", t):
        return "loops"

    if re.search(r"(\bfunksiya|\bfunktsiya|\bdef\s+\w+|\bparametr|\breturn\b|\bqaytarish|\bфункци)", t):
        return "functions"

    if re.search(r"(\bclass\s+\w+|\bklass|\bobyekt|\boop\b|__init__|\bmeros|\bpolimorfizm|\binkapsulyatsiya|\bкласс|\bобъект|\bнаследован|\bинкапсуляц)", t):
        return "oop"

    if re.search(r"(\blist\b|\bdict\b|\bdictionary\b|\blug['’]?at|\bmassiv|\bset\b|\btuple\b|\bkortej|\bro['’]?yxat|\bspisok|\bspiski|\bсловар|\.append\s*\(|\.pop\s*\()", t):
        return "data_structures"

    if re.search(r"(\btry\s*:|\bexcept\b|\bexception|\bxatolikni\s+ushlash|indexerror|keyerror|valueerror|typeerror|zerodivisionerror|\bисключени)", t):
        return "exceptions"

    if re.search(r"(\bfayl|open\s*\(|with\s+open|\bfaylga|\bfayldan|\bфайл)", t):
        return "file_io"

    return None


def detect_student_feedback_reaction(text: str) -> str | None:
    """
    O'quvchining oldingi javobdan keyingi reaksiyasini (muvaffaqiyat / tushunmovchilik) aniqlaydi.
    Natija: 'success' | 'confusion' | None.
    """
    if not text:
        return None
    t = text.lower().strip()

    # Muvaffaqiyat (Success)
    if re.search(r"\b(rahmat|raxmat|tushundim|ishladi|ishlab ketdi|xato yo'qoldi|to'g'rilandi|tog'rilandi|boldi|bo'ldi|spasibo|ponyal|zarabotalo|poluchilos|rabotayet|vse ponyatno|spasibki)\b", t):
        return "success"

    # Tushunmovchilik (Confusion)
    if re.search(r"\b(tushunmadim|qanaqasiga|nima degani|yana xato|baribir ishlamadi|ishlamayapti|ishlamadi|ne ponyal|ne rabotayet|snova oshibka|vse ravno ne rabotayet)\b", t):
        return "confusion"

    return None


def apply_socratic_critic(answer: str, user_message: str) -> str:
    """
    Pedagogik Sifat Nazoratchisi (Critic):
    O'quvchilarga tayyor uy vazifasi yechimini 100% ko'chirishga berib yubormaydi.
    Katta (25+ qatorli) tayyor kod bloklarini scaffold + yo'naltiruvchi sokratik savolga aylantiradi.
    """
    if not answer:
        return answer

    # Ortiqcha tizim taglarini tozalash
    answer = re.sub(r"<<<[A-Za-z0-9_]+:[^>]*>>>", "", answer)

    # Markdown kod bloklarini tekshirish
    code_block_regex = re.compile(r"```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```")

    def _truncate_code_block(match: re.Match) -> str:
        lang = match.group(1) or "python"
        code = match.group(2)
        lines = code.splitlines()

        # Agar kod 25 qatordan kam bo'lsa, o'zgartirmaymiz
        if len(lines) <= 25:
            return match.group(0)

        is_ru = is_russian_text(user_message) or is_russian_text(answer)

        # 12 qator saqlab qolamiz, qolganini scaffold qilamiz
        kept_lines = lines[:12]
        comment_prefix = "//" if lang.lower() in ("javascript", "js", "cpp", "c", "csharp", "cs", "java", "dart") else "#"

        if is_ru:
            placeholder = (
                f"\n{comment_prefix} ... [ОСТАЛЬНУЮ ЧАСТЬ КОДА НАПИШИТЕ САМОСТОЯТЕЛЬНО] ...\n"
                f"{comment_prefix} Подсказка: Попробуйте применить условие или цикл здесь.\n"
            )
        else:
            placeholder = (
                f"\n{comment_prefix} ... [QOLGAN MANTIQNI O'ZINGIZ YOZIB KO'RING] ...\n"
                f"{comment_prefix} Maslahat: Shu yerda shart yoki tsikl yordamida davom ettiring.\n"
            )

        new_code = "\n".join(kept_lines) + placeholder
        return f"```{lang}\n{new_code}\n```"

    transformed_answer = code_block_regex.sub(_truncate_code_block, answer)

    # Agar kod qisqartirilgan bo'lsa, oxiriga Sokratik pedagogik savol qo'shamiz
    if transformed_answer != answer:
        is_ru = is_russian_text(user_message) or is_russian_text(answer)
        if is_ru:
            socratic_hint = (
                "\n\n💡 **Совет наставника:** Полное копирование готового кода не научит программировать. "
                "Я дал вам базовый шаблон выше. Как вы думаете, какой следующий шаг нужно сделать? "
                "Напишите свой вариант, и я с радостью помогу его доработать!"
            )
        else:
            socratic_hint = (
                "\n\n💡 **Ustoz maslahati:** Tayyor kodni to'liq ko'chirib qo'yish dasturlashni o'rganishga yordam bermaydi. "
                "Yuqorida sizga asosiy skeletni (shablonni) berdim. Sizningcha, keyingi qadamda nima qilishimiz kerak? "
                "O'z fikringizni yoki kodingizni yozing, birgalikda tekshiramiz 😊"
            )
        transformed_answer += socratic_hint

    return transformed_answer


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
        (r"\b(?:1|bir)?\s*necha\s*(?:bo['’‘`]?lsa\s*ham\s*)?soat\w*", "2 soat"),
        (r"\b(?:1|bir)?\s*necha\s*(?:bo['’‘`]?lsa\s*ham\s*)?(?:daqiqa|minut)\w*", "15 daqiqa"),
        (r"\b(?:1|bir)?\s*necha\s*(?:bo['’‘`]?lsa\s*ham\s*)?kun\w*", "2 kun"),
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


def _create_default_cascade() -> dict[str, dict[str, Any]]:
    """Har bir miya uchun toza, mustaqil 4 talik modellar zanjirini yaratadi."""
    return {
        "openai/gpt-oss-120b": {"role": "Asosiy (120B)", "state": "active", "context": "128k", "tpm": "8k", "rpm": 1000},
        "openai/gpt-oss-20b": {"role": "Zaxira 1 (20B)", "state": "standby", "context": "128k", "tpm": "8k", "rpm": 1000},
        "qwen/qwen3.8-27b": {"role": "Zaxira 2 (Qwen 27B)", "state": "standby", "context": "128k", "tpm": "8k", "rpm": 1000},
        "Google Gemini": {"role": "Temir Zaxira (1M)", "state": "standby", "context": "1M", "tpm": "1M", "rpm": 15},
    }


class AIService:
    detect_student_feedback_reaction = staticmethod(detect_student_feedback_reaction)

    def __init__(self):
        self._groq_clients: list[Any] = []
        self._groq_keys: list[str] = []
        self._client_to_idx: dict[int, int] = {}
        # 3 ta mustaqil va limitlari ajratilgan kalitlar hovuzi:
        self._frontline_clients: list[Any] = []   # Miya 1: O'quvchilar va umumiy chatlar
        self._vip_clients: list[Any] = []         # Miya 2: VIP Vazifalar guruhi & Mentor
        self._reserve_clients: list[Any] = []     # Miya 3: Groq Zaxira Qalqoni (Buffer)
        self._autonomous_clients: list[Any] = []  # Miya 5: Avtonom O'rganuvchi Ong (Daemon)
        self._groq_idx: int = 0
        self._frontline_idx: int = 0
        self._vip_idx: int = 0
        self._reserve_idx: int = 0
        self._autonomous_idx: int = 0
        self._last_active_key_idx: int = 0
        self._last_active_team_idx: int = 1
        self._key_stats: dict[int, dict[str, Any]] = {}
        self._gemini_client: Any = None
        self._brain_stats: dict[str, int] = {
            "frontline": 0,
            "vip": 0,
            "groq_reserve": 0,
            "reserve": 0,
            "autonomous": 0,
        }
        self._brain_token_windows: dict[str, list[tuple[float, int]]] = {
            "frontline": [],
            "vip": [],
            "groq_reserve": [],
            "reserve": [],
            "autonomous": [],
        }
        self._brain_tokens_total: dict[str, int] = {
            "frontline": 0,
            "vip": 0,
            "groq_reserve": 0,
            "reserve": 0,
            "autonomous": 0,
        }
        # Har bir Miya uchun 100% mustaqil modellar zanjiri (Per-Brain Cascade Architecture):
        self._brain_cascades: dict[str, dict[str, dict[str, Any]]] = {
            "frontline": _create_default_cascade(),
            "vip": _create_default_cascade(),
            "groq_reserve": _create_default_cascade(),
            "autonomous": _create_default_cascade(),
        }
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
                "remaining_tokens": 8000,
                "limit_tokens": 8000,
                "used_tokens_pct": 0.0,
                "remaining_requests": 1000,
                "limit_requests": 1000,
                "reset_tokens": "0s",
                "reset_requests": "0s",
            },
            "cascade_status": self._brain_cascades["vip"],
            "brain_cascades": self._brain_cascades,
        }
        self._setup_clients()

    def restart(self) -> None:
        """AI Service holatini to'liq tozalaydi, kalitlarni qayta ulaydi va barcha statuslarni tiklaydi."""
        self._groq_idx = 0
        self._frontline_idx = 0
        self._vip_idx = 0
        self._reserve_idx = 0
        self._autonomous_idx = 0
        self._last_active_key_idx = 0
        self._last_active_team_idx = 1
        self._key_stats = {}
        for b in ("frontline", "vip", "groq_reserve", "autonomous"):
            self._brain_cascades[b] = _create_default_cascade()
        self._metrics["cascade_status"] = self._brain_cascades["vip"]
        self._metrics["brain_cascades"] = self._brain_cascades
        self._setup_clients()
        logger.info("🔄 AIService to'liq qayta yuklandi va mustaqil miya kaskadlari yangilandi.")

    def _resolve_brain_tag(self, k_idx: int) -> str:
        """Kalit indeksiga qarab miyaning tagini aniqlaydi."""
        if 0 <= k_idx < len(self._groq_clients):
            c = self._groq_clients[k_idx]
            if c in self._frontline_clients:
                return "frontline"
            elif c in self._vip_clients:
                return "vip"
            elif c in self._reserve_clients:
                return "groq_reserve"
            elif c in self._autonomous_clients:
                return "autonomous"
        fl = len(self._frontline_clients)
        vl = fl + len(self._vip_clients)
        rl = vl + len(self._reserve_clients)
        if k_idx < fl:
            return "frontline"
        elif k_idx < vl:
            return "vip"
        elif k_idx < rl:
            return "groq_reserve"
        return "autonomous"

    def _record_brain_tokens(self, brain: str, tokens: int) -> None:
        """Rolling 60s oynasiga tokenlarni yozadi va jami hisobni oshiradi."""
        now = time.time()
        if brain not in self._brain_token_windows:
            self._brain_token_windows[brain] = []
        self._brain_token_windows[brain].append((now, tokens))
        # 60 soniyadan eski yozuvlarni tozalash
        cutoff = now - 60.0
        self._brain_token_windows[brain] = [
            (ts, t) for ts, t in self._brain_token_windows[brain] if ts >= cutoff
        ]
        self._brain_tokens_total[brain] = self._brain_tokens_total.get(brain, 0) + tokens

    def _get_brain_minute_tokens(self, brain: str) -> int:
        """So'nggi 60 soniyada sarflangan tokenlar soni."""
        now = time.time()
        cutoff = now - 60.0
        window = self._brain_token_windows.get(brain, [])
        # Tozalash ham
        fresh = [(ts, t) for ts, t in window if ts >= cutoff]
        self._brain_token_windows[brain] = fresh
        return sum(t for _, t in fresh)

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
            # Per-brain token tracking
            brain_tag = self._resolve_brain_tag(self._last_active_key_idx)
            self._record_brain_tokens(brain_tag, t_tok)
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
                def _parse_duration_seconds(dur_str: str) -> float:
                    if not dur_str:
                        return 60.0
                    d = dur_str.strip().lower()
                    try:
                        if d.endswith("ms"):
                            return float(d[:-2]) / 1000.0
                        if "m" in d and "s" in d:
                            parts = d.split("m")
                            m = float(parts[0])
                            s = float(parts[1].replace("s", "")) if parts[1] else 0.0
                            return m * 60.0 + s
                        if d.endswith("s"):
                            return float(d[:-1])
                        if d.endswith("m"):
                            return float(d[:-1]) * 60.0
                        return float(d)
                    except Exception:
                        return 60.0

                self._last_groq_metrics_ts = time.time()
                self._reset_tokens_seconds = _parse_duration_seconds(rst_t_str)
                self._reset_requests_seconds = _parse_duration_seconds(rst_r_str)

                self._metrics["rate_limits"] = {
                    "remaining_tokens": rem_t,
                    "limit_tokens": lim_t,
                    "used_tokens_pct": used_pct,
                    "remaining_requests": rem_r,
                    "limit_requests": lim_r,
                    "reset_tokens": rst_t_str or "0s",
                    "reset_requests": rst_r_str or "0s",
                }

            self._recalculate_cascade_states(brain=brain_tag, active_override=model_name)
        except Exception as err:
            logger.warning("AI metrikalarini yangilashda ogohlantirish: %s", err)

    def _recalculate_cascade_states(self, brain: str = "vip", active_override: str | None = None) -> None:
        """
        Tanlangan miya (frontline, vip, autonomous) kaskad zanjiridagi modellar holatini
        haqiqiy holat bo'yicha dinamik qayta hisoblaydi.
        Har bir miya uchun faqat bitta sog'lom model 'active' (🟢 Faol) bo'ladi,
        qolgan sog'lom modellar 'standby' (🟡 Zaxirada) bo'ladi.
        """
        try:
            if not hasattr(self, "_brain_cascades") or not self._brain_cascades:
                self._brain_cascades = {
                    "frontline": _create_default_cascade(),
                    "vip": _create_default_cascade(),
                    "autonomous": _create_default_cascade(),
                }
            if brain not in self._brain_cascades:
                self._brain_cascades[brain] = _create_default_cascade()
            cascade = self._brain_cascades[brain]
            now_ts = time.time()
            priority_order = [
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
                "qwen/qwen3.8-27b",
                "Google Gemini",
            ]
            if config.groq_model and config.groq_model not in priority_order:
                priority_order.insert(0, config.groq_model)

            # Muddati o'tgan limitlarni tozalash
            for m_key, info in cascade.items():
                if info.get("state") == "rate_limited":
                    until = info.get("rate_limited_until", 0)
                    if now_ts >= until:
                        info["state"] = "standby"
                        info["last_error"] = None

            if active_override and active_override in cascade:
                for m_key, info in cascade.items():
                    if m_key == active_override:
                        info["state"] = "active"
                    elif info.get("state") != "rate_limited":
                        info["state"] = "standby"
                if brain == "vip":
                    self._metrics["active_model"] = active_override
                    self._metrics["cascade_status"] = cascade
                return

            first_healthy_found = False
            active_name = None
            for m_key in priority_order:
                if m_key not in cascade:
                    continue
                info = cascade[m_key]
                if info.get("state") == "rate_limited":
                    continue
                if not first_healthy_found:
                    info["state"] = "active"
                    active_name = m_key
                    first_healthy_found = True
                else:
                    info["state"] = "standby"

            # Agar yuqorida bo'lmagan boshqa modellar bo'lsa, ularni ham standby qilish
            for m_key, info in cascade.items():
                if m_key != active_name and info.get("state") != "rate_limited":
                    info["state"] = "standby"

            if not first_healthy_found and "Google Gemini" in cascade:
                cascade["Google Gemini"]["state"] = "active"
                active_name = "Google Gemini"

            if brain == "vip" and active_name:
                self._metrics["active_model"] = active_name
                self._metrics["cascade_status"] = cascade
        except Exception as e:
            logger.debug("Cascade qayta hisoblashda ogohlantirish (%s): %s", brain, e)

    def _refresh_key_and_model_recovery(self) -> None:
        """60 soniyalik limit davri o'tgan kalitlar va barcha miyalar modellarini avtomatik tiklash."""
        now_ts = time.time()
        for idx, stat in self._key_stats.items():
            if stat.get("status") in ("rate_limited", "error"):
                until = stat.get("rate_limited_until", 0)
                if now_ts >= until:
                    stat["status"] = "standby"
                    stat["last_error"] = None

        for b in ("frontline", "vip", "autonomous"):
            self._recalculate_cascade_states(brain=b)

    def _record_model_rate_limited(self, model_name: str, error_msg: str = "", brain: str = "frontline") -> None:
        """Tanlangan miyada model limitga uchraganida uning holatini yangilaydi."""
        try:
            if not hasattr(self, "_brain_cascades") or not self._brain_cascades:
                self._brain_cascades = {
                    "frontline": _create_default_cascade(),
                    "vip": _create_default_cascade(),
                    "autonomous": _create_default_cascade(),
                }
            if brain not in self._brain_cascades:
                self._brain_cascades[brain] = _create_default_cascade()
            cascade = self._brain_cascades[brain]
            if model_name in cascade:
                cascade[model_name]["state"] = "rate_limited"
                cascade[model_name]["last_error"] = str(error_msg)[:120]
                err_str = str(error_msg).lower()
                parsed_cooldown = 0.0
                match = re.search(r"try again in (?:(\d+)m)?(?:([\d\.]+)s)?", err_str)
                if match:
                    mins = float(match.group(1)) if match.group(1) else 0.0
                    secs = float(match.group(2)) if match.group(2) else 0.0
                    if mins > 0 or secs > 0:
                        parsed_cooldown = mins * 60.0 + secs
                cooldown = 60.0
                if parsed_cooldown > 0:
                    cooldown = parsed_cooldown
                elif "tpd" in err_str or "tokens per day" in err_str or "per day" in err_str:
                    cooldown = 900.0

                now_curr = time.time()
                new_until = now_curr + cooldown
                existing_until = cascade[model_name].get("rate_limited_until", 0.0)

                # Agar model allaqachon limitda bo'lsa va uning taymeri hali tugamagan bo'lsa,
                # mavjud ochilish vaqtini aslo orqaga surib yubormaymiz!
                if existing_until > now_curr:
                    cascade[model_name]["rate_limited_until"] = min(existing_until, new_until)
                else:
                    cascade[model_name]["rate_limited_until"] = new_until
            self._recalculate_cascade_states(brain=brain)
        except Exception:
            pass

    def _record_gemini_metrics(self, prompt_len: int, completion_len: int, duration_ms: int = 0, brain_tag: str = "reserve") -> None:
        """Google Gemini zaxira tizimi ishlaganda metrikalarni yangilaydi."""
        try:
            self._metrics["last_provider"] = "Google Gemini"
            self._metrics["active_model"] = "Google Gemini"
            self._metrics["last_model"] = config.gemini_model
            now_iso = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
            self._metrics["last_updated"] = now_iso
            self._metrics["total_requests"] = self._metrics.get("total_requests", 0) + 1
            self._brain_stats["reserve"] = self._brain_stats.get("reserve", 0) + 1
            if brain_tag and brain_tag != "reserve":
                self._brain_stats[brain_tag] = self._brain_stats.get(brain_tag, 0) + 1

            p_tok = int(prompt_len / 3.5)
            c_tok = int(completion_len / 3.5)
            t_tok = p_tok + c_tok
            self._metrics["total_tokens"] = self._metrics.get("total_tokens", 0) + t_tok
            # Per-brain token tracking
            self._record_brain_tokens(brain_tag, t_tok)
            self._metrics["last_request"] = {
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": t_tok,
                "duration_ms": duration_ms,
                "timestamp": now_iso,
            }
            if brain_tag in self._brain_cascades:
                self._recalculate_cascade_states(brain=brain_tag, active_override="Google Gemini")
            cascade = self._metrics.setdefault("cascade_status", {})
            if "Google Gemini" in cascade:
                cascade["Google Gemini"]["state"] = "active"
        except Exception as err:
            logger.warning("Gemini metrikalarini yangilashda ogohlantirish: %s", err)

    def _mark_key_used(self, key_idx: int) -> None:
        """Belgilangan kalit va tegishli jamoani faol deb belgilaydi hamda statistikasini oshiradi."""
        try:
            if not self._groq_keys or key_idx < 0 or key_idx >= len(self._groq_keys):
                return
            self._last_active_key_idx = key_idx
            self._last_active_team_idx = (key_idx // 3) + 1
            now_iso = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%H:%M:%S")
            if key_idx not in self._key_stats:
                self._key_stats[key_idx] = {"requests": 0, "last_used": None, "status": "active", "errors": 0}
            self._key_stats[key_idx]["requests"] = self._key_stats[key_idx].get("requests", 0) + 1
            self._key_stats[key_idx]["last_used"] = now_iso
            self._key_stats[key_idx]["status"] = "active"
        except Exception as e:
            logger.debug("Kalit statistikasini yangilashda ogohlantirish: %s", e)

    def _mark_key_error(self, key_idx: int, error_msg: str = "") -> None:
        """Kalitda xatolik yoki limit bo'lganda holatini qayd etadi (TTL: 60s)."""
        try:
            if not self._groq_keys or key_idx < 0 or key_idx >= len(self._groq_keys):
                return
            if key_idx not in self._key_stats:
                self._key_stats[key_idx] = {"requests": 0, "last_used": None, "status": "standby", "errors": 0}
            self._key_stats[key_idx]["errors"] = self._key_stats[key_idx].get("errors", 0) + 1
            err_str = str(error_msg).lower()
            now_ts = time.time()
            if "429" in err_str or "rate_limit" in err_str or "413" in err_str:
                self._key_stats[key_idx]["status"] = "rate_limited"
                self._key_stats[key_idx]["rate_limited_until"] = now_ts + 60.0
            else:
                self._key_stats[key_idx]["status"] = "error"
                self._key_stats[key_idx]["rate_limited_until"] = now_ts + 30.0
            self._key_stats[key_idx]["last_error"] = str(error_msg)[:100]
        except Exception:
            pass

    def get_metrics(self) -> dict[str, Any]:
        """Tizimning joriy AI modeli, TPM/RPM limitlari, kalitlar va jamoalar statistikasi."""
        self._refresh_key_and_model_recovery()
        total_keys = len(self._groq_keys)
        def _resolve_brain_info(k_idx: int) -> tuple[str, str]:
            tag = self._resolve_brain_tag(k_idx)
            if tag == "frontline":
                return "Miya 1: Frontline", "frontline"
            elif tag == "vip":
                return "Miya 2: VIP Vazifalar", "vip"
            elif tag == "groq_reserve":
                return "Miya 3: Groq Zaxira Qalqoni", "groq_reserve"
            else:
                return "Miya 5: Avtonom Ong", "autonomous"

        keys_pool = []
        for i, k in enumerate(self._groq_keys):
            masked = f"{k[:8]}...{k[-4:]}" if len(k) > 14 else (f"{k[:4]}..." if k else f"Key #{i+1}")
            stats = self._key_stats.get(i, {"requests": 0, "last_used": None, "status": "standby"})
            is_active = (i == self._last_active_key_idx)
            team_id = (i // 3) + 1
            brain_name, brain_tag = _resolve_brain_info(i)
            st = stats.get("status", "standby")
            if is_active:
                st = "active"
            elif st not in ("rate_limited", "error"):
                st = "standby"

            keys_pool.append({
                "index": i + 1,
                "key_masked": masked,
                "team_id": team_id,
                "brain": brain_name,
                "brain_tag": brain_tag,
                "is_active": is_active,
                "requests_count": stats.get("requests", 0),
                "last_used": stats.get("last_used"),
                "status": st,
            })

        teams = []
        total_teams = max(1, (len(self._groq_keys) + 2) // 3) if self._groq_keys else 0
        for t in range(1, total_teams + 1):
            team_keys = [kp for kp in keys_pool if kp["team_id"] == t]
            team_is_active = (t == self._last_active_team_idx)
            team_requests = sum(kp["requests_count"] for kp in team_keys)
            key_indices = [kp["index"] for kp in team_keys]
            if t <= 4:
                t_brain = "Miya 1: Frontline (Talabalar)"
            elif t <= 8:
                t_brain = "Miya 2: VIP Vazifalar (Mentor)"
            elif t <= 12:
                t_brain = "Miya 3: Groq Zaxira Qalqoni (Buffer)"
            else:
                t_brain = "Miya 5: Avtonom Ong (Pre-Cognition)"

            teams.append({
                "team_id": t,
                "name": f"Jamoa #{t}",
                "brain": t_brain,
                "keys": key_indices,
                "keys_text": f"Kalitlar: {', '.join(f'#{k}' for k in key_indices)}",
                "is_active": team_is_active,
                "requests_count": team_requests,
                "members_count": len(team_keys),
                "roles": "Lead Coder, Senior Critic, Synthesizer" if len(team_keys) >= 3 else "Assistent",
                "status": "active" if team_is_active else "standby",
            })

        # Real-time dinamik TPM va RPM tiklanishini hisoblash (O'tgan vaqt hisobga olinadi):
        now_ts = time.time()
        rl = dict(self._metrics.get("rate_limits", {}))
        last_ts = getattr(self, "_last_groq_metrics_ts", 0)

        if last_ts > 0 and rl:
            elapsed = now_ts - last_ts
            reset_t_sec = getattr(self, "_reset_tokens_seconds", 60.0)
            reset_r_sec = getattr(self, "_reset_requests_seconds", 60.0)
            lim_t = rl.get("limit_tokens", 8000)
            lim_r = rl.get("limit_requests", 1000)

            if elapsed >= reset_t_sec or elapsed >= 60.0:
                # 60 soniyadan so'ng yoki reset vaqti o'tgach TPM 100% tiklangan!
                rl["remaining_tokens"] = lim_t
                rl["used_tokens_pct"] = 0.0
                rl["reset_tokens"] = "0s (100% bo'sh)"
            else:
                rem_sec = max(0.0, reset_t_sec - elapsed)
                rl["reset_tokens"] = f"{rem_sec:.1f}s"
                ratio = min(1.0, elapsed / max(1.0, reset_t_sec))
                initial_rem = rl.get("remaining_tokens", lim_t)
                current_rem = int(initial_rem + (lim_t - initial_rem) * ratio)
                rl["remaining_tokens"] = min(lim_t, max(initial_rem, current_rem))
                rl["used_tokens_pct"] = round(max(0.0, (lim_t - rl["remaining_tokens"]) / lim_t * 100), 1)

            if elapsed >= reset_r_sec or elapsed >= 60.0:
                rl["remaining_requests"] = lim_r
                rl["reset_requests"] = "0s"
            else:
                rem_r_sec = max(0.0, reset_r_sec - elapsed)
                rl["reset_requests"] = f"{rem_r_sec:.1f}s"

        _fl_mt = self._get_brain_minute_tokens("frontline")
        _vip_mt = self._get_brain_minute_tokens("vip")
        _groq_res_mt = self._get_brain_minute_tokens("groq_reserve")
        _res_mt = self._get_brain_minute_tokens("reserve")
        _aut_mt = self._get_brain_minute_tokens("autonomous")

        _fl_lim = max(8000, len(self._frontline_clients) * 8000)
        _vip_lim = max(8000, len(self._vip_clients) * 8000)
        _groq_res_lim = max(8000, len(self._reserve_clients) * 8000)
        _aut_lim = max(8000, len(self._autonomous_clients) * 8000)

        return {
            "ok": True,
            "active_model": self._metrics.get("active_model", config.groq_model),
            "last_provider": self._metrics.get("last_provider", "Groq"),
            "last_model": self._metrics.get("last_model", config.groq_model),
            "last_updated": self._metrics.get("last_updated"),
            "total_requests": self._metrics.get("total_requests", 0),
            "total_tokens": self._metrics.get("total_tokens", 0),
            "last_request": self._metrics.get("last_request", {}),
            "rate_limits": rl,
            "cascade_status": self._brain_cascades.get("vip", {}),
            "brain_cascades": self._brain_cascades,
            "available_groq_keys": len(self._groq_clients),
            "frontline_keys_count": len(self._frontline_clients),
            "vip_keys_count": len(self._vip_clients),
            "reserve_groq_keys_count": len(self._reserve_clients),
            "autonomous_keys_count": len(self._autonomous_clients),
            "active_key_index": (self._last_active_key_idx + 1) if self._groq_clients else 0,
            "active_team_id": self._last_active_team_idx if self._groq_clients else 0,
            "brain_stats": self._brain_stats,
            "brains": {
                "miya_1_frontline": {
                    "title": "Miya 1: Frontline (Talabalar & Chatlar)",
                    "keys_count": len(self._frontline_clients),
                    "status": "active" if self._frontline_clients else "standby",
                    "active_model": next((m for m, inf in self._brain_cascades.get("frontline", {}).items() if inf.get("state") == "active"), config.groq_model),
                    "cascade": self._brain_cascades.get("frontline", {}),
                    "role": "Barcha o'quvchilar va umumiy guruhlar so'rovlariga tezkor javob beradi (Jamoalar #1-#4)",
                    "requests": self._brain_stats.get("frontline", 0),
                    "minute_tokens": _fl_mt,
                    "limit_tpm": _fl_lim,
                    "minute_tokens_pct": round(min(100.0, _fl_mt / _fl_lim * 100), 1),
                    "total_tokens": self._brain_tokens_total.get("frontline", 0),
                },
                "miya_2_vip": {
                    "title": "Miya 2: VIP Vazifalar Guruhi (O'ta muhim)",
                    "keys_count": len(self._vip_clients),
                    "status": "active" if self._vip_clients else "standby",
                    "active_model": next((m for m, inf in self._brain_cascades.get("vip", {}).items() if inf.get("state") == "active"), config.groq_model),
                    "cascade": self._brain_cascades.get("vip", {}),
                    "role": "Vazifalar guruhi va Mentor buyruqlari uchun 100% ajratilgan mustaqil limit (Jamoalar #5-#8)",
                    "requests": self._brain_stats.get("vip", 0),
                    "minute_tokens": _vip_mt,
                    "limit_tpm": _vip_lim,
                    "minute_tokens_pct": round(min(100.0, _vip_mt / _vip_lim * 100), 1),
                    "total_tokens": self._brain_tokens_total.get("vip", 0),
                },
                "miya_3_groq_reserve": {
                    "title": "Miya 3: Groq Zaxira Qalqoni (Buffer)",
                    "keys_count": len(self._reserve_clients),
                    "status": "active" if self._reserve_clients else "standby",
                    "active_model": next((m for m, inf in self._brain_cascades.get("groq_reserve", {}).items() if inf.get("state") == "active"), config.groq_model),
                    "cascade": self._brain_cascades.get("groq_reserve", {}),
                    "role": "Frontline va VIP miyalar limitga uchraganda Gemini'dan oldin yordamga keluvchi bufer (Jamoalar #9-#12)",
                    "requests": self._brain_stats.get("groq_reserve", 0),
                    "minute_tokens": _groq_res_mt,
                    "limit_tpm": _groq_res_lim,
                    "minute_tokens_pct": round(min(100.0, _groq_res_mt / _groq_res_lim * 100), 1),
                    "total_tokens": self._brain_tokens_total.get("groq_reserve", 0),
                },
                "miya_4_reserve": {
                    "title": "Miya 4: Temir Zaxira (Google Gemini)",
                    "enabled": memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true",
                    "keys_count": 1 if self._gemini_client else 0,
                    "status": ("active" if self._gemini_client else "standby") if memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true" else "disabled",
                    "active_model": "Google Gemini",
                    "role": "Favqulodda vaziyatlar va barcha Groq limitlari tugaganda so'nggi istehkom (1M context)",
                    "requests": self._brain_stats.get("reserve", 0),
                    "minute_tokens": _res_mt,
                    "limit_tpm": 1000000,
                    "minute_tokens_pct": round(min(100.0, _res_mt / 1000000 * 100), 1),
                    "total_tokens": self._brain_tokens_total.get("reserve", 0),
                    "scope": memory_service.get_setting("gemini_scope", "all"),
                    "trigger_after": memory_service.get_setting("gemini_trigger_after", "after_reserve"),
                },
                "miya_5_autonomous": {
                    "title": "Miya 5: Avtonom Tafakkur Ongi (Daemon)",
                    "keys_count": len(self._autonomous_clients),
                    "status": "active" if self._autonomous_clients else "standby",
                    "active_model": next((m for m, inf in self._brain_cascades.get("autonomous", {}).items() if inf.get("state") == "active"), config.groq_model),
                    "cascade": self._brain_cascades.get("autonomous", {}),
                    "role": "Orqa fonda to'xtovsiz tafakkur qiladi, o'rganadi va yechimlarni oldindan tayyorlaydi (Jamoalar #13-#16)",
                    "requests": self._brain_stats.get("autonomous", 0),
                    "minute_tokens": _aut_mt,
                    "limit_tpm": _aut_lim,
                    "minute_tokens_pct": round(min(100.0, _aut_mt / _aut_lim * 100), 1),
                    "total_tokens": self._brain_tokens_total.get("autonomous", 0),
                },
            },
            "keys_pool": keys_pool,
            "teams": teams,
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
        # Groq yangi modellarida reasoning va javob uchun 1000 token xavfsiz chegara
        safe_max_tokens = min(max_tokens, 1000)
        t0 = time.time()
        k_idx = self._client_to_idx.get(id(client), self._last_active_key_idx)
        self._mark_key_used(k_idx)
        try:
            if hasattr(client.chat.completions, "with_raw_response"):
                raw_resp = await asyncio.wait_for(
                    client.chat.completions.with_raw_response.create(
                        model=model_name,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=safe_max_tokens,
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
                        max_tokens=safe_max_tokens,
                    ),
                    timeout=18.0,
                )
                duration_ms = int((time.time() - t0) * 1000)
                self._record_groq_metrics(model_name, response, headers=None, duration_ms=duration_ms)
                return response
        except Exception as err:
            self._mark_key_error(k_idx, str(err))
            raise

    def _setup_clients(self) -> None:
        """Mavjud provayderlarni aniqlaydi va kalitlar zaxirasini sozlaydi."""
        # 1. Groq kalitlarini ulash (Multi-key pool)
        keys = config.groq_api_keys or ([config.groq_api_key] if config.groq_api_key else [])
        self._groq_clients = []
        self._groq_keys = [k for k in keys if k]
        self._client_to_idx = {}
        if not hasattr(self, "_key_stats") or not self._key_stats:
            self._key_stats = {}

        if self._groq_keys:
            try:
                from groq import AsyncGroq
                for idx, k in enumerate(self._groq_keys):
                    c = AsyncGroq(api_key=k, timeout=15.0, max_retries=1)
                    self._groq_clients.append(c)
                    self._client_to_idx[id(c)] = idx
                    if idx not in self._key_stats:
                        self._key_stats[idx] = {
                            "requests": 0,
                            "last_used": None,
                            "status": "standby",
                            "errors": 0,
                        }
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

        # 3. 4 ta mustaqil Groq miyasiga kalitlar taqsimoti (Limitlar va TPM/RPM mutlaq izolyatsiya qilingan):
        total = len(self._groq_clients)
        has_explicit = bool(config.groq_frontline_keys or config.groq_vip_keys or config.groq_reserve_keys or config.groq_autonomous_keys)
        if has_explicit:
            f_keys = config.groq_frontline_keys or []
            v_keys = config.groq_vip_keys or []
            r_keys = config.groq_reserve_keys or []
            a_keys = config.groq_autonomous_keys or []
            self._frontline_clients = [c for c in self._groq_clients if self._groq_keys[self._client_to_idx.get(id(c), 0)] in f_keys]
            self._vip_clients = [c for c in self._groq_clients if self._groq_keys[self._client_to_idx.get(id(c), 0)] in v_keys]
            self._reserve_clients = [c for c in self._groq_clients if self._groq_keys[self._client_to_idx.get(id(c), 0)] in r_keys]
            self._autonomous_clients = [c for c in self._groq_clients if self._groq_keys[self._client_to_idx.get(id(c), 0)] in a_keys]
            if not self._frontline_clients:
                self._frontline_clients = list(self._groq_clients[:12]) if total >= 12 else list(self._groq_clients)
            if not self._vip_clients:
                self._vip_clients = list(self._groq_clients[12:24]) if total >= 24 else list(self._groq_clients)
            if not self._reserve_clients:
                self._reserve_clients = list(self._groq_clients[24:36]) if total >= 36 else list(self._groq_clients)
            if not self._autonomous_clients:
                self._autonomous_clients = list(self._groq_clients[36:]) if total >= 37 else list(self._groq_clients)
        elif total >= 48:
            self._frontline_clients = self._groq_clients[:12]
            self._vip_clients = self._groq_clients[12:24]
            self._reserve_clients = self._groq_clients[24:36]
            self._autonomous_clients = self._groq_clients[36:48]
        elif total >= 30:
            # 30 ta kalit (10 ta 3 kishilik Pod komanda):
            self._frontline_clients = self._groq_clients[:12]
            self._vip_clients = self._groq_clients[12:21]
            self._reserve_clients = self._groq_clients[21:26]
            self._autonomous_clients = self._groq_clients[26:30]
        elif total >= 20:
            # 20 ta kalit:
            self._frontline_clients = self._groq_clients[:10]
            self._vip_clients = self._groq_clients[10:15]
            self._reserve_clients = self._groq_clients[15:18]
            self._autonomous_clients = self._groq_clients[18:total]
        elif total >= 9:
            f_end = (total * 3) // 10
            v_end = f_end + (total * 3) // 10
            r_end = v_end + (total * 2) // 10
            self._frontline_clients = self._groq_clients[:f_end]
            self._vip_clients = self._groq_clients[f_end:v_end]
            self._reserve_clients = self._groq_clients[v_end:r_end]
            self._autonomous_clients = self._groq_clients[r_end:]
        elif total >= 4:
            self._frontline_clients = [self._groq_clients[0]]
            self._vip_clients = [self._groq_clients[1]]
            self._reserve_clients = [self._groq_clients[2]]
            self._autonomous_clients = self._groq_clients[3:]
        else:
            self._frontline_clients = list(self._groq_clients)
            self._vip_clients = list(self._groq_clients)
            self._reserve_clients = list(self._groq_clients)
            self._autonomous_clients = list(self._groq_clients)

        logger.info(
            "🧠 Miyalararo Resurs Taqsimoti (Total: %d): Frontline=%d kalit, VIP Vazifalar=%d kalit, Groq Zaxira=%d kalit, Avtonom Ong=%d kalit",
            total,
            len(self._frontline_clients),
            len(self._vip_clients),
            len(self._reserve_clients),
            len(self._autonomous_clients),
        )

    def _get_active_pool(self, is_admin_mode: bool) -> tuple[list[Any], str]:
        """So'rov turiga ko'ra mutlaqo ajratilgan kalitlar hovuzini tanlaydi."""
        if is_admin_mode:
            pool = self._vip_clients if self._vip_clients else self._groq_clients
            return pool, "vip"
        else:
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients
            return pool, "frontline"

    async def generate_autonomous_reflection(self, prompt: str) -> str | None:
        """
        4-Miya (Avtonom Ong - Pre-Cognition) uchun maxsus orqa fon generatsiyasi.
        MUTLAQ ISOLYATSIYA:
        Faqatgina _autonomous_clients (Jamoalar #8-#10) kalitlaridan foydalanadi.
        O'quvchilar (Frontline) va VIP Vazifalar guruhi limitlariga zarracha ta'sir qilmaydi.
        """
        pool = self._autonomous_clients if self._autonomous_clients else self._groq_clients
        for retry_cycle in range(1, 3):
            if pool:
                self._brain_stats["autonomous"] = self._brain_stats.get("autonomous", 0) + 1

                self._refresh_key_and_model_recovery()
                preferred = []
                if config.groq_model:
                    preferred.append(config.groq_model)
                for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
                    if m not in preferred:
                        preferred.append(m)
                candidate_models = preferred

                cascade = self._brain_cascades.get("autonomous", {})
                now_ts = time.time()
                healthy_candidates = [
                    m for m in candidate_models
                    if cascade.get(m, {}).get("state") != "rate_limited" or now_ts >= cascade.get(m, {}).get("rate_limited_until", 0)
                ]
                candidate_models = healthy_candidates
                if not candidate_models:
                    logger.info("Miya 4 da barcha Groq modellari cooldown limitida.")
                    break

                for model_name in candidate_models:
                    self._recalculate_cascade_states(brain="autonomous", active_override=model_name)
                    max_try = min(5, len(pool))
                    model_had_success = False
                    for _ in range(max_try):
                        idx = self._autonomous_idx % len(pool)
                        self._autonomous_idx = (self._autonomous_idx + 1) % len(pool)
                        client = pool[idx]
                        k_real_idx = self._client_to_idx.get(id(client), 0)
                        self._mark_key_used(k_real_idx)
                        try:
                            res = await client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {"role": "system", "content": "Siz CoddyCamp IT akademiyasining ichki avtonom tafakkur miyasisiz (Miya 4)."},
                                    {"role": "user", "content": prompt},
                                ],
                                temperature=0.3,
                                max_tokens=700,
                            )
                            msg_obj = res.choices[0].message
                            txt = (getattr(msg_obj, "content", "") or "").strip()
                            if not txt and hasattr(msg_obj, "reasoning") and msg_obj.reasoning:
                                txt = msg_obj.reasoning.strip()
                            if txt:
                                model_had_success = True
                                self._record_brain_tokens("autonomous", max(1, len(txt) // 3))
                                return txt
                        except Exception as e:
                            logger.warning("Miya 4 avtonom generatsiyasida ogohlantirish (%s, kalit #%d): %s", model_name, k_real_idx + 1, e)
                            if "429" in str(e) or "rate_limit" in str(e):
                                self._mark_key_error(k_real_idx, str(e))
                                # Boshqa kalitlarni sinash uchun davom etamiz
                                continue
                            elif "413" in str(e):
                                break

                    if not model_had_success:
                        self._record_model_rate_limited(model_name, "All keys failed or rate-limited", brain="autonomous")

            # Fallback to Gemini if Groq is depleted or failed
            if self._gemini_client:
                try:
                    from google.genai import types
                    for m in [config.gemini_model, "gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest"]:
                        try:
                            response = self._gemini_client.models.generate_content(
                                model=m,
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    system_instruction="Siz CoddyCamp IT akademiyasining ichki avtonom tafakkur miyasisiz (Miya 4).",
                                    temperature=0.3,
                                    max_output_tokens=700,
                                ),
                            )
                            if response and response.text:
                                txt = response.text.strip()
                                self._record_brain_tokens("autonomous", max(1, len(txt) // 3))
                                return txt
                        except Exception as ge:
                            logger.warning("Miya 4 Gemini zaxira generatsiyasida ogohlantirish (%s): %s", m, ge)
                            continue
                except Exception as ge_all:
                    logger.error("Miya 4 Gemini zaxira tizimida xatolik: %s", ge_all)

            # Agar bu siklda hamma kalitlar limit bo'lsa, savolni tashlab yubormasdan 15s kutib qayta urinish:
            if retry_cycle < 2:
                logger.info("⏳ Miya 4 da barcha kalitlar qisqa limitda. 15s kutilmoqda va o'sha topshiriq qayta ishlanadi...")
                await asyncio.sleep(15)

        return None

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

    async def _extract_and_save_insight(self, prompt: str, reply: str) -> None:
        """
        Murakkab suhbat va yechimlardan avtomatik ravishda universal texnik xulosa/qoida
        ajratib olib, doimiy bilimlar bazasiga (autonomous_insight) saqlaydi.
        """
        try:
            if len(prompt.split()) < 6 or len(reply.split()) < 20:
                return
            # Telegram action yoki oddiy salom bo'lsa o'rganmaslik
            if "<<<ACTION:" in reply or any(w in prompt.lower() for w in ("salom", "kim yozdi", "eslat", "rahmat", "lokatsiya")):
                return

            pool = self._autonomous_clients if self._autonomous_clients else self._groq_clients
            if not pool:
                return
            client = pool[self._autonomous_idx % len(pool)]
            self._autonomous_idx = (self._autonomous_idx + 1) % len(pool)
            extract_prompt = (
                f"Quyidagi foydalanuvchi so'rovi va berilgan texnik yechimdan kelajakda AI agent uchun asqotadigan "
                f"1 ta universal texnik xulosa, qoida yoki arxitekturaviy saboq bormi?\n\n"
                f"So'rov: {prompt[:400]}\n"
                f"Yechim: {reply[:600]}\n\n"
                f"Agar bu oddiy gap yoki umumiy ma'lumot bo'lsa, FAQAT 'NO_INSIGHT' deb yozing.\n"
                f"Agar muhim texnik saboq yoki doimiy qoida bo'lsa, FAQAT quyidagi JSON formatida bering:\n"
                f'{{"topic": "qisqa_mavzu", "insight": "1 jumlalik aniq amaliy qoida"}}'
            )
            res = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.groq_model,
                    messages=[
                        {"role": "system", "content": "Siz bilim va xulosalarni ixcham ekstraksiya qiluvchi mutaxassissiz."},
                        {"role": "user", "content": extract_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=150,
                ),
                timeout=6.0,
            )
            text = res.choices[0].message.content.strip()
            if "NO_INSIGHT" in text or "{" not in text:
                return
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                topic = str(data.get("topic", "")).strip()
                insight = str(data.get("insight", "")).strip()
                if topic and insight and len(insight) > 10:
                    memory_service.record_autonomous_insight(topic, insight)
                    logger.info("🧠 Agent o'z tajribasidan yangi qoida o'rgandi: [%s] %s", topic, insight)
        except Exception as e:
            logger.debug("Avtonom bilim ekstraksiyasida xatolik (e'tiborsiz): %s", e)

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
        3 talik konsilium (Pod Klaster - System 2) orqali chuqur tahlil qilingan xatosiz javob generatsiya qilish:
        1-Agent: Lead Architect / Generator (Yechim va maqsad dekompozitsiyasi)
        2-Agent: Senior Critic / Devil's Advocate (Edge-cases, risklar, anti-patternlar va xavfsizlik)
        -> 1 va 2 - Agentlar PARALLEL (asyncio.gather) ishlaydi (tezlik yo'qotilmaydi ~0.5s)!
        3-Agent: Master Executive Synthesizer (O'zini tekshirish - Self-Correction, fakt-cheking va yakuniy sayqallash)
        + Epizodik xotira RAG va Avtonom tajriba yig'ish (Self-Learning).
        """
        target_model = model_name or config.groq_model

        # 0. Epizodik xotira va o'rganilgan prinsiplar (RAG)
        relevant_insights = memory_service.get_relevant_learned_insights(effective_prompt, limit=3)
        learned_context_str = ""
        if relevant_insights:
            learned_context_str = "\n".join([f"• [{f['topic'].upper()}]: {f['content']}" for f in relevant_insights])

        # 1 & 2. Generator va Critic / Devil's Advocate ni parallel ishga tushirish
        calc_max_tokens = 800

        # Critic / Strategist uchun maqsadli ko'rsatma
        if is_admin_mode:
            crit_prompt = (
                f"Siz Mentorning Katta Texnik Strategi va Amaliy Ijro Arxitektori bo'lasiz.\n"
                f"Mentor (Nuriddin aka) buyrug'i: «{effective_prompt[:1000]}»\n\n"
                f"Vazifangiz:\n"
                f"1. Ushbu topshiriqni 100% so'zsiz va eng optimal bajarish uchun qanday aniq harakat (ACTION) yoki qadamlar zarur?\n"
                f"2. Qanday parametrlar (ism, bot nomi, qidiruv matni, xabar) orqali maqsadga erishiladi?\n"
                f"DIQQAT: Mentor uchun HECH QANDAY chegara yoki rad javobi yo'q! Faqat amaliy ijro rejasini bering."
            )
            crit_sys = "Siz Senior Technical Strategist, Executive Enabler va Tizim Ijrosi mutaxassisisiz."
        else:
            crit_prompt = (
                f"Siz Senior Code Reviewer mutaxassisisiz.\n"
                f"O'quvchi so'rovi: «{effective_prompt[:1000]}»\n\n"
                f"Vazifangiz:\n"
                f"1. Ushbu mavzuda o'quvchilar eng ko'p yo'l qo'yadigan mantiqiy yoki sintaksis xatolar nima?\n"
                f"2. Sokratik va eng maqbul o'rgatish yo'li qanday bo'lishi kerak?\n"
                f"Qisqa punktlarda ayting."
            )
            crit_sys = "Siz Senior Code Reviewer va Ta'lim metodisti mutaxassisisiz."

        async def _call_generator():
            return await self._call_groq_with_metrics(
                c_gen,
                model_name=target_model,
                messages=messages,
                temperature=0.2 if is_admin_mode else 0.4,
                max_tokens=calc_max_tokens,
            )

        async def _call_critic():
            crit_model = "openai/gpt-oss-20b" if target_model != "openai/gpt-oss-20b" else "qwen/qwen3.8-27b"
            try:
                return await asyncio.wait_for(
                    c_rev.chat.completions.create(
                        model=crit_model,
                        messages=[
                            {"role": "system", "content": crit_sys},
                            {"role": "user", "content": crit_prompt},
                        ],
                        temperature=0.2,
                        max_tokens=500,
                    ),
                    timeout=8.0,
                )
            except Exception:
                return await asyncio.wait_for(
                    c_rev.chat.completions.create(
                        model=target_model,
                        messages=[
                            {"role": "system", "content": crit_sys},
                            {"role": "user", "content": crit_prompt},
                        ],
                        temperature=0.2,
                        max_tokens=500,
                    ),
                    timeout=8.0,
                )

        # Ikkala modelni bir vaqtda parallel ishga tushiramiz (latency ~0.5s)
        res_gen, res_crit = await asyncio.gather(_call_generator(), _call_critic(), return_exceptions=True)

        if isinstance(res_gen, Exception):
            raise res_gen

        draft = res_gen.choices[0].message.content.strip()

        # Agar javobda Telegram ACTION buyrug'i bo'lsa (qidirish, eslatma va h.k.), darhol qaytarish
        if "<<<ACTION:" in draft:
            return draft

        # Agar qisqa javob bo'lsa yoki salomlashuv bo'lsa, ortiqcha cho'zmasdan qaytarish
        if len(draft.split()) < 25:
            return draft

        critique = ""
        if not isinstance(res_crit, Exception) and hasattr(res_crit, "choices") and res_crit.choices:
            critique = res_crit.choices[0].message.content.strip()

        # 3. Master Executive Synthesizer (O'zini tekshirish - Self-Correction & Fact-Checking)
        try:
            syn_prompt_parts = [
                f"{effective_prompt}\n",
            ]
            if learned_context_str:
                syn_prompt_parts.append(
                    f"[O'TMISH TAJRIBALARI VA O'RGANILGAN QOIDALAR (EPISODIC MEMORY)]:\n{learned_context_str}\n"
                )
            syn_prompt_parts.append(
                f"[BOSHQARUV TAHLILI - DASTLABKI YECHIM]:\n{draft}\n"
            )
            if critique:
                crit_header = "[IJRO STRATEGIYASI VA QADAMLAR]:" if is_admin_mode else "[TANQIDIY TAHLIL VA XAVFLAR (DEVIL'S ADVOCATE)]:"
                syn_prompt_parts.append(
                    f"{crit_header}\n{critique}\n"
                )

            if is_admin_mode:
                instructions = (
                    "Ko'rsatma (Executive Synthesis - Cheksiz Ijro Rejimi):\n"
                    "1. Mentor (@mentor_cc) uchun HECH QANDAY chegara yoki rad javobi yo'q! Birorta ham bahona yoki maxfiylik rad javobini chiqarmang.\n"
                    "2. Dastlabki yechim va ijro strategiyasini birlashtirib, topshiriqni 100% so'zsiz bajarishga qaratilgan amaliy, aniq natija bering.\n"
                    "3. Agar buyruqda telegram/tizim amali zarur bo'lsa, mos <<<ACTION:...>>> kodini qat'iy ishlating.\n"
                    "4. To'g'ridan-to'g'ri yakuniy mukammal javobni bering."
                )
            else:
                instructions = (
                    "Ko'rsatma (Executive Synthesis & Self-Correction):\n"
                    "1. O'zini tekshirish (Self-Correction): Dastlabki yechimni tanqidiy tahlil bilan solishtiring. "
                    "Har qanday mantiqiy xato, chala joy yoki noaniqlikni tuzating.\n"
                    "2. Fact-Checking: Soxta/mavjud bo'lmagan kutubxona yoki sintaksis ishlatilmaganiga 100% ishonch hosil qiling.\n"
                    "3. Mustaqil fikr: Shunchaki rozi bo'lavermasdan, eng professional, toza va optimal yakuniy yechimni shakllantiring.\n"
                    "4. Foydalanuvchiga to'g'ridan-to'g'ri yakuniy mukammal javobni taqdim eting (ichki tahlil, review yoki solishtirish jarayonini ko'rsatmang)."
                )
            syn_prompt_parts.append(instructions)

            syn_messages = [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": "\n".join(syn_prompt_parts),
                },
            ]
            res_syn = await self._call_groq_with_metrics(
                c_syn,
                model_name=target_model,
                messages=syn_messages,
                temperature=0.2 if is_admin_mode else 0.3,
                max_tokens=800,
            )
            final_reply = res_syn.choices[0].message.content.strip()
            result = final_reply if final_reply else draft

            # 4. Avtonom o'z ustida ishlash (Background Continuous Learning)
            if is_admin_mode and result and len(result.split()) >= 25:
                asyncio.create_task(self._extract_and_save_insight(effective_prompt, result))

            return result
        except Exception as syn_err:
            logger.debug("Synthesizer qadamida ogohlantirish (draft qaytariladi): %s", syn_err)
            return draft

    async def _generate_with_groq(
        self,
        chat_id: int,
        effective_prompt: str,
        image_bytes: bytes | None = None,
        is_admin_mode: bool = False,
        pool_override: list[Any] | None = None,
        brain_type_override: str | None = None,
        is_administration_mode: bool = False,
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
            sys_prompt = self._build_system_prompt(
                is_admin_mode, effective_prompt=effective_prompt, is_administration_mode=is_administration_mode
            )
            messages = [{"role": "system", "content": sys_prompt}]

            prev_assistant = ""
            recent_history = history[-4:] if not is_admin_mode else history[-5:]
            for msg in recent_history:
                content_clean = msg.content.strip()
                if msg.role == "model":
                    # Agar ketma-ket bir xil assistant javobi bo'lsa, takrorlamaslik
                    if content_clean == prev_assistant:
                        continue
                    prev_assistant = content_clean
                role = "user" if msg.role == "user" else "assistant"
                # Tokenlar hajmi 413/429 limitiga urilmasligi uchun eski xabarlarni ixchamlashtirish
                compact_content = content_clean[:400] + ("..." if len(content_clean) > 400 else "")
                messages.append({"role": role, "content": compact_content})

            messages.append({"role": "user", "content": effective_prompt})

        # Adaptive Cognitive Gating (System 1 vs System 2):
        if pool_override:
            pool = pool_override
            brain_type = brain_type_override or "groq_reserve"
        else:
            pool, brain_type = self._get_active_pool(is_admin_mode)
        self._brain_stats[brain_type] = self._brain_stats.get(brain_type, 0) + 1
        is_student_group = (chat_id < 0 and not is_escalation_chat(chat_id))
        is_simple_query = (
            len(effective_prompt.split()) <= 4
            and any(w in effective_prompt.lower() for w in (
                "salom", "assalom", "privet", "zdravstvuyte", "rahmat", "spasibo",
                "ok", "tushundim", "ha", "yo'q", "yaxshi", "kimsan", "qayerdasan"
            ))
        )
        is_action_query = any(k in effective_prompt.lower() for k in (
            "kim yozdi", "kim yozgan", "oxirgi xabar", "eslat", "remind", "jadval",
            "lokatsiya", "turgan joy", "joylashuv", "statistika"
        ))
        is_pod_requested = any(k in effective_prompt.lower() for k in (
            "/deep", "konsilium", "pod tahlil", "chuqur tahlil", "arxitektura tahlili", "multi-agent"
        ))
        is_complex = (
            is_admin_mode
            and not image_bytes
            and not is_student_group
            and not is_simple_query
            and not is_action_query
            and len(pool) >= 3
            and is_pod_requested
        )

        if image_bytes:
            candidate_models = [config.groq_vision_model or "qwen/qwen3.8-27b"]
        else:
            candidate_models = []
            # Faqat Groq klasterida 100% mavjud va ishlaydigan haqiqiy modellar
            preferred = [
                config.groq_model or "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
                "qwen/qwen3.8-27b",
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

        # 1. Proactive Halving: Agar so'rov 3,500 tokendan oshsa, limitga yetmasdan oldin xotirani 2 ga bo'lish
        if est_tokens > 3500 and len(active_messages) > 3:
            logger.info("⚡ So'rov hajmi katta (%d token). Xotira 2 ga bo'linib, eng muhim qismlarga qisqartirildi.", est_tokens)
            # Tizim prompti (messages[0]) + oxirgi 2 ta xabar + joriy so'rov (messages[-1])
            active_messages = [active_messages[0]] + active_messages[-3:]
            est_tokens = self._estimate_tokens(active_messages)

        # Cooldown o'tgan kalitlar va modellarni avtomatik tiklash:
        self._refresh_key_and_model_recovery()

        # Cooldown muddati o'tmagan limitdagi modellarni o'tkazib yuborish (taymer uzayib ketmasligi uchun):
        cascade = self._brain_cascades.get(brain_type, self._brain_cascades.get("frontline", {}))
        now_ts = time.time()
        healthy_models = [
            m for m in candidate_models
            if cascade.get(m, {}).get("state") != "rate_limited" or now_ts >= cascade.get(m, {}).get("rate_limited_until", 0)
        ]
        candidate_models = healthy_models
        if not candidate_models:
            logger.info("⚠️ Ushbu miyada barcha Groq modellari hozirda cooldown limitida. Zaxira tizimiga o'tilmoqda...")
            raise RuntimeError("Barcha Groq modellari limitda.")

        # Kaskadli zaxira modellar bo'yicha ketma-ket urinish:
        for model_to_use in candidate_models:
            last_error = None
            # Ushbu modelni aktiv deb kaskadda qayd etish
            self._recalculate_cascade_states(brain=brain_type, active_override=model_to_use)

            # Kichik 8k kontekstli modellar (Gemma) limitiga urilmaslik uchun:
            if "gemma" in model_to_use.lower() and est_tokens > 7000:
                logger.info("Model [%s] 8k kontekst limiti sababli o'tkazib yuborildi (%d token).", model_to_use, est_tokens)
                continue

            # 1. 3 talik komanda (Pod Klaster) - faqat maxsus konsilium so'ralganda va faqat 1-urinishda
            if is_complex and len(pool) >= 3 and model_to_use == candidate_models[0]:
                if brain_type == "vip":
                    idx1 = self._vip_idx % len(pool)
                    idx2 = (self._vip_idx + 1) % len(pool)
                    idx3 = (self._vip_idx + 2) % len(pool)
                    self._vip_idx = (self._vip_idx + 3) % len(pool)
                elif brain_type == "groq_reserve":
                    idx1 = self._reserve_idx % len(pool)
                    idx2 = (self._reserve_idx + 1) % len(pool)
                    idx3 = (self._reserve_idx + 2) % len(pool)
                    self._reserve_idx = (self._reserve_idx + 3) % len(pool)
                else:
                    idx1 = self._frontline_idx % len(pool)
                    idx2 = (self._frontline_idx + 1) % len(pool)
                    idx3 = (self._frontline_idx + 2) % len(pool)
                    self._frontline_idx = (self._frontline_idx + 3) % len(pool)

                c_gen = pool[idx1]
                c_rev = pool[idx2]
                c_syn = pool[idx3]
                k_id1 = self._client_to_idx.get(id(c_gen), 0)
                k_id2 = self._client_to_idx.get(id(c_rev), 0)
                k_id3 = self._client_to_idx.get(id(c_syn), 0)

                team_num = (k_id1 // 3) + 1
                self._last_active_team_idx = team_num
                self._last_active_key_idx = k_id1
                self._mark_key_used(k_id1)
                self._mark_key_used(k_id2)
                self._mark_key_used(k_id3)
                logger.info(
                    "⚡ 3 talik komanda (Pod #%d, Miya: %s) ishga tushirildi: Model [%s], [Kalit %d, %d, %d]",
                    team_num, brain_type.upper(), model_to_use, k_id1 + 1, k_id2 + 1, k_id3 + 1,
                )
                try:
                    pod_result = await self._generate_with_groq_pod(
                        c_gen,
                        c_rev,
                        c_syn,
                        active_messages,
                        effective_prompt,
                        sys_prompt,
                        is_admin_mode,
                        model_name=model_to_use,
                    )
                    if pod_result and pod_result.strip():
                        return pod_result
                except Exception as pod_err:
                    logger.warning("Pod klasterida xatolik (%s): %s", model_to_use, pod_err)
                    last_error = pod_err
                    if "429" in str(pod_err) or "rate_limit_exceeded" in str(pod_err):
                        self._record_model_rate_limited(model_to_use, str(pod_err), brain=brain_type)
                        logger.warning("⚡ Model [%s] da Pod 429 limit bo'ldi. Darhol keyingi zaxira modelga o'tilmoqda...", model_to_use)
                        continue

            # 2. To'g'ridan-to'g'ri tezkor model chaqiruvi (Direct Fast Inference)
            calc_max_tokens = 800
            max_attempts = min(5, len(pool))
            model_success = False
            for _ in range(max_attempts):
                if brain_type == "vip":
                    curr_local_idx = self._vip_idx % len(pool)
                    self._vip_idx = (self._vip_idx + 1) % len(pool)
                elif brain_type == "groq_reserve":
                    curr_local_idx = self._reserve_idx % len(pool)
                    self._reserve_idx = (self._reserve_idx + 1) % len(pool)
                else:
                    curr_local_idx = self._frontline_idx % len(pool)
                    self._frontline_idx = (self._frontline_idx + 1) % len(pool)

                client = pool[curr_local_idx]
                k_real_idx = self._client_to_idx.get(id(client), 0)
                self._last_active_key_idx = k_real_idx
                self._last_active_team_idx = (k_real_idx // 3) + 1
                self._mark_key_used(k_real_idx)
                try:
                    response = await self._call_groq_with_metrics(
                        client,
                        model_name=model_to_use,
                        messages=active_messages,
                        temperature=0.2 if is_admin_mode else 0.4,
                        max_tokens=calc_max_tokens,
                    )
                    msg_obj = response.choices[0].message
                    content_str = (getattr(msg_obj, "content", "") or "").strip()
                    if not content_str and hasattr(msg_obj, "reasoning") and msg_obj.reasoning:
                        content_str = msg_obj.reasoning.strip()
                    if content_str:
                        model_success = True
                        return content_str
                except Exception as e:
                    logger.warning("Groq kalitida xatolik (model: %s, kalit #%d): %s", model_to_use, k_real_idx + 1, e)
                    last_error = e
                    if "model_not_found" in str(e) or "does not exist" in str(e) or "404" in str(e) or "400" in str(e):
                        logger.warning("⚡ Model [%s] mavjud emas yoki noto'g'ri so'rov (%s). Keyingi zaxira modelga o'tilmoqda...", model_to_use, e)
                        break
                    elif "429" in str(e) or "rate_limit_exceeded" in str(e):
                        # Har bir kalitning o'z mustaqil TPM/RPM limiti bor. Bitta kalit 429 bo'lsa, keyingi kalitni sinaymiz!
                        logger.info("⚡ Kalit #%d da 429 limit. Hovuzdagi keyingi kalit tekshirilmoqda...", k_real_idx + 1)
                        continue
                    elif "413" in str(e) and len(active_messages) > 2:
                        logger.warning("⚠️ 413 token limiti! Xotira 2 ga bo'linib qayta urinilmoqda...")
                        active_messages = [active_messages[0], active_messages[-1]]
                        calc_max_tokens = max(350, calc_max_tokens // 2)
                        try:
                            retry_resp = await self._call_groq_with_metrics(
                                client,
                                model_name=model_to_use,
                                messages=active_messages,
                                temperature=0.2 if is_admin_mode else 0.4,
                                max_tokens=calc_max_tokens,
                            )
                            msg_obj = retry_resp.choices[0].message
                            content_str = (getattr(msg_obj, "content", "") or "").strip()
                            if not content_str and hasattr(msg_obj, "reasoning") and msg_obj.reasoning:
                                content_str = msg_obj.reasoning.strip()
                            if content_str:
                                model_success = True
                                return content_str
                        except Exception as r_err:
                            logger.warning("Qisqartirilgan xotira bilan qayta urinishda ham xatolik: %s", r_err)
                            last_error = r_err

            # Agar bu modelda barcha sinab ko'rilgan kalitlar 429 limit bo'lsa, modelni kaskadda cooldown ga qo'yish
            if not model_success and last_error and ("429" in str(last_error) or "rate_limit_exceeded" in str(last_error)):
                self._record_model_rate_limited(model_to_use, str(last_error), brain=brain_type)
                logger.warning("⚡ Model [%s] bo'yicha barcha %d ta kalit sinovi limitga uchradi. Keyingi zaxira modelga o'tilmoqda...", model_to_use, max_attempts)
            else:
                logger.warning("⚠️ Model [%s] bo'yicha limit yoki xatolik yuz berdi. Keyingi zaxira modelga o'tilmoqda...", model_to_use)

        # Agar rasm hajmi tufayli 413 (rate_limit_exceeded) bo'lsa, yanada ixcham (640px) qilib qayta urinib ko'rish
        if image_bytes and last_error and ("rate_limit_exceeded" in str(last_error) or "413" in str(last_error)):
            logger.warning("Rasm hajmi oshdi (413), 640px ga yanada kichraytirib qayta urinilmoqda...")
            try:
                tiny_image = optimize_image_for_vision(image_bytes, max_dim=640, quality=65)
                tiny_b64 = base64.b64encode(tiny_image).decode("utf-8")
                messages[-1]["content"][1]["image_url"]["url"] = f"data:image/jpeg;base64,{tiny_b64}"
                for client in pool:
                    try:
                        response = await client.chat.completions.create(
                            model=config.groq_vision_model,
                            messages=messages,
                            temperature=0.3,
                            max_tokens=800,
                        )
                        return response.choices[0].message.content.strip()
                    except Exception:
                        continue
            except Exception as retry_err:
                logger.warning("Qayta urinishda xatolik: %s", retry_err)

        if last_error:
            raise last_error
        return "Javob olinmadi."

    def _build_system_prompt(self, is_admin_mode: bool, effective_prompt: str = "", is_administration_mode: bool = False) -> str:
        """Tizim promptini bilimlar bazasi va tanlangan mentorlik uslubi (persona) bilan boyitadi."""
        if is_administration_mode:
            sys_prompt = ADMINISTRATION_SYSTEM_PROMPT
            admin_dossier = memory_service.get_setting("admin_dossier_coddycamp_sergeli", "")
            if admin_dossier:
                sys_prompt = f"{sys_prompt}\n\n# CODDYCAMP MA'MURIYATI CHATI KOGNITIV TAHLILI (DOSYE):\n{admin_dossier}"
            return sys_prompt

        sys_prompt = ADMIN_SYSTEM_PROMPT if is_admin_mode else SYSTEM_PROMPT
        
        # Token Budgeting: 8k TPM limitiga sig'ish uchun faqat eng muhim dolzarb saboq va bilimlarni ulaymiz
        if effective_prompt and effective_prompt.strip():
            relevant = memory_service.get_relevant_learned_insights(effective_prompt, limit=2)
            if relevant:
                lines = ["# MENTORNING O'RGANILGAN QOIDALARI:"]
                for f in relevant:
                    lines.append(f"• [{f['topic'].upper()}]: {f['content']}")
                sys_prompt = f"{sys_prompt}\n\n" + "\n".join(lines)
            else:
                knowledge_context = memory_service.get_knowledge_context(limit=2)
                if knowledge_context:
                    sys_prompt = f"{sys_prompt}\n\n{knowledge_context}"
        else:
            knowledge_context = memory_service.get_knowledge_context(limit=2)
            if knowledge_context:
                sys_prompt = f"{sys_prompt}\n\n{knowledge_context}"

        # O'rganilgan eng muhim leksikon (maksimal 6 ta):
        lexicon_snippet = memory_service.get_lexicon_prompt_snippet(max_entries=6)
        if lexicon_snippet:
            sys_prompt = f"{sys_prompt}\n\n{lexicon_snippet}"

        # Eng muhim xatoliklar qoidalari (maksimal 3 ta):
        mistakes_snippet = memory_service.get_mistakes_prompt_snippet(max_rules=3)
        if mistakes_snippet:
            sys_prompt = f"{sys_prompt}\n\n{mistakes_snippet}"

        # Obsidian Vault'dagi mentor qoidalari (Human-in-the-loop):
        try:
            from services.obsidian_brain_service import obsidian_brain_service
            obsidian_rules = obsidian_brain_service.read_custom_rules()
            if obsidian_rules:
                obs_block = "\n".join(obsidian_rules[:4])
                sys_prompt = f"{sys_prompt}\n\n# OBSIDIAN VAULT QOIDALARI (MENTOR SOZLAMALARI):\n{obs_block}"
        except Exception:
            pass

        if is_admin_mode:
            try:
                now_tashkent = datetime.now(ZoneInfo("Asia/Tashkent"))
                h = now_tashkent.hour
                period_uz = "Erta tong" if 5 <= h < 11 else ("Kunduzi" if 11 <= h < 17 else ("Oqshom" if 17 <= h < 22 else "Tun"))
                time_block = (
                    f"\n\n# JORIY VAQT (Asia/Tashkent): {now_tashkent.strftime('%d.%m.%Y %H:%M')} ({period_uz})\n"
                    f"Eslatma: Mentor bilan salomlashganda joriy vaqtga mos ohangda javob bering!"
                )
                sys_prompt = f"{sys_prompt}{time_block}"
            except Exception:
                pass

        if not is_admin_mode:
            # O'quv markazining rasmiy steki (ixcham)
            curriculum_topics = memory_service.get_curriculum_topics()
            if curriculum_topics:
                topics_str = ", ".join(curriculum_topics[:12])
                curriculum_block = (
                    f"# CODDYCAMP RASMIY STEKI: [{topics_str}]. "
                    f"Dasturlash tushunchalarini markazimizning rasmiy steki (JavaScript/React/Node.js/MongoDB) bo'yicha tushuntiring."
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

            # Guruhlar va Ota-onalar bilan muloqot madaniyati:
            group_humor_block = (
                "# GURUH CHATLARI, OTA-ONALAR VA JONLI MULOQOT MADANIYATI:\n"
                "• Guruhda o'quvchilar bilan bir qatorda ota-onalar ham qatnashishadi. Ota-onalarga chuqur hurmat va ehtirom ko'rsating.\n"
                "• Hazillar va kulgili savollarda (😂, mashinalar, sovg'alar va h.k.) robotdek rad javobi bermang, samimiy tabassum bilan iliq javob bering.\n"
                "• Ustoz bergan ro'yxat (masalan mashina nomlari, mavzular) — bolalarning amaliy dasturlash vebsaytlari loyihasi mavzusidir. Buni tushunib munosabat bildiring."
            )
            sys_prompt = f"{sys_prompt}\n\n{group_humor_block}"

        return sys_prompt

    def _generate_with_genai(
        self,
        prompt: str,
        history_context: str,
        is_admin_mode: bool = False,
        image_bytes: bytes | None = None,
        is_administration_mode: bool = False,
    ) -> str:
        """Google GenAI orqali javob generatsiya qilish (fallback va Vision)."""
        from google.genai import types

        full_content = prompt
        if history_context:
            full_content = f"Avvalgi suhbat konteksti:\n{history_context}\n\nFoydalanuvchining yangi xabari:\n{prompt}"

        sys_prompt = self._build_system_prompt(is_admin_mode, effective_prompt=prompt, is_administration_mode=is_administration_mode)
        gemini_candidates = [
            config.gemini_model,
            "gemini-3-flash-preview",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
        ]
        unique_candidates = []
        for m in gemini_candidates:
            if m and m not in unique_candidates:
                unique_candidates.append(m)

        contents_payload = [full_content]
        if image_bytes:
            try:
                contents_payload.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
            except Exception as img_err:
                logger.warning("Gemini uchun rasm yuklashda ogohlantirish: %s", img_err)

        last_err = None
        for m in unique_candidates:
            try:
                response = self._gemini_client.models.generate_content(
                    model=m,
                    contents=contents_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt,
                        temperature=0.2 if is_admin_mode else 0.5,
                    ),
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as ge:
                last_err = ge
                logger.warning("Gemini modelida (%s) xatolik: %s", m, ge)
                continue
        if last_err:
            raise last_err
        return ""

    async def _generate_gemini_reply(
        self,
        chat_id: int,
        effective_prompt: str,
        is_admin_mode: bool = False,
        image_bytes: bytes | None = None,
        brain_tag: str = "reserve",
        is_administration_mode: bool = False,
    ) -> str | None:
        """Google Gemini zaxira miyasi orqali javob shakllantiradi va token metrikalarini qayd etadi."""
        if not self._gemini_client:
            return None
        try:
            logger.info("⚡ Google Gemini zaxira tizimi ishga tushirildi (vision=%s)...", bool(image_bytes))
            self._recalculate_cascade_states(active_override="Google Gemini")
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
                    None, self._generate_with_genai, effective_prompt, history_context, is_admin_mode, image_bytes, is_administration_mode
                ),
                timeout=20.0,
            )
            if answer and answer.strip():
                d_ms = int((time.time() - t_gem) * 1000)
                self._record_gemini_metrics(
                    len(effective_prompt) + len(history_context),
                    len(answer),
                    duration_ms=d_ms,
                    brain_tag=brain_tag,
                )
                logger.info("✅ Google Gemini zaxira tizimi orqali muvaffaqiyatli javob olindi.")
                return answer.strip()
        except Exception as gemini_err:
            logger.error("Gemini zaxira tizimida xatolik: %s", gemini_err)
        return None

    async def generate_reply(
        self,
        chat_id: int,
        user_message: str,
        reply_to_context: str | None = None,
        image_bytes: bytes | None = None,
        file_name: str | None = None,
        file_text: str | None = None,
        is_admin_mode: bool | None = None,
        is_administration_mode: bool = False,
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

        # Standart xatoliklarga (FAQ) 0.01 soniyada tezkor javob berish (faqat oddiy o'quvchilar uchun)
        if not is_admin_mode and not is_administration_mode and not file_text and not image_bytes:
            fast_faq = check_fast_faq(user_message)
            if fast_faq:
                logger.info("Fast FAQ mos keldi [%s], tezkor javob berildi.", chat_id)
                memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
                memory_service.add_message(chat_id=chat_id, role="model", content=fast_faq)
                return AIResult(fast_faq)

            # 0-Bosqich: Miya 5 (Avtonom Ong) oldindan keshlab qo'ygan yechimni tekshirish (0.02s - Limit sarflanmaydi)
            precomputed = memory_service.find_precomputed_answer(user_message)
            if precomputed:
                ans_text = precomputed.get("answer_text", "")
                if ans_text:
                    match_type = precomputed.get("match_type", "kesh")
                    logger.info("⚡ Miya 5 (Zero-Latency Cache Hit) qo'llanildi [%s: %s | %s]", chat_id, precomputed.get("topic"), match_type)
                    memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
                    memory_service.add_message(chat_id=chat_id, role="model", content=ans_text)
                    return AIResult(ans_text)

        # Javob berilayotgan kontekst
        effective_prompt = user_message
        if file_name and file_text:
            effective_prompt = f"[Yuklangan fayl: {file_name}]\n```\n{file_text[:6000]}\n```\n\n{effective_prompt}"

        if reply_to_context:
            effective_prompt = f"[Javob berilayotgan xabar: \"{reply_to_context}\"]\n{effective_prompt}"

        # 0.2-Bosqich: Universal Multi-Stack Linter (Python, JS, React, HTML, CSS, JSON)
        # O'quvchilar kodi xatoliklarini 0.005s da AI'siz, mutlaqo bepul va vizual ko'rsatkich bilan aniqlash
        # Mentor, Vazifalar guruhi va Ma'muriyat uchun 0 ta cheklov (mutlaq erkin, to'liq AI ishlaydi)
        if not is_admin_mode and not is_administration_mode and not image_bytes:
            try:
                from services.code_linter_service import check_code_snippets
                is_ru = is_russian_text(user_message)
                code_to_check = file_text if file_text else user_message
                lint_err, lint_topic = check_code_snippets(code_to_check, file_name=file_name, is_ru=is_ru)
                if lint_err:
                    logger.info("⚡ Universal Linter sintaksis xatosini aniqladi [%s: %s]", chat_id, lint_topic)
                    if lint_topic:
                        memory_service.record_student_topic_struggle(chat_id, lint_topic, user_message[:200])
                    memory_service.add_message(chat_id=chat_id, role="user", content=user_message)
                    memory_service.add_message(chat_id=chat_id, role="model", content=lint_err)
                    return AIResult(lint_err)
            except Exception as l_err:
                logger.warning("Universal Linter tekshiruvida ogohlantirish: %s", l_err)

        # Web Search & Rasmiy IT Dokumentatsiyalardan qidiruv (Real-time docs)
        web_search_enabled = memory_service.get_setting("web_search_enabled", "true").lower() == "true"
        if web_search_enabled and not image_bytes and user_message:
            clean_text = user_message.lower()
            from services.search_service import get_web_search_context, is_programming_query

            should_search = False
            if is_admin_mode or is_administration_mode:
                # Mentor yoki Ma'muriyat: mutlaq erkin, har qanday mavzuda
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
                    search_ctx = await get_web_search_context(user_message, is_admin=(is_admin_mode or is_administration_mode))
                    if search_ctx:
                        effective_prompt = f"{search_ctx}\n\n[Foydalanuvchi so'rovi]:\n{effective_prompt}"
                        logger.info("Web Search natijalari AI promptiga qo'shildi [%s]", chat_id)
                except Exception as s_err:
                    logger.warning("Web search qo'shishda ogohlantirish: %s", s_err)

        # 3-Mexanizm: O'quvchining Dinamik Xatolar Xaritasi (Student Weakness Profiling)
        # Faqat oddiy o'quvchilar uchun (Mentor, Vazifalar guruhi va Ma'muriyatga mutlaqo ta'sir qilmaydi)
        if not is_admin_mode and not is_administration_mode and user_message:
            try:
                topic = detect_programming_topic(user_message)
                if topic:
                    memory_service.record_student_topic_struggle(chat_id, topic, user_message)
                    weaknesses = memory_service.get_student_weaknesses(chat_id)
                    struggle_count = 0
                    for w in weaknesses:
                        if w.get("topic") == topic:
                            struggle_count = w.get("error_count", 0)
                            break
                    if struggle_count >= 2:
                        topic_names_uz = {
                            "loops": "Tsikllar (for, while)",
                            "functions": "Funksiyalar va return",
                            "data_structures": "Ma'lumotlar tuzilmasi (list, dict, set)",
                            "oop": "OOP (Klasslar va obyektlar)",
                            "syntax_indentation": "Sintaksis va Indentation (probellar)",
                            "exceptions": "Xatoliklarni ushlash (try/except)",
                            "file_io": "Fayllar bilan ishlash",
                        }
                        readable_topic = topic_names_uz.get(topic, topic)
                        cognitive_guidance = (
                            f"[Pedagogik Tavsiya: O'quvchi ushbu '{readable_topic}' mavzusida ilgari bir necha bor qiynalgan ({struggle_count} marta savol bergan). "
                            f"Unga murakkab texnik terminlarsiz, juda oddiy, hayotiy analogiya (o'xshatish) bilan bosqichma-bosqich, "
                            f"rag'batlantiruvchi tarzda tushuntiring.]"
                        )
                        effective_prompt = f"{cognitive_guidance}\n\n{effective_prompt}"
                        logger.info("🎯 O'quvchi kognitiv profili qo'llandi: chat_id=%s, mavzu=%s (xatolar: %d)", chat_id, topic, struggle_count)

                    # Mavzu bo'yicha eng samarali Oltin Standart analogiyani tekshirish
                    winning_analogy = memory_service.get_top_pedagogy_for_topic(topic)
                    if winning_analogy:
                        analogy_hint = f"[O'quvchilar eng yaxshi tushungan sinovdan o'tgan uslub: {winning_analogy[:200]}]"
                        effective_prompt = f"{analogy_hint}\n\n{effective_prompt}"

                # Pedagogical Outcome Tracker (Implicit RLHF)
                reaction = detect_student_feedback_reaction(user_message)
                if reaction:
                    hist = memory_service.get_history(chat_id)
                    last_model_msg = None
                    last_user_msg = None
                    for h in reversed(hist):
                        if h.role == "model" and not last_model_msg:
                            last_model_msg = h.content
                        elif h.role == "user" and not last_user_msg:
                            last_user_msg = h.content
                        if last_model_msg and last_user_msg:
                            break

                    cur_topic = topic or detect_programming_topic(last_user_msg or "") or "general"
                    if reaction == "confusion":
                        memory_service.record_pedagogical_outcome(chat_id, cur_topic, last_user_msg or "", last_model_msg or "", "confusion", user_message)
                        cognitive_adapt = (
                            f"[Pedagogik Qayta Tushuntirish: O'quvchi oldingi tushuntirishni tushunmadi ('{user_message}'). "
                            f"Oldingi uslubni TAKRORLAMANG! Mutlaqo boshqacha, bolalar tushunadigan juda sodda hayotiy analogiya bilan qisqa va tushunarli qilib qaytadan tushuntiring.]"
                        )
                        effective_prompt = f"{cognitive_adapt}\n\n{effective_prompt}"
                        logger.info("🔄 Pedagogik feedback: 'confusion' qayd etildi va javob soddalashtirildi [%s]", chat_id)
                    elif reaction == "success":
                        memory_service.record_pedagogical_outcome(chat_id, cur_topic, last_user_msg or "", last_model_msg or "", "success", user_message)
                        if last_model_msg and len(last_model_msg.split()) >= 15:
                            memory_service.save_high_yield_pedagogy(cur_topic, last_model_msg[:500])
                            logger.info("🏆 Pedagogik muvaffaqiyat: Oltin Standart saqlandi [%s: %s]", chat_id, cur_topic)

                # Miya 5: O'quvchi dosyesidan ichki kontekst olish (agar mavjud bo'lsa)
                dossier = memory_service.get_user_dossier(chat_id)
                if dossier and dossier.get("dossier_text"):
                    dossier_snippet = dossier["dossier_text"][:220].replace("\n", " ")
                    effective_prompt = f"[Suhbatdosh Kognitiv Ma'lumoti: {dossier_snippet}]\n\n{effective_prompt}"

            except Exception as prof_err:
                logger.warning("O'quvchi kognitiv tahlilida ogohlantirish: %s", prof_err)

        try:
            answer = None

            # Gemini sozlamalari (Kim uchun va nimadan keyin ishlashi)
            gemini_backup_enabled = memory_service.get_setting("gemini_backup_enabled", "true").lower() == "true"
            gemini_scope = memory_service.get_setting("gemini_scope", "all")
            gemini_trigger_after = memory_service.get_setting("gemini_trigger_after", "after_reserve")

            is_group_chat = (chat_id < 0)
            is_vazifalar = is_escalation_chat(chat_id)
            is_mentor = (chat_id in (config.mentor_user_id, 8105823872))
            is_vip = bool(is_admin_mode or is_vazifalar or is_mentor)

            def _is_gemini_allowed_for_request() -> bool:
                if not self._gemini_client or not gemini_backup_enabled:
                    return False
                if gemini_scope == "all":
                    return True
                elif gemini_scope == "vip_only":
                    return is_vip
                elif gemini_scope == "students_only":
                    return not is_vip
                elif gemini_scope == "mentor_only":
                    return is_mentor
                elif gemini_scope == "vazifalar_group_only":
                    return is_vazifalar
                elif gemini_scope == "groups_only":
                    return is_group_chat
                elif gemini_scope == "private_only":
                    return not is_group_chat
                elif gemini_scope == "students_dm_only":
                    return (not is_vip) and (not is_group_chat)
                elif gemini_scope == "vision_only":
                    return bool(image_bytes)
                return True

            # 0-ustuvorlik: Gemini Asosiy Miya sifatida (gemini_first / primary_first)
            # Har doim 1-o'rinda Google Gemini ishlaydi, Groq esa uning zaxirasi bo'lib turadi
            if not answer and gemini_trigger_after in ("gemini_first", "primary_first") and _is_gemini_allowed_for_request():
                logger.info("🥇 [gemini_first] Google Gemini Asosiy Miya (1-o'rinda) sifatida ishga tushirildi...")
                answer = await self._generate_gemini_reply(
                    chat_id, effective_prompt, is_admin_mode=is_admin_mode, image_bytes=image_bytes, brain_tag="reserve", is_administration_mode=is_administration_mode
                )

            # 0.5-ustuvorlik: Agar "vision_first" tanlangan bo'lsa va rasm bo'lsa, 1-o'rinda Gemini Vision ishlaydi
            if not answer and image_bytes and gemini_trigger_after == "vision_first" and _is_gemini_allowed_for_request():
                logger.info("🖼️ [vision_first] Rasm tahlili uchun to'g'ridan-to'g'ri 1-o'rinda Google Gemini Vision ishga tushirildi...")
                answer = await self._generate_gemini_reply(
                    chat_id, effective_prompt, is_admin_mode=is_admin_mode, image_bytes=image_bytes, brain_tag="reserve", is_administration_mode=is_administration_mode
                )

            # 0.7-ustuvorlik: Agar "smart_hybrid" tanlangan bo'lsa va VIP/Mentor yoki rasm bo'lsa, 1-o'rinda Gemini ishlaydi
            if not answer and (is_vip or image_bytes) and gemini_trigger_after == "smart_hybrid" and _is_gemini_allowed_for_request():
                logger.info("👑 [smart_hybrid] VIP/Murakkab so'rov uchun Gemini 1-o'rinda ishga tushirildi...")
                answer = await self._generate_gemini_reply(
                    chat_id, effective_prompt, is_admin_mode=is_admin_mode, image_bytes=image_bytes, brain_tag="reserve", is_administration_mode=is_administration_mode
                )

            # 1-ustuvorlik: Groq Birlamchi Miya (Miya 1: Frontline yoki Miya 2: VIP)
            if not answer and self._groq_clients:
                try:
                    answer = await asyncio.wait_for(
                        self._generate_with_groq(
                            chat_id, effective_prompt, image_bytes=image_bytes, is_admin_mode=is_admin_mode, is_administration_mode=is_administration_mode
                        ),
                        timeout=30.0,
                    )
                except Exception as groq_err:
                    logger.warning(
                        "⚠️ Groq asosiy miyasi (%s) limitga uchradi yoki xatolik: %s",
                        "VIP" if is_admin_mode else "Frontline",
                        groq_err,
                    )
                    answer = None

            # 2-ustuvorlik: Agar "after_primary" sozlamasi yoqilgan bo'lsa, asosiy miya to'lishi bilan darhol Gemini ishlaydi
            if not answer and gemini_trigger_after == "after_primary" and _is_gemini_allowed_for_request():
                logger.info("⚡ [after_primary] Asosiy miya to'ldi. Gemini'ga darhol o'tilmoqda (Groq Zaxira kutib o'tirilmaydi)...")
                answer = await self._generate_gemini_reply(
                    chat_id, effective_prompt, is_admin_mode=is_admin_mode, image_bytes=image_bytes, brain_tag="reserve", is_administration_mode=is_administration_mode
                )

            # 3-ustuvorlik: Miya 3: Groq Zaxira Qalqoni (12 ta kalit, Jamoalar #9-#12)
            # Agar "after_reserve" bo'lsa yoki oldingi bosqichlarda xatolik bo'lsa zaxira Groq ulanadi
            if not answer and self._reserve_clients and not image_bytes:
                try:
                    logger.info("🛡️ Miya 3: Groq Zaxira Qalqoni (12 ta kalit) yordamga ulandi...")
                    answer = await asyncio.wait_for(
                        self._generate_with_groq(
                            chat_id,
                            effective_prompt,
                            image_bytes=image_bytes,
                            is_admin_mode=is_admin_mode,
                            pool_override=self._reserve_clients,
                            brain_type_override="groq_reserve",
                            is_administration_mode=is_administration_mode,
                        ),
                        timeout=30.0,
                    )
                    if answer:
                        logger.info("✅ Groq Zaxira Qalqoni orqali muvaffaqiyatli javob olindi.")
                except Exception as res_err:
                    logger.warning(
                        "⚠️ Groq Zaxira Qalqoni ham to'ldi yoki xatolik: %s",
                        res_err,
                    )
                    answer = None

            # 4-ustuvorlik: Google Gemini (Temir Zaxira - 1 million token limit)
            # Standart "after_reserve", "smart_hybrid" yoki yuqoridagi barcha miyalar to'lganda so'nggi istehkom
            if not answer and _is_gemini_allowed_for_request():
                if gemini_trigger_after != "vision_only_trigger" or image_bytes or file_text:
                    logger.info("⚡ So'nggi istehkom: Google Gemini zaxira tizimi ulanmoqda (scope=%s, trigger=%s)...", gemini_scope, gemini_trigger_after)
                    answer = await self._generate_gemini_reply(
                        chat_id, effective_prompt, is_admin_mode=is_admin_mode, image_bytes=image_bytes, brain_tag="reserve", is_administration_mode=is_administration_mode
                    )

            if not answer:
                answer = "Hozirda tizimda yuklama yuqori bo'lgani sababli javob bera olmadim. Iltimos, 1 daqiqadan so'ng qayta urinib ko'ring! ⏳"

            # Eskalyatsiya blokini ajratish
            escalation_info = None
            match = ESCALATE_PATTERN.search(answer)
            if match:
                escalation_info = (match.group(1) or match.group(2) or "").strip()
                answer = ESCALATE_PATTERN.sub("", answer).strip()

            # Qolgan har qanday ochiq yoki buzilgan eskalatsiya teglari o'quvchiga ko'rinib qolmasligi uchun tozalash
            answer = re.sub(r"<+/?(?:END_)?ESCALATE>+", "", answer, flags=re.IGNORECASE).strip()
            answer = re.sub(r"(?:Sabab|Reason|Причина):\s*Dasturlashga aloqador bo'lmagan.*", "", answer, flags=re.IGNORECASE).strip()

            # Maxfiy ma'lumotlarni tozalash (Data Leak Prevention)
            answer = redact_sensitive_data(answer)
            if escalation_info:
                escalation_info = redact_sensitive_data(escalation_info)

            # Begona mavzu yoki CoddyCamp ta'lim doirasidan tashqari murojaatlarda
            # foydalanuvchiga mentorga yetkazilganini bildirish va Vazifalar guruhiga uzatish (faqat oddiy o'quvchilar uchun)
            if not is_admin_mode and not is_administration_mode:
                off_topic_patterns = [
                    r"CoddyCamp dasturlash ta['’`]?limi bo['’`]?yicha yordam beraman",
                    r"darslarimiz haqida gaplashaylik",
                    r"обучени[юя]\s+программированию\s+в\s+CoddyCamp",
                    r"поговорим\s+о\s+наших\s+уроках",
                ]
                if any(re.search(pat, answer, re.IGNORECASE) for pat in off_topic_patterns):
                    if not any(k in answer.lower() for k in ["yetkazdim", "xabar qildim", "передал", "сообщил"]):
                        if is_russian_text(answer):
                            answer = f"{answer} Я также передал ваше сообщение нашему ментору (Нуриддину)."
                        else:
                            answer = f"{answer} Ushbu xabaringizni mentorimizga (Nuriddin akaga) ham yetkazdim."
                    if not escalation_info:
                        escalation_info = "Dasturlashga aloqador bo'lmagan yoki begona mavzuda murojaat"

                # Agar model o'quvchiga ustozni ogohlantirdim degan bo'lsa (tag qo'yishni unutgan bo'lsa ham)
                mention_mentor_phrases = [
                    r"mentorimizga\s+.*?yetkazdim",
                    r"ustozga\s+.*?yetkazdim",
                    r"ustozni\s+ogohlantirdim",
                    r"nuriddin\s+akaga\s+.*?yetkazdim",
                    r"наставнику\s+.*?передал",
                    r"передал\s+.*?учителю",
                    r"передал\s+.*?наставнику",
                    r"сообщил\s+.*?наставнику",
                    r"сообщил\s+.*?учителю",
                ]
                if any(re.search(p, answer, re.IGNORECASE) for p in mention_mentor_phrases):
                    if not escalation_info:
                        escalation_info = "AI o'quvchiga ustozga xabar yetkazilganini bildirdi"

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

            # 4-Mexanizm: "Critic" Pedagogik Sifat Nazoratchisi (Self-Correction & Socratic Hint Enforcement)
            # Faqat o'quvchilar uchun! (Mentor va Vazifalar guruhiga 0 cheklov - 100% to'liq javob va kod)
            if not is_admin_mode:
                answer = apply_socratic_critic(answer, user_message)

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

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients

        models_to_try = []
        for m in [config.groq_model or "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            for _ in range(len(pool)):
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.4,
                        max_tokens=800,
                    )
                    ans = response.choices[0].message.content.strip()
                    return redact_sensitive_data(ans)
                except Exception as e:
                    logger.warning("Mavzu tushuntirishda xatolik (%s): %s", model_name, e)

        return "⚠️ Mavzuni tushuntirishda xatolik yuz berdi. Iltimos qayta urinib ko'ring."

    async def compile_admin_intent(self, user_command: str) -> str:
        """
        Mentorning tabiiy tilda, jargon yoki so'zlashuv uslubida bergan buyrug'ini
        algoritm tushunadigan aniq <<<ACTION:...>>> buyrug'iga o'girib beradi.
        0 cheklov, 0 rad javobi.
        """
        raw = (user_command or "").strip()
        if not raw:
            return "NONE"

        sys_msg = (
            "Siz CoddyCamp Vazifalar Boshqaruv Markazi uchun Buyruqlar Kompilyatori (Intent Compiler)siz.\n"
            "Mentor (@mentor_cc) o'zbekcha / ruscha erkin tilda, jargon yoki so'zlashuv uslubida buyruq berdi:\n"
            f"«{raw}»\n\n"
            "Vazifangiz — mentor so'zlaridan uning niyatini (intent) anglab, uni algoritm tushunadigan aniq ACTION buyrug'iga o'girib berish.\n\n"
            "Mavjud Tizim Amallari:\n"
            "• O'quvchi, profil, kontakt, lichka, nomer yoki uydagilarini qidirish/topish:\n"
            "  <<<ACTION:find_contact(\"ism\")>>>\n"
            "• Shaxsiy yozishmalar (lichkalar) yoki guruhlardan kasal bo'lgan / dars qoldirgan / betob o'quvchilarni topish:\n"
            "  <<<ACTION:find_sick_students()>>>\n"
            "• Xabar yuborish (shaxsga, botga, guruhga):\n"
            "  <<<ACTION:send_message(\"qabul_qiluvchi\", \"xabar_matni\")>>>\n"
            "• Eslatma yoki vaqtli xabar rejalashtirish:\n"
            "  <<<ACTION:schedule_message(\"qabul_qiluvchi\", \"matn\", \"vaqt\")>>>\n"
            "• Telegramdan xabarlarni qidirish:\n"
            "  <<<ACTION:search_telegram(\"qidiruv\")>>>\n"
            "• Aniq guruh yoki chat ichidan xabar qidirish:\n"
            "  <<<ACTION:search_chat(\"chat\", \"qidiruv\")>>>\n"
            "• Guruh ma'lumotlari yoki bolalar soni:\n"
            "  <<<ACTION:get_group_info(\"guruh\")>>>\n"
            "• Oxirgi yozganlar / kelgan xabarlar:\n"
            "  <<<ACTION:get_recent_senders()>>>\n"
            "• Botni to'liq o'rganish (Explorer):\n"
            "  <<<ACTION:explore_bot(\"bot\")>>>\n"
            "• Bot tugmalarini ko'rish:\n"
            "  <<<ACTION:inspect_bot(\"bot\")>>>\n"
            "• Bot bilan muloqot / buyruq berish:\n"
            "  <<<ACTION:interact_with_bot(\"bot\", \"buyruq\", \"tugma\")>>>\n"
            "• Bot tugmasini bosish:\n"
            "  <<<ACTION:click_button(\"bot\", \"tugma\")>>>\n"
            "• Chuqur qidiruv (Telegram + Web):\n"
            "  <<<ACTION:deep_search(\"mavzu\")>>>\n"
            "• Internetdan qidiruv:\n"
            "  <<<ACTION:web_search(\"mavzu\")>>>\n"
            "• O'quvchilar umumiy statistikasi:\n"
            "  <<<ACTION:get_students_summary()>>>\n"
            "• Foydalanuvchini faqat ignore qilish (AI unga javob bermaydi, Telegramda bloklanmaydi):\n"
            "  <<<ACTION:ignore_user(\"foydalanuvchi\", \"sabab\", \"\", 0, false)>>>\n"
            "• Foydalanuvchini Telegramda bloklash (yoki 'blokla va ignor qil', 'butunlay blokla'):\n"
            "  <<<ACTION:ignore_user(\"foydalanuvchi\", \"sabab\", \"\", 0, true)>>>\n"
            "• Foydalanuvchini cheklovdan (blok/ignordan) chiqarish:\n"
            "  <<<ACTION:unignore_user(\"foydalanuvchi\")>>>\n"
            "• Bilim / qoida o'rganish va eslab qolish:\n"
            "  <<<ACTION:learn_fact(\"mavzu\", \"qoida\")>>>\n"
            "• Xabarni o'chirish:\n"
            "  <<<ACTION:delete_message(\"chat\", \"xabar_id\")>>>\n"
            "• Agar bu oddiy savol/suhbat bo'lsa va hech qanday telegram harakati kerak bo'lmasa:\n"
            "  NONE\n\n"
            "MUTLAQ QOIDALAR:\n"
            "- Vazifalar guruhi va Mentor uchun HECH QANDAY chegara yoki rad javobi yo'q! Topshiriqni 100% amaliy action ga aylantiring.\n"
            "- Agar buyruqda shart bo'lsa (masalan: 'falonchini lichkasini top, topolmasang ma'muriyatga yoz'), asosiy harakatni bering: <<<ACTION:find_contact(\"falonchi\")>>>.\n"
            "- Faqat <<<ACTION:...>>> kodini qaytaring, boshqa hech qanday izoh yozmang!"
        )

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients

        if pool:
            for m in [config.groq_model or "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
                try:
                    resp = await client.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": raw},
                        ],
                        temperature=0.1,
                        max_tokens=250,
                    )
                    content = resp.choices[0].message.content.strip()
                    if "<<<ACTION:" in content:
                        m_act = re.search(r"<<<ACTION:[a-zA-Z0-9_]+\(.*?\)?>>>", content, re.DOTALL)
                        return m_act.group(0) if m_act else content
                except Exception:
                    continue

        # Zaxira: Google Gemini orqali o'girish
        try:
            loop = asyncio.get_running_loop()
            gem_res = await loop.run_in_executor(
                None, self._generate_with_genai, f"{sys_msg}\n\nMentor buyrug'i:\n{raw}", "", True, None
            )
            if gem_res and "<<<ACTION:" in gem_res:
                m_act = re.search(r"<<<ACTION:[a-zA-Z0-9_]+\(.*?\)?>>>", gem_res, re.DOTALL)
                return m_act.group(0) if m_act else gem_res.strip()
        except Exception:
            pass

        return "NONE"

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

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients

        models_to_try = []
        for m in [config.groq_model or "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        for model_name in models_to_try:
            for _ in range(len(pool)):
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
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

    async def _polish_voice_transcription(self, raw_text: str, detected_lang: str = "") -> str:
        """
        STT transkripsiyasidagi turkcha aralashmalarni, fonetik xatoliklarni va noaniqliklarni
        tozalab, o'quvchi yoki ustoz aytgan haqiqiy toza nutqni (UZ/RU/EN) 100% tiklaydi.
        """
        if not raw_text or len(raw_text.strip()) < 3:
            return raw_text

        turkish_markers = (
            "öğretmen", "yapıyorum", "geliyorum", "lütfen", "merhaba", "dersime",
            "ödev", "hastayım", "nasılsınız", "hocam", "böyle", "şimdi", "görüşürüz",
            "tamam mı", "ben ", " benim", " dersler", "derse "
        )
        has_turkish = any(tm in raw_text.lower() for tm in turkish_markers) or detected_lang in ("tr", "turkish", "az", "tk")
        if not has_turkish:
            return raw_text.strip()

        logger.info("🧹 Audio transkripsiyasidagi turkcha so'zlarni tozalash (Polish) boshlandi: %s", raw_text[:50])
        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            return raw_text.strip()

        client = pool[self._frontline_idx % len(pool)]
        self._frontline_idx = (self._frontline_idx + 1) % len(pool)

        prompt = (
            "Siz CoddyCamp IT akademiyasining audio-transkripsiya muharririsiz.\n"
            "Ushbu matn o'quvchi tomonidan O'ZBEK tilida aytilgan ovozli xabardan olingan, "
            "lekin STT (audio model) uni xato ravishda turkcha so'zlarga aylantirib yuborgan:\n"
            f"«{raw_text}»\n\n"
            "VAZIFA:\n"
            "1. Barcha turkcha so'zlarni (öğretmenim -> ustoz, derse gelemiyorum -> darsga kela olmayman, "
            "hastayım -> mazam yo'q/kasalman, ödev -> vazifa, ben -> men, lütfen -> iltimos va h.k.) "
            "tabiiy o'zbek tiliga o'giring.\n"
            "2. O'quvchining asl maqsadi va to'liq gaplarini 100% sof va tiniq o'zbekcha qilib tiklang.\n"
            "3. Faqat to'g'rilangan matnning o'zini qaytaring, boshqa hech qanday izoh, belgi yoki kirish yozmang!"
        )
        try:
            polish_model = "openai/gpt-oss-20b"
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=polish_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                ),
                timeout=5.0
            )
            cleaned = resp.choices[0].message.content.strip()
            if cleaned:
                if cleaned.startswith("«") and cleaned.endswith("»"):
                    cleaned = cleaned[1:-1].strip()
                if cleaned.startswith('"') and cleaned.endswith('"'):
                    cleaned = cleaned[1:-1].strip()
                logger.info("✅ Audio transkripsiyasi tozalandi: %s", cleaned[:70])
                return cleaned
        except Exception as p_err:
            logger.warning("Audio matnini tozalashda xatolik: %s", p_err)

        return raw_text.strip()

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Ovozli xabarni matnga o'giradi (Multi-Tier Kaskad - UZ, RU, EN):
        1-bosqich: Google Gemini 3 Flash Preview (Multimodal Audio, eng yuqori aniqlik)
        2-bosqich: Groq Whisper Large v3 (verbose_json + turkcha adashganda majburiy uz tili)
        3-bosqich: Groq LLM Polish (Agar turkcha qoldiqlar bo'lsa, 100% sof o'zbekchaga tiklash)
        """
        if not audio_bytes:
            return ""

        # 1-bosqich: Google Gemini Multimodal Audio (Eng yuqori aniqlik, 0 turkcha adashish)
        if self._gemini_client:
            gem_candidates = [
                getattr(config, "gemini_model", "gemini-3-flash-preview") or "gemini-3-flash-preview",
                "gemini-3-flash-preview",
                "gemini-flash-latest",
            ]
            seen_models = set()
            for gem_model in gem_candidates:
                if gem_model in seen_models:
                    continue
                seen_models.add(gem_model)
                try:
                    logger.info("🎙️ Google Gemini (%s) orqali ovozli xabar transkripsiyasi boshlandi...", gem_model)
                    from google.genai import types
                    loop = asyncio.get_running_loop()

                    def _gemini_transcribe(m=gem_model):
                        resp = self._gemini_client.models.generate_content(
                            model=m,
                            contents=[
                                types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                                (
                                    "Siz O'zbekiston, Toshkentdagi CoddyCamp dasturlash akademiyasi uchun professional audio transkripsiyachisiz.\n"
                                    "Ushbu ovozli xabarni (audio) juda diqqat bilan eshiting.\n\n"
                                    "QAT'IY QOIDALAR:\n"
                                    "1. Ushbu audio O'ZBEKCHA (o'zbek tili, Toshkent og'zaki nutqi), RUSCHA yoki INGLIZCHA nutqdir.\n"
                                    "2. O'zbek tilidagi nutqni aslo TURKCHA (Turkish) deb xato o'ylamang! Bu turk tili emas, O'ZBEK TILI.\n"
                                    "3. So'zlashuvchi aytgan har bir so'zni 100% tiniq, to'liq va aniq qilib so'zma-so'z matnga o'giring (Transkripsiya).\n"
                                    "4. Hech qanday qo'shimcha so'z, kirish, xulosa yoki izoh yozmang. Faqat to'g'ridan-to'g'ri eshitilgan haqiqiy nutq matnini qaytaring."
                                )
                            ],
                        )
                        return resp.text.strip() if resp and resp.text else ""

                    gemini_text = await asyncio.wait_for(loop.run_in_executor(None, _gemini_transcribe), timeout=8.0)
                    if gemini_text:
                        logger.info("✅ Google Gemini orqali ovozli xabar 100% tiniq o'qildi: %s", gemini_text[:80])
                        return await self._polish_voice_transcription(gemini_text)
                    break
                except Exception as gem_err:
                    logger.warning("Google Gemini (%s) transkripsiyasida ogohlantirish: %s", gem_model, gem_err)
                    if "503" in str(gem_err) or "404" in str(gem_err):
                        continue
                    break

        # 2-bosqich: Groq Whisper zaxirasi
        multilingual_prompt = (
            "O'zbekiston, Toshkent, CoddyCamp dasturlash akademiyasi. Bu audio O'zbek tilida (yoki rus/ingliz). "
            "Assalomu alaykum ustoz, dars, uyga vazifa, topshiriq, o'quvchi, darsga kechikaman, kasalman, kela olmayman, kod, dasturlash, Python, CoddyCamp, Rustamjon, Amirbek. "
            "Здравствуйте учитель, урок, домашнее задание, опоздаю, не смогу прийти, заболел, код, ошибка, проект. "
            "Hello teacher, lesson, homework, coding, class, late, project."
        )
        hallucinations = ("subtitles by", "amara.org", "sous-titres", "transcription par", "thank you for watching")
        turkish_markers = (
            "öğretmen", "yapıyorum", "geliyorum", "lütfen", "merhaba", "dersime",
            "ödev", "hastayım", "nasılsınız", "hocam", "böyle", "şimdi", "görüşürüz",
            "tamam mı", "ben ", " benim", " dersler", "derse "
        )

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if pool:
            for _ in range(min(5, len(pool))):
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
                try:
                    transcription = await client.audio.transcriptions.create(
                        file=("voice.ogg", audio_bytes),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                        prompt=multilingual_prompt,
                        temperature=0.0,
                    )
                    det_lang = str(getattr(transcription, "language", "") or "").lower()
                    text = str(getattr(transcription, "text", transcription)).strip()

                    if any(h in text.lower() for h in hallucinations) and len(text) < 45:
                        text = ""

                    # Agar Whisper o'zbekchani turkcha yoki boshqa turkiy til deb o'ylagan bo'lsa:
                    is_turkish = (
                        det_lang in ("tr", "turkish", "az", "azerbaijani", "tk", "turkmen", "kk", "kazakh", "ky", "kyrgyz")
                        or any(tm in text.lower() for tm in turkish_markers)
                    )
                    if is_turkish and audio_bytes:
                        logger.warning("⚠️ Whisper o'zbekcha nutqni turkcha deb o'yladi (det_lang=%s), darhol language='uz' bilan majburiy qayta o'qilmoqda...", det_lang)
                        uz_prompt = (
                            "Assalomu alaykum ustoz, CoddyCamp dasturlash maktabi. Bugun darsga kela olmayman, kechikaman, kasalman, mazam yo'q, uyga vazifa, topshiriq, kod, o'quvchi."
                        )
                        try:
                            trans_uz = await client.audio.transcriptions.create(
                                file=("voice.ogg", audio_bytes),
                                model="whisper-large-v3",
                                language="uz",
                                prompt=uz_prompt,
                                temperature=0.0,
                            )
                            uz_text = str(getattr(trans_uz, "text", trans_uz)).strip()
                            if uz_text and len(uz_text) > 3:
                                text = uz_text
                                det_lang = "uz"
                                logger.info("✅ language='uz' bilan muvaffaqiyatli transkripsiya qilindi: %s", text[:80])
                        except Exception as uz_err:
                            logger.warning("language='uz' bilan transkripsiyada xatolik: %s", uz_err)

                    if text:
                        polished = await self._polish_voice_transcription(text, detected_lang=det_lang)
                        logger.info("✅ Groq Whisper (Frontline) ovozli xabarni matnga aylantirdi: %s", polished[:80])
                        return polished
                except Exception as e:
                    logger.warning("Groq Whisper (Frontline) xatolik, keyingi kalitga o'tilmoqda: %s", e)

        # 3-bosqich: Groq Zaxira Qalqoni orqali urinish
        if self._reserve_clients:
            for _ in range(min(3, len(self._reserve_clients))):
                client = self._reserve_clients[self._reserve_idx % len(self._reserve_clients)]
                self._reserve_idx = (self._reserve_idx + 1) % len(self._reserve_clients)
                try:
                    transcription = await client.audio.transcriptions.create(
                        file=("voice.ogg", audio_bytes),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                        prompt=multilingual_prompt,
                        temperature=0.0,
                    )
                    det_lang = str(getattr(transcription, "language", "") or "").lower()
                    text = str(getattr(transcription, "text", transcription)).strip()

                    if any(h in text.lower() for h in hallucinations) and len(text) < 45:
                        text = ""

                    is_turkish = (
                        det_lang in ("tr", "turkish", "az", "azerbaijani", "tk", "turkmen")
                        or any(tm in text.lower() for tm in turkish_markers)
                    )
                    if is_turkish and audio_bytes:
                        try:
                            trans_uz = await client.audio.transcriptions.create(
                                file=("voice.ogg", audio_bytes),
                                model="whisper-large-v3",
                                language="uz",
                                prompt="Assalomu alaykum ustoz, CoddyCamp dasturlash. Darsga kela olmayman, kasalman, vazifa, topshiriq.",
                                temperature=0.0,
                            )
                            uz_text = str(getattr(trans_uz, "text", trans_uz)).strip()
                            if uz_text:
                                text = uz_text
                                det_lang = "uz"
                        except Exception:
                            pass

                    if text:
                        polished = await self._polish_voice_transcription(text, detected_lang=det_lang)
                        logger.info("🛡️ Groq Whisper (Zaxira Qalqoni) ovozli xabarni matnga aylantirdi: %s", polished[:80])
                        return polished
                except Exception as e:
                    logger.warning("Groq Whisper (Zaxira Qalqoni) xatolik: %s", e)

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

        pool = self._vip_clients if self._vip_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._vip_clients if self._vip_clients else self._groq_clients

        for _ in range(len(pool)):
            client = pool[self._vip_idx % len(pool)]
            self._vip_idx = (self._vip_idx + 1) % len(pool)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=800,
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

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients

        for _ in range(len(pool)):
            client = pool[self._frontline_idx % len(pool)]
            self._frontline_idx = (self._frontline_idx + 1) % len(pool)
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

        pool = self._frontline_clients if self._frontline_clients else self._groq_clients
        if not pool:
            self._setup_clients()
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients

        for _ in range(len(pool)):
            client = pool[self._frontline_idx % len(pool)]
            self._frontline_idx = (self._frontline_idx + 1) % len(pool)
            try:
                response = await client.chat.completions.create(
                    model=config.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=800,
                )
                return redact_sensitive_data(response.choices[0].message.content.strip())
            except Exception as e:
                logger.warning("GitHub tahlilida xatolik: %s", e)

        return "⚠️ GitHub repozitoriysini tahlil qilishda xatolik yuz berdi."

    async def extract_name_and_group_from_reply(self, reply_text: str) -> dict[str, str]:
        """
        O'quvchining ism va guruhi haqidagi javobidan to'liq ism va guruh nomini ajratib oladi.
        Masalan: 'Mening ismim Bobur Xoliqov, 14:00 guruhi' -> {'name': 'Bobur Xoliqov', 'group': '14:00 guruhi'}
        """
        raw = (reply_text or "").strip()
        if not raw:
            return {"name": "", "group": ""}

        prompt = (
            "Foydalanuvchi (o'quvchi) o'z ismi va guruhi haqida quyidagi xabarni yubordi:\n"
            f"«{raw}»\n\n"
            "Ushbu matndan o'quvchining haqiqiy to'liq ismini (Ism Familiya) va o'qiydigan guruhini ajratib oling.\n"
            "Faqat quyidagi JSON formatida javob bering, boshqa hech narsa yozmang:\n"
            '{"name": "Ism Familiya", "group": "Guruh nomi yoki dars vaqti"}'
        )
        try:
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients
            if pool:
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
                resp = await client.chat.completions.create(
                    model=config.groq_model or "llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=150,
                    response_format={"type": "json_object"}
                )
                import json
                parsed = json.loads(resp.choices[0].message.content.strip())
                if isinstance(parsed, dict):
                    return {
                        "name": (parsed.get("name") or "").strip(),
                        "group": (parsed.get("group") or "").strip(),
                    }
        except Exception as e:
            logger.debug("AI orqali ism/guruh ajratishda ogohlantirish: %s", e)

        # Fallback: regex
        m_name = re.search(r"\b([A-Z\u0410-\u042F][a-z\u0430-\u044F\']+(?:\s+[A-Z\u0410-\u042F][a-z\u0430-\u044F\']+)?)\b", raw)
        name_val = m_name.group(1).title() if m_name else raw
        m_grp = re.search(r"([A-Za-z0-9_\s\u0400-\u04FF]+?)\s+guruh(?:i|idan)?\b", raw, re.I)
        grp_val = m_grp.group(1).strip() if m_grp else ""
        return {"name": name_val, "group": grp_val}

    async def verify_inquiry_answer(
        self, question: str, expected_info: str, reply_text: str
    ) -> dict[str, Any]:
        """
        Kutilayotgan so'rov (inquiry) savoliga olingan javobning mantiqan to'g'ri va mosligini tekshiradi.
        Qaytaradi:
        {
            "is_relevant": bool,
            "extracted_answer": str,
            "clarification_needed": bool,
            "polite_followup": str
        }
        """
        raw = (reply_text or "").strip()
        if not raw:
            return {
                "is_relevant": False,
                "extracted_answer": "",
                "clarification_needed": True,
                "polite_followup": "Kechirasiz, javobingizni tushuna olmadim. Iltimos, batafsilroq yozib yubora olasizmi? 😊",
            }

        prompt = (
            "Siz CoddyCamp yordamchi agentisiz. Suhbatdoshga oldinroq quyidagi savol berilgan edi:\n"
            f"❓ Berilgan savol: «{question}»\n"
            f"🎯 Kutilayotgan ma'lumot (maqsad): «{expected_info}»\n\n"
            f"Suhbatdoshdan kelgan javob xabari:\n«{raw}»\n\n"
            "Vazifangiz ushbu javobni tahlil qilish:\n"
            "1. 'is_relevant': Javob berilgan savolga mantiqan mos keladimi va kutilayotgan ma'lumotni o'z ichiga oladimi? (true yoki false)\n"
            "   (Agar javob salomlashish, tushunarsiz stiker/emoji yoki mavzudan mutlaqo yiroq bo'lsa -> false)\n"
            "   (Agar javob savolga mantiqiy javob bersa, masalan 'ha', 'yo\\'q', 'ertaga kela olmayman', 'bormayman', 'kechikaman', 'tayyor' -> true)\n"
            "2. 'extracted_answer': Suhbatdosh javobining qisqa, aniq xulosasi (masalan: 'Ertaga darsga kela olmaydi', 'Soat 15:00 da keladi', 'Vazifani tugatgan').\n"
            "3. 'clarification_needed': Agar javob noaniq bo'lsa yoki savolga javob berilmagan bo'lsa -> true, aks holda false.\n"
            "4. 'polite_followup': Agar clarification_needed true bo'lsa, o'quvchiga savolni muloyimlik bilan eslatib, aniqlashtirish so'rovchi qisqa xabar matni (o'zbek tilida). Agar is_relevant true bo'lsa bo'sh qoldiring.\n\n"
            "Faqat quyidagi JSON formatida javob bering:\n"
            "{\n"
            '  "is_relevant": true,\n'
            '  "extracted_answer": "...",\n'
            '  "clarification_needed": false,\n'
            '  "polite_followup": ""\n'
            "}"
        )

        try:
            pool = self._frontline_clients if self._frontline_clients else self._groq_clients
            if pool:
                client = pool[self._frontline_idx % len(pool)]
                self._frontline_idx = (self._frontline_idx + 1) % len(pool)
                resp = await client.chat.completions.create(
                    model=config.groq_model or "llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=250,
                    response_format={"type": "json_object"}
                )
                import json
                parsed = json.loads(resp.choices[0].message.content.strip())
                if isinstance(parsed, dict):
                    return {
                        "is_relevant": bool(parsed.get("is_relevant")),
                        "extracted_answer": str(parsed.get("extracted_answer") or raw).strip(),
                        "clarification_needed": bool(parsed.get("clarification_needed")),
                        "polite_followup": str(parsed.get("polite_followup") or "").strip(),
                    }
        except Exception as e:
            logger.warning("AI verify_inquiry_answer tahlilida ogohlantirish: %s", e)

        # Fallback agar AI ishlamay qolsa
        return {
            "is_relevant": len(raw) > 1,
            "extracted_answer": raw,
            "clarification_needed": False,
            "polite_followup": "",
        }


# Global AI xizmati instansiyasi
ai_service = AIService()
