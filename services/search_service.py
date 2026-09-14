"""
services/search_service.py
Web Search & Rasmiy IT Dokumentatsiyalardan qidirish xizmati.
- O'quvchilar uchun: Faqat IT/dasturlash va ta'limiy mavzularda qidiruv (chegaradan chiqmasdan).
- Vazifalar (Mentor) uchun: Mutlaq erkin, har qanday mavzuda cheklovlarsiz qidiruv.
"""

import asyncio
import logging
import re
import urllib.parse
from typing import Any
import aiohttp

logger = logging.getLogger(__name__)

# Dasturlash va IT sohasiga oid kalit so'zlar ro'yxati (chegara nazorati uchun)
PROGRAMMING_KEYWORDS = {
    # Dasturlash tillari
    "python", "javascript", "js", "typescript", "ts", "html", "css", "c++", "cpp", "c#",
    "java", "php", "ruby", "go", "golang", "rust", "kotlin", "swift", "sql", "bash", "shell",
    # Freymvork va kutubxonalar
    "django", "flask", "fastapi", "react", "vue", "angular", "node", "nodejs", "telethon",
    "aiogram", "pyrogram", "requests", "aiohttp", "pandas", "numpy", "matplotlib", "seaborn",
    "scipy", "scikit", "sklearn", "tensorflow", "pytorch", "keras", "opencv", "pygame", "turtle",
    "tkinter", "customtkinter", "sqlalchemy", "peewee", "celery", "redis", "pydantic",
    # Texnologiya va tushunchalar
    "git", "github", "gitlab", "docker", "kubernetes", "linux", "ubuntu", "terminal", "pip",
    "npm", "yarn", "venv", "virtualenv", "api", "rest", "json", "jwt", "oauth", "webhook",
    "database", "baza", "sqlite", "sqlite3", "postgres", "postgresql", "mysql", "mongodb",
    "asyncio", "async", "await", "multithreading", "orm", "oop", "crud", "frontend", "backend",
    "fullstack", "devops", "qa", "testing", "pytest", "unittest", "regex",
    # Sintaksis va xatoliklar
    "error", "exception", "traceback", "syntaxerror", "typeerror", "valueerror",
    "modulenotfounderror", "importerror", "nameerror", "indexerror", "keyerror",
    "attributeerror", "zerodivisionerror", "indentationerror", "bug", "debug",
    "funksiya", "function", "def", "class", "metod", "method", "loop", "sikli", "tsikl",
    "for", "while", "if", "else", "elif", "try", "except", "dict", "list", "tuple", "set",
    "string", "int", "float", "bool", "array", "massiv", "ozgaruvchi", "o'zgaruvchi",
    # O'quv markazi va ta'lim
    "coddycamp", "coddy", "dars", "topshiriq", "vazifa", "uyga vazifa", "lms", "kod", "code",
    "dastur", "algoritm", "amaliyot", "scratch", "robolab", "robototexnika",
}


def is_programming_query(query: str) -> bool:
    """
    Savol dasturlash yoki IT mavzusiga tegishli ekanligini tekshiradi.
    O'quvchilar chegaradan chiqmasligi uchun filtr sifatida ishlatiladi.
    """
    if not query:
        return False

    q_lower = query.lower()
    # 1. So'zlarga ajratib tekshirish
    words = set(re.findall(r"[a-z0-9+#_]+", q_lower))
    if words.intersection(PROGRAMMING_KEYWORDS):
        return True

    # 2. O'zbekcha / ruscha qo'shimchalar bilan kelganda o'zakni tekshirish (masalan: reactda, pythonga, xatoni)
    for kw in PROGRAMMING_KEYWORDS:
        if len(kw) >= 4:
            if any(w.startswith(kw) or kw in w for w in words):
                return True
        else:
            # Qisqa so'zlar: js, ts, sql, git, pip, npm, c++
            if re.search(r'\b' + re.escape(kw) + r'(?:da|ni|ga|ning|dan|cha)?\b', q_lower):
                return True

    # 3. Fraza va xatolik belgilari
    it_phrases = [
        "dasturlash", "kod yozish", "qanday o'rnat", "qanday ornat", "install", "pip install",
        "npm i", "git commit", "git push", "pull request", "xatolik chiqdi", "xato berdi",
        "nega ishlamayapti", "kodim xato", "kutubxona", "dokumentatsiya", "documentation",
        "yangi versiya", "oxirgi versiya", "python 3", "darsda", "uyga vazifa", "hook", "state",
    ]
    return any(phrase in q_lower for phrase in it_phrases)


