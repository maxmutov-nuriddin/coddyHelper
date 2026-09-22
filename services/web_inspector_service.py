"""
services/web_inspector_service.py
0-Token Veb-Inspektor va Vizual Skrinshot Xizmati (Zero-Token Web Inspector).
O'quvchilar va mentorlar yuborgan veb-loyihalarni (Vercel, Netlify, GitHub Pages, LMS va boshqa saytlar)
mutlaqo AI tokensiz (0 TOKEN) audit qiladi, skrinshotini oladi va hisobot tuzadi.
"""

import asyncio
import logging
import re
import time
from html.parser import HTMLParser
from typing import Any
import aiohttp

logger = logging.getLogger(__name__)

# O'quvchilar ko'p foydalanadigan deployment va veb-platformalar
STUDENT_DEPLOY_DOMAINS = (
    "vercel.app",
    "netlify.app",
    "github.io",
    "surge.sh",
    "render.com",
    "railway.app",
    "pages.dev",
    "web.app",
    "firebaseapp.com",
    "repl.co",
    "renderforestsites.com",
    "renderforest.com",
    "wixsite.com",
    "codepen.io",
    "glitch.me",
)

# Tekshirish niyatini bildiruvchi kalit iboralar
AUDIT_INTENT_KEYWORDS = (
    "tekshir",
    "korib ber",
    "ko'rib ber",
    "qarab ber",
    "qara",
    "qanday chiqibdi",
    "qanday bolibdi",
    "qanday bo'libdi",
    "baho ber",
    "audit",
    "ishlayaptimi",
    "saytim",
    "loyiham",
    "saytni",
    "loyihani",
    "frontend",
    "sayt qanday",
    "fikring",
    "check",
    "review",
    "посмотри",
    "проверь",
    "как тебе",
    "оцени",
)

# Chalg'imaslik kerak bo'lgan domenlar (YouTube, Telegram, Instagram, Google, va h.k.)
IGNORED_DOMAINS = (
    "t.me",
    "telegram.org",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "google.com",
    "yandex.ru",
    "mail.ru",
    "twitter.com",
    "x.com",
    "zoom.us",
    "meet.google.com",
)


class SimpleHTMLAuditor(HTMLParser):
    """
    Python standart kutubxonasidagi HTMLParser orqali
    HTML tuzilishi, meta-teglar, rasmlar va resurslarni 0 tokensiz tahlil qilish.
    """

    def __init__(self):
        super().__init__()
        self.title: str = ""
        self.in_title: bool = False
        self.has_viewport: bool = False
        self.has_charset: bool = False
        self.has_favicon: bool = False
        self.meta_description: str = ""

        # Teglar hisobi
        self.tags_count: dict[str, int] = {}
        self.images: list[dict[str, Any]] = []
        self.css_links: list[str] = []
        self.scripts: list[str] = []
        self.empty_links: int = 0
        self.h1_count: int = 0

        # Stek belgilari
        self.detected_stacks: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        self.tags_count[tag_lower] = self.tags_count.get(tag_lower, 0) + 1
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_lower == "title":
            self.in_title = True

        elif tag_lower == "meta":
            if attr_dict.get("name", "").lower() == "viewport":
                self.has_viewport = True
            if "charset" in attr_dict:
                self.has_charset = True
            if attr_dict.get("name", "").lower() == "description":
                self.meta_description = attr_dict.get("content", "")

        elif tag_lower == "link":
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "")
            if "icon" in rel:
                self.has_favicon = True
            if "stylesheet" in rel:
                self.css_links.append(href)
                if "tailwind" in href.lower():
                    self.detected_stacks.add("Tailwind CSS")
                elif "bootstrap" in href.lower():
                    self.detected_stacks.add("Bootstrap")
                elif "font-awesome" in href.lower() or "fontawesome" in href.lower():
                    self.detected_stacks.add("FontAwesome")

        elif tag_lower == "img":
            src = attr_dict.get("src", "").strip()
            alt = attr_dict.get("alt", "").strip()
            self.images.append({"src": src, "has_alt": bool(alt)})

        elif tag_lower == "a":
            href = attr_dict.get("href", "").strip()
            if not href or href == "#" or href.startswith("javascript:void(0)"):
                self.empty_links += 1

        elif tag_lower == "h1":
            self.h1_count += 1

        elif tag_lower == "script":
            src = attr_dict.get("src", "")
            if src:
                self.scripts.append(src)
                src_l = src.lower()
                if "react" in src_l:
                    self.detected_stacks.add("React")
                elif "vue" in src_l:
                    self.detected_stacks.add("Vue")
                elif "next" in src_l or "_next" in src_l:
                    self.detected_stacks.add("Next.js")
                elif "vite" in src_l:
                    self.detected_stacks.add("Vite")

        # Class yoki ID lar orqali stekni aniqlash
        classes = attr_dict.get("class", "").lower()
        if "flex" in classes and ("gap-" in classes or "p-" in classes or "text-" in classes):
            self.detected_stacks.add("Tailwind CSS")
        if "btn-primary" in classes or "container-fluid" in classes:
            self.detected_stacks.add("Bootstrap")

    def handle_endtag(self, tag: str):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str):
        if self.in_title:
            self.title += data


