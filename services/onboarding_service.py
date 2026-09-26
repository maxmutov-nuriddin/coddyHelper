"""
Yangi mijoz uchun conversational onboarding.

Agent yangi mijoz bilan suhbatlashib, biznes haqida ma'lumot to'playdi,
so'ng AI yordamida system_prompt va bilimlar bazasini avtomatik yaratadi.
"""

import json
import logging
from services.memory_service import memory_service
from services.tenant_context import tenant_scope

logger = logging.getLogger("coddyHelper.onboarding")

# Onboarding holati settings kaliti
_STATE_KEY = "onboarding_state"
_DATA_KEY  = "onboarding_data"

# Savollar ketma-ketligi
QUESTIONS = [
    {
        "key": "business_name",
        "text": (
            "Sizning biznesingiz yoki kompaniyangiz nomi nima? "
            "(Masalan: Akmal Mebel, Grand Clinic, Najot Rieltor)"
        ),
    },
    {
        "key": "profession",
        "text": (
            "Qanday soha yoki xizmat ko'rsatasiz? "
            "(Masalan: mebel sotish, tibbiy konsultatsiya, ko'chmas mulk, restoran, online do'kon)"
        ),
    },
    {
        "key": "products",
        "text": (
            "Asosiy mahsulot yoki xizmatlaringizni sanab bering. "
            "(Masalan: yotoq xonasi mebellari, stol-stullar, 3D loyiha; yoki ko'rikdan o'tkazish, EKG, massaj)"
        ),
    },
    {
        "key": "hours",
        "text": (
            "Ish vaqtingiz qanday? "
            "(Masalan: Dushanba–Shanba, 09:00–20:00; yoki 24/7 online)"
        ),
    },
    {
        "key": "prices",
        "text": (
            "Narx diapazoni yoki asosiy narxlar haqida qisqacha aytib bering. "
            "(Masalan: stullar 150,000 dan, to'xtash narxi muzokarali; yoki konsultatsiya 50,000 UZS)"
        ),
    },
    {
        "key": "language",
        "text": (
            "Mijozlaringiz asosan qaysi tilda muloqot qiladi? "
            "(O'zbek / Rus / Ingliz / Aralash)"
        ),
    },
    {
        "key": "special",
        "text": (
            "Agentingiz bilishi kerak bo'lgan boshqa muhim ma'lumot bormi? "
            "(Manzil, yetkazib berish shartlari, chegirmalar, ijtimoiy tarmoqlar — ixtiyoriy. "
            "Yo'q desangiz, \"yo'q\" deb yozing.)"
        ),
    },
]


def get_state(user_id: int) -> str | None:
    with tenant_scope(user_id):
        return memory_service.get_setting(_STATE_KEY)


def set_state(user_id: int, state: str) -> None:
    with tenant_scope(user_id):
        memory_service.set_setting(_STATE_KEY, state)


def get_data(user_id: int) -> dict:
    with tenant_scope(user_id):
        raw = memory_service.get_setting(_DATA_KEY) or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def save_data(user_id: int, data: dict) -> None:
    with tenant_scope(user_id):
        memory_service.set_setting(_DATA_KEY, json.dumps(data, ensure_ascii=False))


def is_onboarding_needed(user_id: int) -> bool:
    """Mijozda system_prompt va bilimlar bazasi bo'sh bo'lsa onboarding kerak."""
    state = get_state(user_id)
    if state == "done":
        return False
    with tenant_scope(user_id):
        sub = memory_service.get_subscription(user_id) or {}
        has_prompt = bool((sub.get("system_prompt") or "").strip())
        has_knowledge = bool(memory_service.get_all_precomputed_answers(limit=1, owner_id=user_id))
    return not has_prompt and not has_knowledge


def current_question_index(user_id: int) -> int:
    """Hozirgi savol indeksini qaytaradi (0-based). -1 = hali boshlanmagan."""
    state = get_state(user_id)
    if not state or state in ("done", "generating"):
        return -1
    try:
        return int(state.replace("q", ""))
    except (ValueError, AttributeError):
        return -1


def start_onboarding(user_id: int) -> str:
    """Onboardingni boshlaydi, birinchi savolni qaytaradi."""
    set_state(user_id, "q0")
    save_data(user_id, {})
    return (
        "🎉 **Xush kelibsiz! Men sizning shaxsiy AI yordamchingizman.**\n\n"
        "Mijozlaringizga yaxshiroq xizmat ko'rsatish uchun biznesingiz haqida "
        "bir necha savol beraman — faqat 2-3 daqiqa vaqt oladi. "
        "Javoblaringizdan kelib chiqib o'zimni sozlab olaman.\n\n"
        f"1️⃣ {QUESTIONS[0]['text']}"
    )


def process_answer(user_id: int, answer: str) -> str:
    """
    Foydalanuvchi javobini saqlaydi, keyingi savolni yoki yakunni qaytaradi.
    Qaytadi: (matn, is_done)
    """
    idx = current_question_index(user_id)
    if idx < 0:
        return "", False

    data = get_data(user_id)
    key = QUESTIONS[idx]["key"]
    data[key] = answer.strip()
    save_data(user_id, data)

    next_idx = idx + 1
    if next_idx < len(QUESTIONS):
        set_state(user_id, f"q{next_idx}")
        q = QUESTIONS[next_idx]
        return f"{next_idx + 1}️⃣ {q['text']}", False
    else:
        set_state(user_id, "generating")
        return "", True


