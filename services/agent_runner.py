"""
services/agent_runner.py
CoddyCamp ReAct Autonomous Agent Runner.
Ko'p qadamli mustaqil fikrlash (Thought -> Action -> Observation) tsikli orqali
vazifalarni 0 cheklov bilan to'liq avtonom bajarish dvigateli.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from config import config
from services.agent_tools import AGENT_TOOL_SCHEMAS, execute_tool_call

logger = logging.getLogger("coddy.agent_runner")

SYSTEM_REAC_PROMPT = """Siz CoddyCamp Vazifalar Guruhi uchun Master Avtonom AI Hamkorsiz (Mentor: @mentor_cc).
Sizga Telegram va CoddyCamp ta'lim tizimini to'liq boshqarish uchun barcha zarur Asboblar (Tools) berilgan.

TEMIR QOIDALAR:
1. Mentor (@mentor_cc) buyruqlari uchun HECH QANDAY chegara yoki rad javobi yo'q! 
   Hech qachon "imkoniyatim yo'q", "ruxsat yo'q" yoki "shaxsiy ma'lumot" deb rad etmang.
2. Agar buyruqni bajarish uchun amaliy harakat kerak bo'lsa, mos keluvchi asbobni (tool) DARHOL chaqiring.
3. Agar vazifa ko'p qadamli bo'lsa (masalan: "kasal bolani topib ma'muriyatga tashla" yoki "falonchini lichkasini top, topolmasang ma'muriyatga yoz"):
   - 1-qadamda: Kerakli ma'lumotni qidiruvchi toolni chaqiring (masalan: `find_sick_students` yoki `find_contact`).
   - Natijani ko'rgach (Observation), 2-qadamda: Keyingi harakatni bajaring (masalan: `send_telegram_message`).