def extract_inspection_url(text: str) -> str | None:
    """
    Xabardan faqat tekshirilishi kerak bo'lgan veb-sayt havolasini ajratib oladi.
    Tasodifiy Telegram yoki YouTube linklariga chalg'imaydi.
    """
    if not text:
        return None

    clean = text.strip()

    # Maxsus buyruqlar: .site, .audit, /site, /audit, .web, /web
    cmd_match = re.search(r"^(?:[./]?(?:site|audit|sayt|web))\s+(https?://[^\s]+)", clean, re.I)
    if cmd_match:
        url = cmd_match.group(1).rstrip(".,;)>]")
        return url

    # Barcha HTTP/HTTPS linklarini topish
    found_urls = re.findall(r"https?://[^\s]+", clean)
    if not found_urls:
        return None

    lower_text = clean.lower()
    has_audit_intent = any(k in lower_text for k in AUDIT_INTENT_KEYWORDS)

    for raw_url in found_urls:
        url = raw_url.rstrip(".,;)>]")
        
        # Ignored domenlarni o'tkazib yuborish
        if any(ign in url.lower() for ign in IGNORED_DOMAINS):
            continue

        # Agar o'quvchi deployment domeniga (Vercel, Netlify, Github Pages...) ega bo'lsa
        if any(dep in url.lower() for dep in STUDENT_DEPLOY_DOMAINS):
            return url

        # Agar foydalanuvchi xabarda tekshirish niyatini bildirgan bo'lsa
        if has_audit_intent:
            return url

    return None