async def finalize_onboarding(user_id: int) -> str:
    """
    Barcha javoblarni AI orqali tahlil qilib system_prompt + bilimlar bazasini yaratadi.
    Tugaganda 'done' holatiga o'tkazadi.
    """
    data = get_data(user_id)

    raw_summary = "\n".join(
        f"- {QUESTIONS[i]['key']}: {data.get(QUESTIONS[i]['key'], '—')}"
        for i in range(len(QUESTIONS))
    )

    prompt = f"""Quyidagi biznes ma'lumotlariga asoslanib, Telegram AI yordamchi uchun professional system prompt yarat.

BIZNES MA'LUMOTLARI:
{raw_summary}

TALABLAR:
1. system_prompt: 3-5 jumladan iborat. Agent kimligini, qanday javob berishini, nimaga ruxsat va nimaga ruxsat yo'qligini aniq belgilaydi. O'zbek tilida. Mijoz tilini avtomatik aniqlash kerak.
2. knowledge_entries: 3-6 ta muhim bilim yozuvi. Har biri: {{"topic": "...", "content": "..."}} formatda. Narxlar, ish vaqti, manzil, xizmatlar kabi konkret ma'lumotlar.
3. topics: 3-5 ta asosiy mavzu (curriculum topics ro'yxati) - agent faqat shu mavzular bo'yicha yordam beradi.

Faqat JSON formatda javob ber:
{{
  "system_prompt": "...",
  "knowledge_entries": [{{"topic": "...", "content": "..."}}],
  "topics": ["...", "..."]
}}"""

    result_text = ""
    try:
        from services.ai_service import ai_service
        raw = await ai_service.generate_reply(
            messages=[{"role": "user", "content": prompt}],
            system="Sen biznes AI konfiguratsiya mutaxassisisan. Faqat JSON formatda javob ber.",
            max_tokens=1200,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        config_data = json.loads(raw)
    except Exception as e:
        logger.error("Onboarding AI generatsiya xatosi: %s", e)
        config_data = _fallback_config(data)

    system_prompt = config_data.get("system_prompt", "")
    knowledge_entries = config_data.get("knowledge_entries", [])
    topics = config_data.get("topics", [])

    with tenant_scope(user_id):
        sub = memory_service.get_subscription(user_id) or {}
        memory_service.upsert_subscription(
            user_id=user_id,
            username=sub.get("username", ""),
            full_name=sub.get("full_name", ""),
            business_name=data.get("business_name") or sub.get("business_name", ""),
            profession=data.get("profession") or sub.get("profession", ""),
            system_prompt=system_prompt,
            days=0,
            is_edit=True,
            plan=sub.get("plan", "pro"),
        )
        for entry in knowledge_entries[:6]:
            t = str(entry.get("topic", "")).strip()
            c = str(entry.get("content", "")).strip()
            if t and c:
                memory_service.add_precomputed_answer(
                    topic=t,
                    question_pattern=t,
                    answer_text=c,
                    owner_id=user_id,
                )
        if topics:
            memory_service.set_curriculum_topics([str(x).strip() for x in topics if x], user_id=user_id)

        # Javob tilini ham saqlash
        lang_raw = (data.get("language") or "").lower()
        if "rus" in lang_raw or "russian" in lang_raw or "рус" in lang_raw:
            memory_service.set_setting(f"reply_language_{user_id}", "ru")
        elif "ingl" in lang_raw or "english" in lang_raw:
            memory_service.set_setting(f"reply_language_{user_id}", "en")
        else:
            memory_service.set_setting(f"reply_language_{user_id}", "auto")

    set_state(user_id, "done")
    biz = data.get("business_name") or "Biznesingiz"
    result_text = (
        f"✅ **{biz} uchun agent sozlandi!**\n\n"
        f"🧠 AI yo'riqnoma yozildi\n"
        f"📚 {len(knowledge_entries)} ta bilim yozuvi saqlandi\n"
        f"🎯 {len(topics)} ta mavzu belgilandi\n\n"
        "Endi agentingiz to'liq ishlashga tayyor.\n"
        "Paneldan **Mening Agentim** bo'limida Telegram akkauntingizni ulab, ishga tushiring 👇"
    )
    return result_text


def _fallback_config(data: dict) -> dict:
    """AI ishlamasa minimal konfiguratsiya."""
    biz = data.get("business_name", "Biznes")
    prof = data.get("profession", "xizmat ko'rsatish")
    hours = data.get("hours", "ish vaqtida")
    return {
        "system_prompt": (
            f"Men {biz} ning AI yordamchisiman. "
            f"{prof} bo'yicha mijozlarga yordam beraman. "
            f"Xushmuomala, qisqa va aniq javob beraman. "
            f"Bilmasam, egamga yo'naltiraman."
        ),
        "knowledge_entries": [
            {"topic": "ish_vaqti", "content": hours},
            {"topic": "xizmatlar", "content": data.get("products", "")},
            {"topic": "narxlar", "content": data.get("prices", "")},
        ],
        "topics": [prof, biz],
    }
