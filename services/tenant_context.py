"""
Multi-tenant kontekst (har bir obunachining izolyatsiyalangan "dunyosi").

Tenant ID:
  0            -> Super Admin (@mentor_cc) — asosiy coddy_memory.db va asosiy MongoDB kolleksiyalari
  <user_id>    -> Obunachi mijoz — tenants/tenant_<user_id>.db (boshqalar bilan aralashmaydi)

ContextVar asyncio tasklari bo'ylab avtomatik meros qilinadi: handler ichida
tenant_scope() ochilsa, undan yaratilgan barcha ichki tasklar ham shu tenant bazasida ishlaydi.
Standart qiymat 0 bo'lgani uchun mavjud (mentor) oqimlari hech qanday o'zgarishsiz ishlaydi.
"""

from contextlib import contextmanager
from contextvars import ContextVar

MAIN_TENANT_ID = 0

_current_tenant: ContextVar[int] = ContextVar("coddy_current_tenant", default=MAIN_TENANT_ID)


def get_tenant_id() -> int:
    """Joriy tenant ID (0 = Super Admin / asosiy baza)."""
    return _current_tenant.get()


def is_main_tenant() -> bool:
    """Joriy kontekst Super Admin (asosiy baza) ekanini tekshiradi."""
    return _current_tenant.get() == MAIN_TENANT_ID


def _normalize(tenant_id) -> int:
    try:
        tid = int(tenant_id or 0)
    except (TypeError, ValueError):
        return MAIN_TENANT_ID
    if tid < 0:
        return MAIN_TENANT_ID
    try:
        from config import MENTOR_IDS
        if tid in MENTOR_IDS:
            return MAIN_TENANT_ID
    except Exception:
        pass
    return tid


@contextmanager
def tenant_scope(tenant_id):
    """Berilgan tenant bazasida ishlash uchun kontekst (Super Admin ID lari avtomatik 0 ga aylanadi)."""
    token = _current_tenant.set(_normalize(tenant_id))
    try:
        yield
    finally:
        _current_tenant.reset(token)
