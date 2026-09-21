"""
Universal Multi-Stack Code Linter Service.
CoddyCamp o'quv dasturi (Python, JavaScript/Node.js, React JSX, HTML, CSS, JSON, SQL)
uchun lokal 0.005 soniyalik sintaksis va tuzilma tahlilchisi.
"""

import ast
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LintResult:
    language: str
    line_number: int
    column: int
    error_type: str
    visual_snippet: str
    message_uz: str
    message_ru: str
    hint_uz: str
    hint_ru: str


# HTML da yopilishi shart bo'lmagan (void/self-closing) teglar
HTML_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr"
}


def _build_visual_snippet(lines: list[str], err_line: int, err_col: int = 1, context_radius: int = 2) -> str:
    """Xatolik yuz bergan qator atrofidagi kodni va ko'rsatkichni (^) chizib beradi."""
    if not lines:
        return ""

    start_idx = max(0, err_line - 1 - context_radius)
    end_idx = min(len(lines), err_line + context_radius)

    snippet_lines = []
    line_num_width = len(str(end_idx))

    for idx in range(start_idx, end_idx):
        curr_line_num = idx + 1
        line_text = lines[idx]
        prefix = "> " if curr_line_num == err_line else "  "
        num_str = str(curr_line_num).rjust(line_num_width)
        snippet_lines.append(f"{prefix}{num_str} | {line_text}")

        # Ko'rsatkich (^) chizish
        if curr_line_num == err_line:
            col_pos = max(1, err_col)
            # tab larni probelga almashtirib pozitsiyani hisoblash
            leading_text = line_text[:col_pos - 1]
            expanded_leading = len(leading_text.expandtabs(4))
            indent = " " * (2 + line_num_width + 3 + expanded_leading)
            snippet_lines.append(f"{indent}^")

    separator = "-" * max(40, min(65, max(len(l) for l in snippet_lines) if snippet_lines else 40))
    return f"{separator}\n" + "\n".join(snippet_lines) + f"\n{separator}"


def lint_python(code: str) -> LintResult | None:
    """Python kodini ast.parse orqali sintaktik tekshiradi."""
    lines = code.splitlines()
    try:
        ast.parse(code)
        return None
    except IndentationError as ie:
        line_no = ie.lineno or 1
        col_no = ie.offset or 1
        visual = _build_visual_snippet(lines, line_no, col_no)
        msg = str(ie.msg or "IndentationError")
        return LintResult(
            language="Python",
            line_number=line_no,
            column=col_no,
            error_type="IndentationError",
            visual_snippet=visual,
            message_uz=f"`IndentationError`: Qator boshidagi surilish (probel/tab) noto'g'ri: {msg}",
            message_ru=f"`IndentationError`: Нарушен отступ строки (пробел/табуляция): {msg}",
            hint_uz="Python'da `if`, `for`, `def`, `while`, `class` bloklari ichidagi kod aniq 4 ta probel bilan surilishi kerak.",
            hint_ru="В Python блоки кода внутри `if`, `for`, `def`, `while`, `class` должны иметь отступ ровно 4 пробела.",
        )
    except SyntaxError as se:
        line_no = se.lineno or 1
        col_no = se.offset or 1
        visual = _build_visual_snippet(lines, line_no, col_no)
        raw_msg = str(se.msg or "")

        hint_uz = "Sintaksis qoidalarini, qavslar juftligini tekshiring."
        hint_ru = "Проверьте синтаксис и парность скобок."
        extra_desc_uz = raw_msg
        extra_desc_ru = raw_msg

        line_content = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""

        # Ikki nuqta ':' tekshiruvi
        if re.search(r"^\s*(?:if|elif|else|for|while|def|class|try|except|finally|with)\b", line_content) and not line_content.rstrip().endswith(":"):
            extra_desc_uz = "Qator oxirida `:` (ikki nuqta) qolib ketgan!"
            extra_desc_ru = "В конце строки пропущено двоеточие `:`!"
            hint_uz = "`if`, `for`, `def`, `while` va `class` qatorlari oxiriga `:` qo'yilishi shart."
            hint_ru = "После строк `if`, `for`, `def`, `while` и `class` обязательно ставится `:`."
        elif "unexpected eof" in raw_msg.lower():
            extra_desc_uz = "Qator oxirida qavs yoki qo'shtirnoq yopilmay qolgan."
            extra_desc_ru = "В конце строки не закрыта скобка или кавычка."
            hint_uz = "Ochilgan `(`, `[`, `{` qavslar yoki `\"`, `'` qo'shtirnoqlarni to'liq yoping."
            hint_ru = "Убедитесь, что все открытые скобки `(`, `[`, `{` и кавычки закрыты."
        elif "was never closed" in raw_msg.lower() or "unclosed" in raw_msg.lower():
            extra_desc_uz = f"Ochilgan qavs yopilmagan: {raw_msg}"
            extra_desc_ru = f"Открытая скобка не закрыта: {raw_msg}"
            hint_uz = "Har bir ochilgan qavsni mos jufti bilan yoping."
            hint_ru = "Закройте соответствующую открытую скобку."

        return LintResult(
            language="Python",
            line_number=line_no,
            column=col_no,
            error_type="SyntaxError",
            visual_snippet=visual,
            message_uz=f"`SyntaxError`: {extra_desc_uz}",
            message_ru=f"`SyntaxError`: {extra_desc_ru}",
            hint_uz=hint_uz,
            hint_ru=hint_ru,
        )
    except Exception:
        return None


