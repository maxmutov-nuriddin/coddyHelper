"""
Testlar uchun izolyatsiyalangan muhit: haqiqiy coddy_memory.db va MongoDB Atlas'ga TEGMAYDI.
Har bir test faylining eng boshida import qilinishi shart (boshqa loyiha modullaridan oldin).
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# MongoDB o'chiriladi (bo'sh URI), mijoz sessiyalari ishga tushirilmaydi
os.environ["MONGODB_URI"] = ""
os.environ["CLIENT_SESSIONS_MODE"] = "off"
os.environ.setdefault("SESSION_ENCRYPTION_KEY", "test-only-key")

TEST_DIR = Path(tempfile.mkdtemp(prefix="coddy_test_"))

import services.memory_service as _ms  # noqa: E402

_ms.TENANTS_DIR = TEST_DIR / "tenants"
_ms.memory_service.db_path = TEST_DIR / "main.db"
_ms.memory_service._initialized_tenants.clear()
_ms.memory_service._settings_cache_by_tenant.clear()
_ms.memory_service._init_db()
