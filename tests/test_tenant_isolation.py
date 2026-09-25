"""
Multi-tenant izolyatsiya va xavfsizlik testlari:
  • har bir mijozning ma'lumotlari alohida bazada, boshqalar bilan aralashmaydi;
  • mijoz sozlamalari mentorning global sozlamalariga ta'sir qilmaydi;
  • obunalar/tokenlar doimo asosiy (core) bazada;
  • Telegram initData imzosi tekshiriladi, soxta so'rovlar rad etiladi;
  • mijoz tokeni Super Admin endpointlariga kira olmaydi.
"""

import tests._isolated_env  # noqa: F401  (birinchi bo'lib import qilinadi)

import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from config import config
from services.memory_service import memory_service
from services.mongo_memory_service import mongo_memory_service
from services.secret_box import decrypt_secret, encrypt_secret
from services.tenant_context import get_tenant_id, tenant_scope

CLIENT_A = 700000001
CLIENT_B = 700000002


class TestTenantDataIsolation(unittest.TestCase):
    def test_learned_facts_do_not_mix(self):
        with tenant_scope(CLIENT_A):
            memory_service.add_learned_fact("narx_a", "Divan 3 mln")
        with tenant_scope(CLIENT_B):
            memory_service.add_learned_fact("narx_b", "Konsultatsiya 200 ming")

        with tenant_scope(CLIENT_A):
            topics_a = {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)}
        with tenant_scope(CLIENT_B):
            topics_b = {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)}
        topics_main = {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)}

        self.assertIn("narx_a", topics_a)
        self.assertNotIn("narx_b", topics_a)
        self.assertIn("narx_b", topics_b)
        self.assertNotIn("narx_a", topics_b)
        self.assertNotIn("narx_a", topics_main)
        self.assertNotIn("narx_b", topics_main)

    def test_each_tenant_has_own_db_file(self):
        with tenant_scope(CLIENT_A):
            memory_service.add_message(chat_id=555, role="user", content="salom A")
        with tenant_scope(CLIENT_B):
            memory_service.add_message(chat_id=555, role="user", content="salom B")
            history_b = [m.content for m in memory_service.get_history(555)]
        with tenant_scope(CLIENT_A):
            history_a = [m.content for m in memory_service.get_history(555)]
        self.assertIn("salom A", history_a)
        self.assertNotIn("salom B", history_a)
        self.assertIn("salom B", history_b)
        self.assertNotIn("salom A", history_b)
        self.assertTrue(memory_service.tenant_db_path(CLIENT_A).exists())
        self.assertNotEqual(memory_service.tenant_db_path(CLIENT_A), memory_service.db_path)

    def test_client_settings_do_not_touch_main(self):
        memory_service.set_setting("auto_reply_enabled", "true")
        with tenant_scope(CLIENT_A):
            memory_service.set_setting("auto_reply_enabled", "false")
            self.assertEqual(memory_service.get_setting("auto_reply_enabled"), "false")
        self.assertEqual(memory_service.get_setting("auto_reply_enabled"), "true")

    def test_default_value_is_not_cached(self):
        self.assertEqual(memory_service.get_setting("no_such_key_xyz", "a"), "a")
        self.assertEqual(memory_service.get_setting("no_such_key_xyz", "b"), "b")
        self.assertIsNone(memory_service.get_setting("no_such_key_xyz"))

    def test_client_topics_start_empty_and_isolated(self):
        with tenant_scope(CLIENT_A):
            self.assertEqual(memory_service.get_curriculum_topics(), [])
            memory_service.add_curriculum_topic("Mebel")
            self.assertEqual(memory_service.get_curriculum_topics(), ["Mebel"])
        with tenant_scope(CLIENT_B):
            self.assertEqual(memory_service.get_curriculum_topics(), [])
        self.assertNotIn("Mebel", memory_service.get_curriculum_topics())

    def test_reminders_isolated(self):
        with tenant_scope(CLIENT_A):
            memory_service.add_reminder(chat_id=CLIENT_A, reminder_text="A eslatma", remind_at="2099-01-01 10:00:00", creator_id=CLIENT_A)
            texts_a = [r.get("text") or r.get("reminder_text") for r in memory_service.get_active_reminders(50)]
        with tenant_scope(CLIENT_B):
            texts_b = [r.get("text") or r.get("reminder_text") for r in memory_service.get_active_reminders(50)]
        texts_main = [r.get("text") or r.get("reminder_text") for r in memory_service.get_active_reminders(50)]
        self.assertIn("A eslatma", texts_a)
        self.assertNotIn("A eslatma", texts_b)
        self.assertNotIn("A eslatma", texts_main)

    def test_legacy_rows_migrate_into_tenant(self):
        legacy_uid = 700000099
        with memory_service._get_core_connection() as conn:
            conn.execute(
                "INSERT INTO learned_memory (category, topic, content, user_id) VALUES ('rule', 'eski_qoida', 'eski mazmun', ?)",
                (legacy_uid,),
            )
            conn.commit()
        with tenant_scope(legacy_uid):
            topics = {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)}
        self.assertIn("eski_qoida", topics)