def lint_json(code: str) -> LintResult | None:
    """JSON ma'lumotlarini tekshiradi."""
    lines = code.splitlines()
    try:
        json.loads(code)
        return None
    except json.JSONDecodeError as je:
        line_no = je.lineno or 1
        col_no = je.colno or 1
        visual = _build_visual_snippet(lines, line_no, col_no)
        raw_msg = str(je.msg or "")

        hint_uz = "JSON'da kalit va satrlar FAQAT ikkitalik qo'shtirnoqda `\"` bo'lishi, oxirgi elementdan keyin ortiqcha vergul `,` bo'lmasligi kerak."
        hint_ru = "В JSON ключи и строки должны быть строго в двойных кавычках `\"`, без лишней запятой в конце."

        return LintResult(
            language="JSON",
            line_number=line_no,
            column=col_no,
            error_type="JSONDecodeError",
            visual_snippet=visual,
            message_uz=f"JSON formati xatosi: {raw_msg}",
            message_ru=f"Ошибка формата JSON: {raw_msg}",
            hint_uz=hint_uz,
            hint_ru=hint_ru,
        )


def lint_html_or_jsx(code: str, is_jsx: bool = False) -> LintResult | None:
    """HTML yoki React JSX teglari balansi va atributlarini tekshiradi."""
    lines = code.splitlines()

    # 1. React JSX da `class=` ishlatilgan bo'lsa
    if is_jsx or re.search(r"<\s*[A-Z][A-Za-z0-9_]*|import\s+React|from\s+['\"]react['\"]", code):
        for idx, line in enumerate(lines):
            # String yoki comment ichida bo'lmagan class= tekshiruvi
            m = re.search(r"<[^>]*\b(class)=([\"'][^\"']*[\"'])", line)
            if m:
                line_no = idx + 1
                col_no = m.start(1) + 1
                visual = _build_visual_snippet(lines, line_no, col_no)
                return LintResult(
                    language="React (JSX)",
                    line_number=line_no,
                    column=col_no,
                    error_type="ReactJSXWarning",
                    visual_snippet=visual,
                    message_uz="React JSX da `class` o'rniga `className` ishlatilishi shart.",
                    message_ru="В React JSX вместо `class` должно использоваться `className`.",
                    hint_uz="React'da `class` bu JavaScript kalit so'zi bo'lgani uchun, CSS klasslari `className=\"...\"` deb yoziladi.",
                    hint_ru="В React атрибут стиля пишется как `className=\"...\"`.",
                )

    # 2. Teglar balansi (Stack-based parser)
    tag_pattern = re.compile(r"<\s*(/)?\s*([a-zA-Z0-9_\-]+)([^>]*)>", re.DOTALL)
    stack = []  # (tag_name, line_no, col_no)

    for idx, line in enumerate(lines):
        line_no = idx + 1
        for match in tag_pattern.finditer(line):
            is_closing = bool(match.group(1))
            tag_name = match.group(2).lower()
            attrs = match.group(3) or ""
            col_no = match.start() + 1

            # Self-closing tekshiruvi: <img ... /> yoki HTML void teglar
            is_self_closing = attrs.rstrip().endswith("/")

            if not is_jsx and tag_name in HTML_VOID_TAGS:
                continue

            # JSX da <img ...> yopilmagan bo'lsa
            if is_jsx and tag_name in HTML_VOID_TAGS and not is_self_closing:
                visual = _build_visual_snippet(lines, line_no, col_no)
                return LintResult(
                    language="React (JSX)",
                    line_number=line_no,
                    column=col_no,
                    error_type="JSXUnclosedVoidTag",
                    visual_snippet=visual,
                    message_uz=f"React JSX da `<{tag_name}>` tegi o'z-o'zidan yopilishi shart: `<{tag_name} ... />`",
                    message_ru=f"В React JSX тег `<{tag_name}>` должен быть самозакрывающимся: `<{tag_name} ... />`",
                    hint_uz=f"React JSX talabi: `<{tag_name}>` oxiriga `/>` belgisini qo'ying.",
                    hint_ru=f"В React JSX добавьте закрывающий слэш: `<{tag_name} ... />`.",
                )

            if is_self_closing:
                continue

            if not is_closing:
                stack.append((tag_name, line_no, col_no))
            else:
                if not stack:
                    visual = _build_visual_snippet(lines, line_no, col_no)
                    return LintResult(
                        language="HTML/JSX",
                        line_number=line_no,
                        column=col_no,
                        error_type="UnmatchedClosingTag",
                        visual_snippet=visual,
                        message_uz=f"Ortiqcha yoki ochilmagan yopuvchi teg: `</{tag_name}>`",
                        message_ru=f"Лишний закрывающий тег без открывающего: `</{tag_name}>`",
                        hint_uz="Ushbu teg yuqorida ochilganini tekshiring yoki ortiqcha bo'lsa olib tashlang.",
                        hint_ru="Проверьте, был ли открыт этот тег выше.",
                    )
                last_tag, open_line, open_col = stack.pop()
                if last_tag != tag_name:
                    visual = _build_visual_snippet(lines, line_no, col_no)
                    return LintResult(
                        language="HTML/JSX",
                        line_number=line_no,
                        column=col_no,
                        error_type="MismatchedTag",
                        visual_snippet=visual,
                        message_uz=f"Teglar chalkash yopilgan: `<{last_tag}>` ochilgan edi, lekin `</{tag_name}>` bilan yopilmoqda.",
                        message_ru=f"Нарушен порядок закрытия тегов: был открыт `<{last_tag}>`, но закрывается `</{tag_name}>`.",
                        hint_uz=f"Avval `<{last_tag}>` tegini `</{last_tag}>` bilan yoping, so'ng `</{tag_name}>` ni yoping.",
                        hint_ru=f"Сначала закройте тег `</{last_tag}>`, затем `</{tag_name}>`.",
                    )

    if stack:
        unclosed_tag, unclosed_line, unclosed_col = stack[-1]
        visual = _build_visual_snippet(lines, unclosed_line, unclosed_col)
        return LintResult(
            language="HTML/JSX",
            line_number=unclosed_line,
            column=unclosed_col,
            error_type="UnclosedTag",
            visual_snippet=visual,
            message_uz=f"`<{unclosed_tag}>` tegi ochilgan, lekin oxirigacha yopilmagan!",
            message_ru=f"Тег `<{unclosed_tag}>` открыт, но не закрыт!",
            hint_uz=f"Blok oxiriga mos `</{unclosed_tag}>` yopuvchi tegini qo'shing.",
            hint_ru=f"Добавьте закрывающий тег `</{unclosed_tag}>`.",
        )

    return None