async def _fetch_ddg_instant_answer(session: aiohttp.ClientSession, query: str) -> dict[str, str] | None:
    """DuckDuckGo Instant Answer API orqali tezkor hujjat qidiruvi."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                abstract = data.get("AbstractText", "").strip()
                source_url = data.get("AbstractURL", "").strip()
                heading = data.get("Heading", "").strip()
                if abstract and len(abstract) > 20:
                    return {
                        "title": heading or query,
                        "snippet": abstract,
                        "url": source_url or "https://duckduckgo.com",
                    }
    except Exception as e:
        logger.debug("DDG Instant Answer xatolik: %s", e)
    return None


async def _fetch_ddg_html_results(session: aiohttp.ClientSession, query: str, max_results: int = 4) -> list[dict[str, str]]:
    """DuckDuckGo HTML qidiruvi orqali veb va IT dokumentatsiyalardan natijalar olish."""
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        data = {"q": query}
        async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                html = await resp.text()

                # Snippet va sarlavhalarni ajratib olish
                blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, re.DOTALL)
                for b in blocks[:max_results]:
                    # Sarlavha va link
                    title_m = re.search(r'<a class="result__snippet[^>]*>(.*?)</a>', b, re.DOTALL)
                    link_m = re.search(r'<a class="result__url"[^>]*href="([^"]+)"', b)
                    heading_m = re.search(r'<a class="result__a"[^>]*>(.*?)</a>', b, re.DOTALL)

                    snippet = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""
                    title = re.sub(r'<[^>]+>', '', heading_m.group(1)).strip() if heading_m else query
                    raw_link = link_m.group(1).strip() if link_m else ""

                    # Linkni tozalash
                    clean_url = ""
                    if "uddg=" in raw_link:
                        m_uddg = re.search(r'uddg=([^&]+)', raw_link)
                        if m_uddg:
                            clean_url = urllib.parse.unquote(m_uddg.group(1))
                    else:
                        clean_url = raw_link

                    if snippet and len(snippet) > 15:
                        results.append({
                            "title": title,
                            "snippet": snippet,
                            "url": clean_url or "https://duckduckgo.com",
                        })
    except Exception as e:
        logger.debug("DDG HTML qidiruvida xatolik: %s", e)
    return results


async def _fetch_stackoverflow_results(session: aiohttp.ClientSession, query: str) -> list[dict[str, str]]:
    """StackOverflow API orqali dasturlash xatolariga yechimlarni qidirish."""
    results = []
    try:
        clean_q = re.sub(r"[^\w\s]", " ", query).strip()
        url = "https://api.stackexchange.com/2.3/search/advanced"
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": clean_q,
            "site": "stackoverflow",
            "pagesize": "3",
            "filter": "default",
        }
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                items = data.get("items", [])
                for it in items:
                    title = it.get("title", "")
                    link = it.get("link", "")
                    tags = ", ".join(it.get("tags", []))
                    if title and link:
                        results.append({
                            "title": f"[StackOverflow] {title}",
                            "snippet": f"Mavzu teglari: {tags}. Savol havolasi mavjud.",
                            "url": link,
                        })
    except Exception as e:
        logger.debug("StackOverflow qidiruv xatoligi: %s", e)
    return results


async def search_web(query: str, max_results: int = 4) -> list[dict[str, str]]:
    """
    Internet va IT hujjatlaridan qidiruvni amalga oshiradi.
    DuckDuckGo Instant Answer + DuckDuckGo Web + StackOverflow integratsiyasi.
    """
    q = (query or "").strip()
    if not q or len(q) < 3:
        return []

    results = []
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Tezkor javob (Instant answer)
            ia_task = _fetch_ddg_instant_answer(session, q)
            # 2. Veb qidiruv natijalari
            web_task = _fetch_ddg_html_results(session, q, max_results)

            ia_res, web_res = await asyncio.gather(ia_task, web_task, return_exceptions=True)

            if isinstance(ia_res, dict) and ia_res:
                results.append(ia_res)

            if isinstance(web_res, list) and web_res:
                results.extend(web_res)

            # Agar natijalar kam bo'lsa va bu dasturlash xatosi bo'lsa, StackOverflow dan qidirish
            if len(results) < 2 and any(err_w in q.lower() for err_w in ["error", "xato", "exception", "traceback"]):
                so_res = await _fetch_stackoverflow_results(session, q)
                if so_res:
                    results.extend(so_res)

    except Exception as e:
        logger.warning("Web search asosiy jarayonida xatolik: %s", e)

    # Dublikat URL larni tozalash
    seen_urls = set()
    unique_results = []
    for r in results:
        u = r.get("url", "")
        if u and u in seen_urls:
            continue
        seen_urls.add(u)
        unique_results.append(r)

    return unique_results[:max_results]


async def search_targeted_websites(query: str, trusted_sites: list[str], max_results: int = 3) -> list[dict[str, str]]:
    """
    1-POG'ONA: Faqat admin/mentor tanlagan ishonchli ta'limiy saytlar ichidan qidiradi.
    Masalan: python list methods (site:w3schools.com OR site:docs.python.org)
    """
    if not query or not trusted_sites:
        return []

    # DuckDuckGo query uchun saytlar filtri
    # Maksimal 5 ta sayt bilan guruhlash (so'rov juda cho'zilib ketmasligi uchun)
    active_sites = [s.strip() for s in trusted_sites if s.strip()][:5]
    if not active_sites:
        return []

    site_clauses = " OR ".join(f"site:{s}" for s in active_sites)
    targeted_q = f"{query} ({site_clauses})"

    try:
        async with aiohttp.ClientSession() as session:
            results = await _fetch_ddg_html_results(session, targeted_q, max_results=max_results)
            # Natijalar haqiqatdan ham ko'rsatilgan saytlarga tegishli ekanini tekshirish
            filtered = []
            for r in results:
                url = r.get("url", "").lower()
                if any(s.lower() in url for s in active_sites):
                    filtered.append(r)
                elif r.get("snippet"):
                    filtered.append(r)
            return filtered[:max_results]
    except Exception as e:
        logger.debug("Maqsadli saytlardan qidirishda ogohlantirish: %s", e)
        return []


async def get_web_search_context(query: str, is_admin: bool = False) -> str:
    """
    Kaskadli qidiruv (Tiered RAG) kontekstini AI modeli uchun tayyorlaydi.
    1-POG'ONA: Tanlangan ishonchli saytlar (w3schools, docs.python, metanit...).
    2-POG'ONA: Agar topilmasa, ochiq internet (DuckDuckGo + StackOverflow).
    3-POG'ONA: AI o'zbek tilida sodda va do'stona qilib yetkazishi uchun yo'riqnoma.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return ""

    # Chegara nazorati: O'quvchilar faqat IT/dasturlash so'ray oladi
    if not is_admin and not is_programming_query(clean_q):
        logger.info("O'quvchi so'rovi IT mavzusiga kirmaydi, qidiruv cheklandi: %s", clean_q[:50])
        return ""

    from services.memory_service import memory_service
    trusted_sites = memory_service.get_trusted_websites()

    results = []
    source_label = "open_web"

    # 1. Avval ishonchli saytlar ichidan qidirish (Tier 1)
    if trusted_sites:
        logger.info("Kaskad 1-pog'ona: Ishonchli saytlardan qidirilmoqda: %s (%s)", clean_q[:40], ", ".join(trusted_sites[:3]))
        results = await search_targeted_websites(clean_q, trusted_sites, max_results=3)
        if results:
            source_label = "trusted_sites"
            logger.info("Kaskad 1-pog'ona muvaffaqiyatli: %d ta rasmiy manba topildi.", len(results))

    # 2. Agar tanlangan saytlardan topilmasa, butun internetdan qidirish (Tier 2 - Fallback)
    if not results:
        logger.info("Kaskad 2-pog'ona: Butun internet va StackOverflow'dan qidirilmoqda: %s", clean_q[:40])
        results = await search_web(clean_q, max_results=3)
        source_label = "open_web"

    if not results:
        return ""

    if source_label == "trusted_sites":
        lines = [
            "\n--- 🌐 ISHONCHLI MANBALARDAN OLINGAN ANIQ FAKT (Rasmiy Ta'limiy Saytlar) ---",
            "Quyidagi ma'lumotlar mentor tomonidan tasdiqlangan rasmiy ta'limiy saytlardan olindi:"
        ]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. 📌 **{r['title']}**")
            lines.append(f"   Ma'lumot: {r['snippet']}")
            if r.get("url"):
                lines.append(f"   Havola: {r['url']}")
        lines.append("--- Ko'rsatma: Yuqoridagi rasmiy ma'lumotlardan foydalanib, o'quvchiga/mentorga aniq faktni o'zbek tilida, nihoyatda sodda, do'stona va tushunarli tarzda 2-4 gapda bayon qiling. ---")
    else:
        lines = [
            "\n--- 🌐 OCHIQ INTERNET NATIJALARI (DuckDuckGo & StackOverflow) ---"
        ]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. 📌 **{r['title']}**")
            lines.append(f"   Ma'lumot: {r['snippet']}")
            if r.get("url"):
                lines.append(f"   Havola: {r['url']}")
        lines.append("--- Ko'rsatma: Yuqoridagi ma'lumotlardan foydalanib o'quvchiga/mentorga o'zbek tilida aniq va to'g'ri javob bering. ---")

    return "\n".join(lines)
