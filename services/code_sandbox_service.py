"""
Safe Code Runner Sandbox Service.
O'quvchilar yuborgan Python kodini xavfsiz, izolyatsiyalangan va tezkor (0.5s timeout)
sandboxda sinab ko'rib, real runtime xatoliklar (IndexError, TypeError, ZeroDivisionError va h.k.)
hamda natijani (stdout/stderr) aniqlab beruvchi xizmat.
"""

import ast
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Xavfsizlik maqsadida taqiqlangan modullar va funksiyalar ro'yxati
DANGEROUS_PATTERNS = [
    r"\bimport\s+(?:os|subprocess|sys|shutil|ctypes|socket|requests|urllib|http|pathlib|posix|winreg|pty)\b",
    r"\bfrom\s+(?:os|subprocess|sys|shutil|ctypes|socket|requests|urllib|http|pathlib|posix|winreg|pty)\s+import\b",
    r"__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bopen\s*\(",
    r"\bbreakpoint\s*\(",
    r"\bcompile\s*\(",
    r"os\.(?:system|popen|remove|unlink|rmdir|mkdir|chmod|rename)",
    r"shutil\.(?:rmtree|copy|move)",
    r"subprocess\.(?:run|Popen|call|check_output)",
]

DANGEROUS_REGEX = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)


@dataclass
class SandboxResult:
    executed: bool
    success: bool
    stdout: str = ""
    stderr: str = ""
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_line: Optional[int] = None
    timed_out: bool = False
    security_blocked: bool = False
    duration_ms: int = 0


def _is_potentially_unsafe(code: str) -> tuple[bool, str]:
    """Kodda tizimga zarar yetkazishi mumkin bo'lgan xavfli buyruqlar borligini tekshiradi."""
    match = DANGEROUS_REGEX.search(code)
    if match:
        return True, f"Xavfsizlik cheklovi: '{match.group(0)}' chaqiruvi taqiqlangan."
    return False, ""


def _parse_traceback(stderr: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Python traceback matnidan xatolik turi, xabari va qatorini ajratib oladi."""
    if not stderr:
        return None, None, None

    error_type = None
    error_message = None
    error_line = None

    # Qator raqamini topish: File "<...>", line 4, in <module>
    line_matches = re.findall(r'line\s+(\d+)', stderr)
    if line_matches:
        try:
            error_line = int(line_matches[-1])
        except ValueError:
            pass

    # Xatolik nomi va tavsifi: IndexError: list index out of range
    lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
    if lines:
        last_line = lines[-1]
        err_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*Error|[A-Za-z_][A-Za-z0-9_]*Exception):\s*(.*)$", last_line)
        if err_match:
            error_type = err_match.group(1)
            error_message = err_match.group(2).strip()
        else:
            # Ba'zi istisnolar (masalan, KeyboardInterrupt)
            error_type = last_line.split(":")[0].strip()
            error_message = last_line

    return error_type, error_message, error_line


def execute_student_python_code(code: str, timeout_seconds: float = 0.5) -> SandboxResult:
    """
    O'quvchi yuborgan Python kodini xavfsiz izolyatsiyalangan alohida jarayonda bajaradi.
    Maksimal vaqt: 0.5 soniya (cheksiz tsikllarni to'xtatish uchun).
    """
    if not code or not code.strip():
        return SandboxResult(executed=False, success=True)

    # 1. Kod hajmini tekshirish (hujumlar va xotira to'lishining oldini olish)
    if len(code) > 15000:
        return SandboxResult(
            executed=False,
            success=False,
            stderr="Kod hajmi juda katta (maksimal 15,000 belgi).",
            security_blocked=True
        )

    # 2. Xavfsizlik tahlili (Sandbox Guard)
    unsafe, reason = _is_potentially_unsafe(code)
    if unsafe:
        return SandboxResult(
            executed=False,
            success=False,
            stderr=reason,
            security_blocked=True
        )

    # 3. Vaqtinchalik faylga xavfsiz yozish
    start_time = time.time()
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
            tf.write(code)
            temp_file = tf.name

        # Xavfsiz, cheklangan environment
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }

        # Subprocess orqali ishga tushirish
        proc = subprocess.run(
            [sys.executable, "-I", temp_file],  # -I flagi izolyatsiya rejimini yoqadi
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=safe_env,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        stdout = proc.stdout[:2000] if proc.stdout else ""
        stderr = proc.stderr[:2000] if proc.stderr else ""

        if proc.returncode == 0:
            return SandboxResult(
                executed=True,
                success=True,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms
            )
        else:
            err_type, err_msg, err_line = _parse_traceback(stderr)
            return SandboxResult(
                executed=True,
                success=False,
                stdout=stdout,
                stderr=stderr,
                error_type=err_type,
                error_message=err_msg,
                error_line=err_line,
                duration_ms=duration_ms
            )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        return SandboxResult(
            executed=True,
            success=False,
            timed_out=True,
            error_type="TimeoutError",
            error_message=f"Kod bajarilishi {timeout_seconds}s dan oshib ketdi. Cheksiz tsikl (infinite loop) ehtimoli yuqori.",
            stderr=f"Timeout: Kod {timeout_seconds} soniya ichida yakunlanmadi.",
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning("Sandboxda kod bajarishda kutilmagan xatolik: %s", e)
        return SandboxResult(
            executed=False,
            success=False,
            stderr=str(e),
            duration_ms=duration_ms
        )
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def format_sandbox_context_for_ai(result: SandboxResult) -> str:
    """
    Sandbox natijasini AI prompti uchun qulay formatga o'tkazib beradi.
    Model ushbu ma'lumot asosida taxmin qilmasdan, talabaga 100% aniq yo'nalish beradi.
    """
    if not result.executed:
        if result.security_blocked:
            return f"\n[SANDBOX ESLATMASI]: O'quvchi kodi xavfsizlik chekloviga uchradi ({result.stderr})."
        return ""

    if result.timed_out:
        return (
            f"\n[REAL RUNTIME KOD TEKSHIRUVI NATIJASI]:\n"
            f"Holat: ⏳ Cheksiz tsikl (Timeout {result.duration_ms}ms).\n"
            f"Tafsilot: Kod hech qachon to'xtamaydigan tsiklga (masalan, while True yoki noto'g'ri shart) tushib qolgan.\n"
            f"Vazifangiz: O'quvchiga uning kodi qaysi tsiklda to'xtamay qolganini tushuntirib, shartni to'g'irlashga yo'l ko'rsating."
        )

    if not result.success:
        err_info = []
        if result.error_type:
            err_info.append(f"Xatolik turi: {result.error_type}")
        if result.error_line:
            err_info.append(f"Xatolik yuz bergan qator: {result.error_line}-qator")
        if result.error_message:
            err_info.append(f"Xatolik xabari: {result.error_message}")
        
        info_str = " | ".join(err_info)
        return (
            f"\n[REAL RUNTIME KOD TEKSHIRUVI NATIJASI]:\n"
            f"Holat: ❌ Runtime Xatolik ({info_str}).\n"
            f"Stdout: {result.stdout.strip() if result.stdout else '(chiqish yoq)'}\n"
            f"Vazifangiz: Ushbu xatolik sababini o'quvchiga Sokratik uslubda (tayyor kod bermasdan) tushuntirib bering."
        )

    return (
        f"\n[REAL RUNTIME KOD TEKSHIRUVI NATIJASI]:\n"
        f"Holat: ✅ Kod xatosiz bajarildi ({result.duration_ms}ms).\n"
        f"Chiqarilgan natija (stdout):\n{result.stdout.strip() if result.stdout else '(chiqish yoq)'}\n"
    )