def lint_css(code: str) -> LintResult | None:
    """CSS kodini tekshiradi (qavslar, ikki nuqta, nuqta-vergul)."""
    lines = code.splitlines()

    # 1. Jingalak qavslar tekshiruvi
    brace_stack = []
    for idx, line in enumerate(lines):
        line_no = idx + 1
        for col_idx, char in enumerate(line):
            if char == "{":
                brace_stack.append((line_no, col_idx + 1))
            elif char == "}":
                if not brace_stack:
                    visual = _build_visual_snippet(lines, line_no, col_idx + 1)
                    return LintResult(
                        language="CSS",
                        line_number=line_no,
                        column=col_idx + 1,
                        error_type="UnmatchedClosingBrace",
                        visual_snippet=visual,
                        message_uz="CSS'da ortiqcha yopuvchi jingalak qavs `}` mavjud.",
                        message_ru="Лишняя закрывающая фигурная скобка `}` в CSS.",
                        hint_uz="Ortiqcha `}` belgisini olib tashlang.",
                        hint_ru="Удалите лишнюю скобку `}`.",
                    )
                brace_stack.pop()

    if brace_stack:
        b_line, b_col = brace_stack[-1]
        visual = _build_visual_snippet(lines, b_line, b_col)
        return LintResult(
            language="CSS",
            line_number=b_line,
            column=b_col,
            error_type="UnclosedBrace",
            visual_snippet=visual,
            message_uz="CSS qoidasi uchun ochilgan `{` jingalak qavsi yopilmay qolgan.",
            message_ru="Открытая фигурная скобка `{` в CSS правиле не закрыта.",
            hint_uz="Selektor bloki oxiriga `}` qo'ying.",
            hint_ru="Закройте блок правила фигурной скобкой `}`.",
        )

    # 2. Xususiyat (property) va qiymat sintaksisi (masalan: `color red;` yoki `color: red`)
    inside_rule = False
    for idx, line in enumerate(lines):
        line_no = idx + 1
        stripped = line.strip()
        if not stripped or stripped.startswith("/*") or stripped.startswith("//"):
            continue

        if "{" in stripped:
            inside_rule = True
            continue
        if "}" in stripped:
            inside_rule = False
            continue

        if inside_rule:
            # Ikki nuqta ':' qolib ketgan bo'lsa: masalan: `background-color #333;`
            m_no_colon = re.match(r"^([a-zA-Z\-]+)\s+([#a-zA-Z0-9\(\)\s,\.\-]+);?$", stripped)
            if m_no_colon and ":" not in stripped:
                prop = m_no_colon.group(1)
                val = m_no_colon.group(2)
                col_no = line.find(prop) + len(prop) + 1
                visual = _build_visual_snippet(lines, line_no, col_no)
                return LintResult(
                    language="CSS",
                    line_number=line_no,
                    column=col_no,
                    error_type="MissingColon",
                    visual_snippet=visual,
                    message_uz=f"CSS xususiyati (`{prop}`) va qiymati orasida `:` (ikki nuqta) qolib ketgan.",
                    message_ru=f"Пропущено двоеточие `:` между свойством (`{prop}`) и значением в CSS.",
                    hint_uz=f"To'g'risi: `{prop}: {val};`",
                    hint_ru=f"Правильно: `{prop}: {val};`",
                )

    return None