async def audit_website(url: str) -> dict[str, Any]:
    """
    Saytni 0 AI tokensiz, to'liq texnik audit qiladi.
    Yuklanish tezligi, HTTP kodi, mobil moslashuv, rasm xatolari, CSS va stekni aniqlaydi.
    """
    t0 = time.time()
    result: dict[str, Any] = {
        "ok": False,
        "url": url,
        "status_code": 0,
        "latency_sec": 0.0,
        "title": "",
        "has_viewport": False,
        "has_favicon": False,
        "h1_count": 0,
        "images_total": 0,
        "images_missing_alt": 0,
        "empty_links": 0,
        "css_count": 0,
        "detected_stacks": [],
        "issues": [],
        "good_points": [],
        "score": 100,
        "error": None,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 CoddyHelper/2.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "uz,en-US,en;q=0.9,ru;q=0.8",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
                result["status_code"] = resp.status
                result["latency_sec"] = round(time.time() - t0, 2)

                if resp.status != 200:
                    result["error"] = f"Sayt {resp.status} status kodi bilan javob berdi."
                    result["score"] = max(0, 50 - (resp.status - 200))
                    result["issues"].append(f"HTTP Status kodi: {resp.status} (200 OK kutilgan edi)")
                    return result

                html_content = await resp.text(errors="ignore")

                # HTML parser orqali tekshirish
                parser = SimpleHTMLAuditor()
                try:
                    parser.feed(html_content)
                except Exception:
                    pass

                result["ok"] = True
                result["title"] = parser.title.strip()
                result["has_viewport"] = parser.has_viewport
                result["has_favicon"] = parser.has_favicon
                result["h1_count"] = parser.h1_count
                result["images_total"] = len(parser.images)
                result["empty_links"] = parser.empty_links
                result["css_count"] = len(parser.css_links)
                result["detected_stacks"] = sorted(list(parser.detected_stacks))

                # HTML matnidan qo'shimcha stek belgilari
                html_lower = html_content.lower()
                if "react" in html_lower and "React" not in result["detected_stacks"]:
                    result["detected_stacks"].append("React")
                if "vite" in html_lower and "Vite" not in result["detected_stacks"]:
                    result["detected_stacks"].append("Vite")

                # Kamchiliklar va Yutuqlarni hisoblash
                score = 100

                # 1. Mobil moslashuv (Viewport)
                if parser.has_viewport:
                    result["good_points"].append("Mobil moslashuv to'g'ri sozlangan (`<meta name='viewport'>` mavjud).")
                else:
                    score -= 15
                    result["issues"].append("Mobil moslashuv (viewport) yo'q — sayt telefonda kichrayib qolishi mumkin.")

                # 2. Sarlavha (<title>)
                if not parser.title or parser.title.strip().lower() in ("react app", "vite + react", "document", "untitled"):
                    score -= 10
                    default_name = f"'{parser.title.strip()}'" if parser.title else "umuman yo'q"
                    result["issues"].append(f"`<title>` tegi standart yoki bo'sh qolgan ({default_name}). O'z loyihangiz nomini yozing.")
                else:
                    result["good_points"].append(f"Sayt nomi to'g'ri ko'rsatilgan: '{parser.title.strip()}'")

                # 3. H1 sarlavha
                if parser.h1_count == 0:
                    score -= 5
                    result["issues"].append("Sahifada asosiy `<h1>` sarlavhasi topilmadi (SEO uchun 1 ta `<h1>` kerak).")
                elif parser.h1_count > 1:
                    score -= 3
                    result["issues"].append(f"Sahifada {parser.h1_count} ta `<h1>` sarlavha bor. Odatda bitta sahifaga 1 ta `<h1>` tavsiya etiladi.")

                # 4. Rasmlar va alt atributlari
                missing_alts = sum(1 for img in parser.images if not img.get("has_alt"))
                result["images_missing_alt"] = missing_alts
                if missing_alts > 0:
                    score -= min(10, missing_alts * 2)
                    result["issues"].append(f"{missing_alts} ta rasmda alt='...' tavsifi unutilgan.")

                # 5. Bo'sh havolalar (href="#")
                if parser.empty_links > 0:
                    score -= min(10, parser.empty_links * 2)
                    result["issues"].append(f"{parser.empty_links} ta tugma/havolada href='#' qolib ketgan (havola ulanmagan).")

                # 6. Favicon
                if not parser.has_favicon:
                    score -= 5
                    result["issues"].append("Sayt ikonkasi (favicon) ulanmagan — brauzer tabida rasmcha ko'rinmaydi.")

                # 7. Tezlik
                if result["latency_sec"] < 0.5:
                    result["good_points"].append(f"Juda tez yuklandi: {result['latency_sec']}s ⚡")
                elif result["latency_sec"] > 2.0:
                    score -= 5
                    result["issues"].append(f"Yuklanish biroz sekin: {result['latency_sec']}s")

                result["score"] = max(20, min(100, score))
                return result

    except asyncio.TimeoutError:
        result["error"] = "Sayt javob bermadi (8 soniya kutish vaqti tugadi)."
        result["score"] = 0
        result["issues"].append("Sayt serveriga ulanish vaqti tugadi (Timeout).")
        return result
    except Exception as e:
        result["error"] = f"Ulanishda xatolik: {str(e)[:100]}"
        result["score"] = 0
        result["issues"].append(f"Serverga ulanib bo'lmadi: {str(e)[:60]}")
        return result


async def get_website_screenshot(url: str) -> bytes | None:
    """
    Saytning haqiqiy 1024x768 ekran tasvirini bepul render orqali oladi.
    1 dona ham AI token sarflanmaydi (0 Token).
    """
    endpoints = [
        f"https://image.thum.io/get/width/1024/crop/768/noanimate/{url}",
        f"https://mini.s-shot.ru/1024x768/PNG/1024/Z100/?{url}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "image/png,image/webp,image/*",
    }

    for ep in endpoints:
        try:
            timeout = aiohttp.ClientTimeout(total=9)
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(ep, timeout=timeout) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("content-type", "")
                        data = await resp.read()
                        if len(data) > 3000 and ("image" in content_type or data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
                            return data
        except Exception as e:
            logger.debug("Skrinshot olishda ogohlantirish (%s): %s", ep, e)
            continue

    return None


def format_audit_report(audit: dict[str, Any], url: str, is_detailed: bool = False) -> str:
    """
    O'quvchi uchun lo'nda (ixcham) yoki batafsil mentorlik audit hisobotini tuzadi.
    Guruhda xabarlar ko'payib shovqin bo'lmasligi uchun standart holatda 3-4 qatorda ixcham beriladi.
    Tavsiyalar faqat o'quvchi so'raganida (is_detailed=True) to'liq chiqariladi.
    """
    score = audit.get("score", 0)
    score_emoji = "🟢" if score >= 85 else ("🟡" if score >= 65 else "🔴")

    title_str = f" («{audit['title']}»)" if audit.get("title") else ""

    # 1. Standart ixcham (lo'nda) ko'rinish: Guruhni to'ldirib yubormaydi!
    if not is_detailed:
        status_note = "Ajoyib holatda! 🎉" if score >= 85 else "Yaxshi, lekin ayrim tuzatishlar bor 🛠"
        lines = [
            f"🌐 **Loyiha Auditi:** {title_str.strip() or 'Veb-sayt'}",
            f"🔗 `{url}`",
            f"📊 **Baho:** {score_emoji} **{score}/100 ball** | ⚡ **Tezlik:** `{audit.get('latency_sec', 0.0)}s` ({status_note})",
            "💡 *Tavsiyalar va xatolarni ko'rish uchun: «tavsiya ber» deb yozing.*",
        ]
        return "\n".join(lines)

    # 2. Batafsil ko'rinish (faqat o'quvchi tavsiya so'raganda):
    lines = [
        f"🌐 **CODDY Veb-Inspektor: Loyiha Auditi va Baholash**{title_str}",
        f"🔗 **Manzil:** `{url}`",
        f"📊 **Umumiy Baho:** {score_emoji} **{score}/100 ball**",
        f"⚡ **Yuklanish tezligi:** `{audit.get('latency_sec', 0.0)}s` | **Server holati:** `{audit.get('status_code', 0)} OK`",
    ]

    stacks = audit.get("detected_stacks", [])
    if stacks:
        lines.append(f"🛠 **Ishlatilgan texnologiyalar:** {', '.join(stacks)}")

    lines.append("\n🎨 **Ko'rinish, Ishlash va Sifat Tahlili:**")
    if audit.get("has_viewport"):
        lines.append("• 📱 **Ko'rinish & Moslashuv:** Sayt mobil qurilmalarga to'g'ri moslashgan (Responsive).")
    else:
        lines.append("• 📱 **Ko'rinish & Moslashuv:** Mobil moslashuv to'liq emas, telefonda bloklar siljishi mumkin.")

    empty_links = audit.get("empty_links", 0)
    if empty_links == 0:
        lines.append("• 🔗 **Ishlashi va Bog'liqlik:** Barcha tugma va havolalar to'g'ri ulangan.")
    else:
        lines.append(f"• 🔗 **Ishlashi va Bog'liqlik:** {empty_links} ta tugmada `href='#'` qolgan (havola ulanmagan).")

    issues = audit.get("issues", [])
    if issues:
        lines.append("\n🛠 **Yaxshilash uchun mentor tavsiyalari:**")
        for idx, iss in enumerate(issues[:5], 1):
            lines.append(f"{idx}. {iss}")
    else:
        lines.append("\n🎉 **Barakalla!** Hech qanday kamchilik topilmadi, sayt juda yaxshi tayyorlangan.")

    return "\n".join(lines)