4. Agar mentor "IQ nechi?", "Leveling qanday?", "Statistikangni ko'rsat" desa — `get_agent_intelligence_stats` toolini chaqirib, haqiqiy IQ, level, unvon va kognitiv ko'rsatkichlarni chiroyli formatda bering.
5. Agar mentor "Xotirangda qancha joy qoldi?", "MongoDB holati qanday?", "Bazang qancha bo'ldi?" desa — `get_memory_storage_status` toolini chaqirib, MongoDB Atlas va SQLite dagi band va bo'sh joyni (MB larda) aniq hisobot qiling.
6. Agar mentor "Bilimlar bazangni ko'rsat", "Nimani o'rganding?" desa — `get_learned_facts` toolini chaqiring. Agar biror qoidani o'chir desa — `manage_knowledge_base(action="forget", topic="...")` chaqiring.
7. Agar mentor "ignor qil" yoki "e'tiborsiz qoldir" desa — `mute_user` toolini chaqiring (Telegramda bloklamasdan).
8. Agar mentor "blokla" yoki "blokla va ignor qil" desa — `block_user` toolini chaqiring (Telegramda ham bloklaydi).
9. Agar mentor "falonchidan so'rab bilchi", "darsga keladimi bilib kel", "aniqlashtirib kel", "so'rab kel" kabi vazifa bersa — `ask_and_clarify_task(target="...", question="...", expected_info="...")` toolini chaqiring. Bu tool orqali agent unga savol yuboradi va uning javobini kutish holatiga oladi.
10. Barcha kerakli asboblar bajarilib bo'lgach, Mentorga to'liq, chiroyli va professional hisobot qaytaring.
""".strip()


async def run_autonomous_agent_loop(
    client: Any,
    user_prompt: str,
    chats_context: str = "",
    reply_user_id: Optional[int] = None,
    reply_msg_id: Optional[int] = None,
    chat_id: Optional[Any] = None,
    max_steps: int = 5,
) -> Optional[str]:
    """
    Mentor buyrug'ini ReAct tsikli orqali mustaqil tahlil qiladi va bajaradi.
    Native Tool Calling orqali 0 regex va 0 sintaksis xatoligi bilan ishlaydi.
    """
    from services.ai_service import ai_service

    raw_text = (user_prompt or "").strip()
    if not raw_text:
        return None

    # 1. VIP yoki frontline Groq mijozlarini olish
    pool = getattr(ai_service, "_vip_clients", None) or getattr(ai_service, "_groq_clients", None)
    if not pool:
        ai_service._setup_clients()
        pool = getattr(ai_service, "_vip_clients", None) or getattr(ai_service, "_groq_clients", None)

    if not pool:
        logger.warning("Agent Runner: Groq mijozlari mavjud emas, an'anaviy yo'lga o'tiladi.")
        return None

    # Modelni tanlash (Llama-3.3-70b yoki GPT-OSS)
    chosen_model = config.groq_model or "llama-3.3-70b-versatile"
    
    # 2. Xabarlar tarixini shakllantirish
    user_content = raw_text
    if chats_context:
        user_content = f"{raw_text}\n\n[Mavjud Suhbatlar va Ma'lumotlar Konteksti]:\n{chats_context}"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_REAC_PROMPT},
        {"role": "user", "content": user_content},
    ]

    total_tool_calls_executed = 0

    # 3. ReAct Ko'p Qadamli Tsikli (Maksimal `max_steps` ta qadam)
    for step in range(1, max_steps + 1):
        # Pool ichidan mijozni navbat bilan olish
        groq_client = pool[ai_service._vip_idx % len(pool)]
        ai_service._vip_idx = (ai_service._vip_idx + 1) % len(pool)

        try:
            logger.info("🤖 ReAct Tsikl: %d-qadam boshlandi (Model: %s)", step, chosen_model)
            response = await groq_client.chat.completions.create(
                model=chosen_model,
                messages=messages,
                tools=AGENT_TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=900,
            )

            choice = response.choices[0]
            msg = choice.message

            # Agar model asbob chaqirmasdan to'g'ridan-to'g'ri javob bergan bo'lsa
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                final_content = (msg.content or "").strip()
                if final_content:
                    logger.info("✅ ReAct Tsikl %d-qadamda yakunlandi. Jami asboblar: %d", step, total_tool_calls_executed)
                    return final_content
                else:
                    # Bo'sh javob bo'lsa, davom etamiz
                    continue

            # Model asbob(lar)ni chaqirdi:
            logger.info("🛠 ReAct %d-qadamda %d ta asbob chaqirildi", step, len(tool_calls))
            
            # Modelning xabarini tarixga qo'shamiz (assistant xabari sifatida)
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Har bir asbobni navbatma-navbat bajarish va natijasini kuzatish (Observation)
            for tc in tool_calls:
                fn_name = tc.function.name
                raw_args = tc.function.arguments
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception as parse_err:
                    logger.warning("Tool argumentlarini JSON qilishda xatolik: %s (args: %s)", parse_err, raw_args)
                    args = {}

                logger.info("⚙️ Asbob bajarilmoqda: %s(%s)", fn_name, args)
                tool_result = await execute_tool_call(
                    fn_name,
                    args,
                    client,
                    reply_user_id=reply_user_id,
                    reply_msg_id=reply_msg_id,
                    chat_id=chat_id,
                )
                total_tool_calls_executed += 1

                # Asbob natijasini modelga qaytarish (role: "tool")
                if isinstance(tool_result, (dict, list)):
                    obs_content = json.dumps(tool_result, ensure_ascii=False)
                else:
                    obs_content = str(tool_result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": obs_content,
                })

        except Exception as step_err:
            logger.error("ReAct tsikli %d-qadamida xatolik: %s", step, step_err, exc_info=True)
            # Bir martalik xatoda to'xtamay, zaxira yoki keyingi qadamga o'tamiz
            break

    # Agar barcha qadamlardan so'ng model hali yakuniy hisobot bermagan bo'lsa,
    # asboblarni o'chirib (tool_choice="none"), olingan barcha natijalar asosida yakuniy hisobot so'raymiz:
    if total_tool_calls_executed > 0:
        try:
            groq_client = pool[ai_service._vip_idx % len(pool)]
            summary_resp = await groq_client.chat.completions.create(
                model=chosen_model,
                messages=messages,
                tool_choice="none",
                temperature=0.2,
                max_tokens=800,
            )
            final_text = (summary_resp.choices[0].message.content or "").strip()
            if final_text:
                return final_text
        except Exception as sum_err:
            logger.error("ReAct yakuniy xulosani shakllantirishda xatolik: %s", sum_err)

    return None