def lint_javascript(code: str) -> LintResult | None:
    """JavaScript / Node.js qavslar va stringlar balansini tekshiradi."""
    lines = code.splitlines()

    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}

    in_string = None  # '"', "'", '`'
    in_line_comment = False
    in_block_comment = False

    for idx, line in enumerate(lines):
        line_no = idx + 1
        col = 0
        in_line_comment = False

        while col < len(line):
            char = line[col]
            next_char = line[col + 1] if col + 1 < len(line) else ""

            # Izohlar (Comments)
            if not in_string:
                if in_block_comment:
                    if char == "*" and next_char == "/":
                        in_block_comment = False
                        col += 2
                        continue
                    col += 1
                    continue
                if char == "/" and next_char == "*":
                    in_block_comment = True
                    col += 2
                    continue
                if char == "/" and next_char == "/":
                    in_line_comment = True
                    break

            # Satrlar (Strings)
            if char in ('"', "'", "`"):
                # Escape belgisini tekshirish
                if col > 0 and line[col - 1] == "\\":
                    pass
                else:
                    if in_string == char:
                        in_string = None
                    elif in_string is None:
                        in_string = char

            # Qavslar
            if not in_string and not in_block_comment and not in_line_comment:
                if char in ("(", "[", "{"):
                    stack.append((char, line_no, col + 1))
                elif char in (")", "]", "}"):
                    if not stack:
                        visual = _build_visual_snippet(lines, line_no, col + 1)
                        return LintResult(
                            language="JavaScript",
                            line_number=line_no,
                            column=col + 1,
                            error_type="UnmatchedClosingBracket",
                            visual_snippet=visual,
                            message_uz=f"Ortiqcha yoki ochilmagan yopuvchi qavs: `{char}`",
                            message_ru=f"Лишняя закрывающая скобка: `{char}`",
                            hint_uz="Ortiqcha qavsni olib tashlang yoki ochilgan qavslar bilan tekshiring.",
                            hint_ru="Удалите лишнюю скобку или проверьте соответствие.",
                        )
                    last_open, o_line, o_col = stack.pop()
                    if last_open != pairs[char]:
                        visual = _build_visual_snippet(lines, line_no, col + 1)
                        return LintResult(
                            language="JavaScript",
                            line_number=line_no,
                            column=col + 1,
                            error_type="MismatchedBracket",
                            visual_snippet=visual,
                            message_uz=f"Qavslar mos kelmadi: `{last_open}` ochilgan edi, lekin `{char}` bilan yopilmoqda.",
                            message_ru=f"Несоответствие скобок: была открыта `{last_open}`, но закрывается `{char}`.",
                            hint_uz=f"Mos yopuvchi qavsdan foydalaning.",
                            hint_ru=f"Используйте правильную закрывающую скобку.",
                        )

            col += 1

    if in_string == "`":
        return LintResult(
            language="JavaScript",
            line_number=len(lines),
            column=1,
            error_type="UnclosedTemplateLiteral",
            visual_snippet=_build_visual_snippet(lines, len(lines), 1),
            message_uz="Template literal (`` ` ``) satri yopilmay qolgan.",
            message_ru="Шаблонная строка (`` ` ``) не закрыта.",
            hint_uz="Satr oxiriga teskari qo'shtirnoq `` ` `` qo'ying.",
            hint_ru="Закройте строку обратной кавычкой `` ` ``.",
        )

    if stack:
        last_open, o_line, o_col = stack[-1]
        bracket_names = {"(": "dumaloq `(`", "[": "to'rtburchak `[`", "{": "jingalak `{`"}
        bracket_names_ru = {"(": "круглая `(`", "[": "квадратная `[`", "{": "фигурная `{`"}
        visual = _build_visual_snippet(lines, o_line, o_col)
        return LintResult(
            language="JavaScript",
            line_number=o_line,
            column=o_col,
            error_type="UnclosedBracket",
            visual_snippet=visual,
            message_uz=f"Ochilgan {bracket_names.get(last_open, last_open)} qavs oxirigacha yopilmagan!",
            message_ru=f"Открытая {bracket_names_ru.get(last_open, last_open)} скобка не закрыта!",
            hint_uz=f"Mos yopuvchi qavsni qo'shing.",
            hint_ru=f"Добавьте закрывающую скобку.",
        )

    return None