class TestControlPlane(unittest.TestCase):
    def test_subscription_written_to_core_even_inside_tenant_scope(self):
        with tenant_scope(CLIENT_A):
            memory_service.upsert_subscription(user_id=CLIENT_A, days=30, business_name="A Biznes")
        with memory_service._get_core_connection() as conn:
            row = conn.execute("SELECT business_name FROM user_subscriptions WHERE user_id = ?", (CLIENT_A,)).fetchone()
        self.assertEqual(row[0], "A Biznes")

    def test_tokens_live_in_core(self):
        from web_app import generate_admin_token, get_token_user_id, verify_admin_token
        with tenant_scope(CLIENT_A):
            token = generate_admin_token(user_id=CLIENT_A)
        self.assertTrue(verify_admin_token(token))
        with tenant_scope(CLIENT_B):
            self.assertEqual(get_token_user_id(token), CLIENT_A)

    def test_session_string_encrypted_at_rest(self):
        memory_service.upsert_subscription(user_id=CLIENT_B, days=30)
        secret = "1BVtsOK" + "x" * 120
        memory_service.save_session_string(CLIENT_B, secret)
        with memory_service._get_core_connection() as conn:
            raw = conn.execute("SELECT session_string FROM user_subscriptions WHERE user_id = ?", (CLIENT_B,)).fetchone()[0]
        self.assertTrue(raw.startswith("enc:v1:"))
        self.assertNotIn(secret, raw)
        self.assertEqual(memory_service.get_subscription(CLIENT_B)["session_string"], secret)

    def test_secret_box_legacy_plaintext_passthrough(self):
        self.assertEqual(decrypt_secret("plain-old-session"), "plain-old-session")
        self.assertEqual(decrypt_secret(encrypt_secret("abc")), "abc")

    def test_mongo_disabled_inside_tenant_scope(self):
        # Hatto Mongo ulangan bo'lsa ham, tenant kontekstida asosiy kolleksiyalarga yozilmaydi
        original = mongo_memory_service.is_core_connected
        mongo_memory_service.is_core_connected = lambda: True
        try:
            self.assertTrue(mongo_memory_service.is_connected())
            with tenant_scope(CLIENT_A):
                self.assertFalse(mongo_memory_service.is_connected())
        finally:
            mongo_memory_service.is_core_connected = original

    def test_mentor_ids_map_to_main_tenant(self):
        with tenant_scope(8105823872):
            self.assertEqual(get_tenant_id(), 0)
        with tenant_scope(CLIENT_A):
            self.assertEqual(get_tenant_id(), CLIENT_A)
        self.assertEqual(get_tenant_id(), 0)


def _signed_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    params = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAH", "user": json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


class TestWebSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from web_app import setup_web_app_routes
        self._orig_bot_token = config.bot_token
        config.bot_token = "123456:TEST-TOKEN"
        memory_service.upsert_subscription(user_id=CLIENT_A, days=30, business_name="A Biznes")
        app = web.Application()
        setup_web_app_routes(app, lambda: None)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        config.bot_token = self._orig_bot_token

    async def _auth(self, payload: dict):
        resp = await self.client.post("/api/auth", json=payload)
        return resp.status, await resp.json()

    async def test_forged_user_is_rejected(self):
        status, data = await self._auth({"user": {"id": 8105823872, "username": "mentor_cc"}, "user_id": 8105823872})
        self.assertEqual(status, 403)
        self.assertFalse(data.get("ok"))

    async def test_old_master_token_rejected(self):
        status, _ = await self._auth({"token": "mentor_cc_master_8105823872"})
        self.assertEqual(status, 403)
        resp = await self.client.get("/api/status", headers={"Authorization": "Bearer mentor_cc_master_8105823872"})
        self.assertEqual(resp.status, 403)

    async def test_bad_signature_rejected(self):
        init_data = _signed_init_data({"id": CLIENT_A}, "999:WRONG")
        status, _ = await self._auth({"initData": init_data})
        self.assertEqual(status, 403)

    async def test_expired_init_data_rejected(self):
        init_data = _signed_init_data({"id": CLIENT_A}, config.bot_token, auth_date=int(time.time()) - 86400 * 30)
        status, _ = await self._auth({"initData": init_data})
        self.assertEqual(status, 403)

    async def test_client_login_and_isolation(self):
        status, data = await self._auth({"initData": _signed_init_data({"id": CLIENT_A}, config.bot_token)})
        self.assertEqual(status, 200)
        self.assertFalse(data["user"]["is_super_admin"])
        headers = {"Authorization": f"Bearer {data['token']}"}

        # Super Admin endpointlari yopiq, lekin qulflamaydi (role_forbidden)
        for path in ("/api/backup", "/api/ai_metrics", "/api/autonomous-brain/status", "/api/students"):
            resp = await self.client.get(path, headers=headers)
            self.assertEqual(resp.status, 403, path)
            self.assertTrue((await resp.json()).get("role_forbidden"), path)

        # Mijoz o'z bilimini qo'shadi -> faqat o'z bazasida
        resp = await self.client.post("/api/learned-facts/add", headers=headers, json={"topic": "yetkazish", "content": "Bepul"})
        self.assertTrue((await resp.json())["ok"])
        with tenant_scope(CLIENT_A):
            self.assertIn("yetkazish", {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)})
        self.assertNotIn("yetkazish", {f["topic"] for f in memory_service.get_all_learned_facts(limit=100)})

        # Mijoz avto-javobni o'chirsa, mentorning global sozlamasi o'zgarmaydi
        before = config.auto_reply_enabled
        resp = await self.client.post("/api/toggle", headers=headers, json={"feature": "auto_reply", "enabled": False})
        self.assertTrue((await resp.json())["ok"])
        self.assertEqual(config.auto_reply_enabled, before)
        with tenant_scope(CLIENT_A):
            self.assertEqual(memory_service.get_setting("auto_reply_enabled"), "false")

        # Status mijozning o'z holatini qaytaradi va HSS kodni oshkor qilmaydi
        resp = await self.client.get("/api/status", headers=headers)
        body = await resp.json()
        self.assertFalse(body["auto_reply_enabled"])
        self.assertIsNone(body["ai_metrics"])
        self.assertNotIn("session_string", json.dumps(body))

    async def test_super_admin_login_via_signed_init_data(self):
        status, data = await self._auth({"initData": _signed_init_data({"id": 8105823872}, config.bot_token)})
        self.assertEqual(status, 200)
        self.assertTrue(data["user"]["is_super_admin"])
        self.assertNotEqual(data["token"], "mentor_cc_master_8105823872")


if __name__ == "__main__":
    unittest.main()
