"""
Mijoz (tenant) bazalarining doimiy saqlanishi.

Render.com konteyneri qayta ishga tushganda lokal fayllar o'chadi. Har bir mijozning
tenants/tenant_<id>.db fayli o'zgarganda MongoDB'dagi `system_core.tenant_snapshots`
kolleksiyasiga to'liq (gzip) nusxasi yoziladi va kerak bo'lganda qayta tiklanadi.
Shu tariqa mijoz ma'lumotlari:
  - boshqa mijozlar va mentor ma'lumotlari bilan aralashmaydi (alohida fayl);
  - restart/deploydan keyin yo'qolmaydi.
"""

import asyncio
import logging
import sqlite3
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# {tenant_id: oxirgi yuklangan faylning mtime qiymati}
_last_synced_mtime: dict[int, float] = {}


def _tenants_dir() -> Path:
    from services.memory_service import TENANTS_DIR
    return TENANTS_DIR


def restore_tenant_snapshot(tenant_id: int, target_path: Path) -> bool:
    """Bulutdagi snapshotni lokal faylga yozadi (fayl hali mavjud bo'lmaganda chaqiriladi)."""
    from services.mongo_memory_service import mongo_memory_service
    data = mongo_memory_service.load_tenant_snapshot(tenant_id)
    if not data:
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = target_path.with_suffix(".restore")
    tmp.write_bytes(data)
    tmp.replace(target_path)
    try:
        _last_synced_mtime[int(tenant_id)] = target_path.stat().st_mtime
    except Exception:
        pass
    return True


def _consistent_copy_bytes(db_path: Path) -> bytes:
    """Ishlab turgan SQLite bazasining izchil (consistent) nusxasini oladi (sqlite backup API)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / "snapshot.db"
        src = sqlite3.connect(str(db_path), timeout=10.0)
        dst = sqlite3.connect(str(tmp_file))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return tmp_file.read_bytes()


def snapshot_tenant(tenant_id: int, force: bool = False) -> bool:
    """Tenant bazasi o'zgargan bo'lsa (yoki force=True), bulutga yuklaydi."""
    from services.mongo_memory_service import mongo_memory_service
    from services.memory_service import memory_service
    tid = int(tenant_id)
    path = memory_service.tenant_db_path(tid)
    if not path.exists():
        return False
    mtime = path.stat().st_mtime
    if not force and _last_synced_mtime.get(tid) == mtime:
        return False
    try:
        data = _consistent_copy_bytes(path)
    except Exception as e:
        logger.error("Tenant %s bazasidan nusxa olishda xatolik: %s", tid, e)
        return False
    if mongo_memory_service.save_tenant_snapshot(tid, data):
        _last_synced_mtime[tid] = mtime
        logger.debug("☁️ Tenant %s snapshoti bulutga saqlandi (%d bayt).", tid, len(data))
        return True
    return False


def snapshot_all_tenants(force: bool = False) -> int:
    """Barcha mavjud tenant bazalarini tekshirib, o'zgarganlarini bulutga yuklaydi."""
    tdir = _tenants_dir()
    if not tdir.exists():
        return 0
    saved = 0
    for f in tdir.glob("tenant_*.db"):
        try:
            tid = int(f.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if snapshot_tenant(tid, force=force):
            saved += 1
    return saved


def delete_tenant_data(tenant_id: int) -> None:
    """Mijoz butunlay o'chirilganda uning lokal bazasi va bulutdagi snapshotini o'chiradi."""
    from services.mongo_memory_service import mongo_memory_service
    from services.memory_service import memory_service
    tid = int(tenant_id)
    path = memory_service.tenant_db_path(tid)
    try:
        path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Tenant %s faylini o'chirishda ogohlantirish: %s", tid, e)
    memory_service._initialized_tenants.discard(tid)
    memory_service._settings_cache_by_tenant.pop(tid, None)
    _last_synced_mtime.pop(tid, None)
    mongo_memory_service.delete_tenant_snapshot(tid)


async def tenant_persistence_worker(interval_seconds: int = 45) -> None:
    """Fon xizmati: har `interval_seconds` da o'zgargan tenant bazalarini bulutga saqlaydi."""
    logger.info("☁️ Tenant bazalarini bulutga saqlash xizmati ishga tushdi.")
    await asyncio.sleep(20)
    while True:
        try:
            from services.instance_lease import instance_lease
            # Faqat mijoz sessiyalarini yuritayotgan (lease egasi) server yozadi —
            # aks holda eskirgan lokal nusxa bulutdagi yangi ma'lumotni bosib ketishi mumkin.
            if instance_lease.is_holder:
                await asyncio.to_thread(snapshot_all_tenants)
        except Exception as e:
            logger.warning("Tenant snapshot xizmatida ogohlantirish: %s", e)
        await asyncio.sleep(interval_seconds)