def format_lint_response(lint: LintResult, is_ru: bool = False) -> str:
    """O'quvchi uchun chiroyli, tushunarli vizual diagnostika xabarini yaratadi."""
    title = (
        f"🔍 **Обнаружена ошибка синтаксиса ({lint.language}, строка {lint.line_number}):**"
        if is_ru else
        f"🔍 **Sintaksis xatosi aniqlandi ({lint.language}, {lint.line_number}-qator):**"
    )

    msg = lint.message_ru if is_ru else lint.message_uz
    hint = lint.hint_ru if is_ru else lint.hint_uz
    hint_title = "💡 **Совет наставника:**" if is_ru else "💡 **Ustoz maslahati:**"

    return (
        f"{title}\n\n"
        f"```text\n{lint.visual_snippet}\n```\n\n"
        f"❌ {msg}\n\n"
        f"{hint_title} {hint}\n\n"
        f"_Tuzatib qayta yuboring, birga tekshiramiz! 😊_"
    )


def check_code_snippets(
    text: str,
    file_name: str | None = None,
    is_ru: bool = False,
) -> tuple[str | None, str | None]:
    """
    Matn yoki yuklangan faylni tahlil qilib, agar aniq sintaktik xato bo'lsa,
    (formatted_error_text, topic_name) qaytaradi.
    Xatolik bo'lmasa (None, None) qaytaradi.
    """
    if not text:
        return None, None

    # 1. Fayl kengaytmasi orqali aniqlash
    ext = (file_name.rsplit(".", 1)[-1].lower() if file_name and "." in file_name else "")

    # 2. Markdown kod bloklarini ajratish
    code_blocks = re.findall(r"```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```", text)

    # Agar matn to'liq kod bo'lsa (fayl yuklangan yoki to'g'ridan-to'g'ri kod tashlangan)
    if not code_blocks:
        stripped = text.strip()
        if ext or "\n" in stripped or any(kw in stripped for kw in ("def ", "class ", "import ", "function", "const ", "<div", "SELECT ", "{\n")):
            code_blocks = [(ext or "", stripped)]

    for lang_tag, code in code_blocks:
        code_clean = code.strip()
        if not code_clean or len(code_clean) < 8:
            continue

        l_lower = lang_tag.lower() if lang_tag else ext

        # Python
        if l_lower in ("python", "py") or (not l_lower and ("def " in code_clean or "import " in code_clean or "print(" in code_clean)):
            res = lint_python(code_clean)
            if res:
                return format_lint_response(res, is_ru), "syntax_indentation"

        # JSON
        if l_lower == "json" or (not l_lower and code_clean.startswith("{") and code_clean.endswith("}") and '"' in code_clean):
            res = lint_json(code_clean)
            if res:
                return format_lint_response(res, is_ru), "data_structures"

        # HTML / React JSX
        if l_lower in ("html", "htm", "jsx", "tsx") or (not l_lower and "<" in code_clean and ">" in code_clean and re.search(r"<\s*[a-zA-Z0-9_\-]+", code_clean)):
            is_jsx = l_lower in ("jsx", "tsx") or "className=" in code_clean or "import React" in code_clean
            res = lint_html_or_jsx(code_clean, is_jsx=is_jsx)
            if res:
                return format_lint_response(res, is_ru), "syntax_indentation"

        # CSS
        if l_lower in ("css", "scss") or (not l_lower and "{" in code_clean and "}" in code_clean and ":" in code_clean and ("color" in code_clean or "margin" in code_clean or "display" in code_clean)):
            res = lint_css(code_clean)
            if res:
                return format_lint_response(res, is_ru), "syntax_indentation"

        # JavaScript / Node.js
        if l_lower in ("javascript", "js", "ts", "node") or (not l_lower and ("const " in code_clean or "let " in code_clean or "function " in code_clean or "=>" in code_clean)):
            res = lint_javascript(code_clean)
            if res:
                return format_lint_response(res, is_ru), "syntax_indentation"

    return None, None
