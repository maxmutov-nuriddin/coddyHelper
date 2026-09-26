"""
Mijoz agenti handlerining xulq-atvori (Telegram'siz, soxta hodisalar bilan):
  • begona xabariga javob FAQAT mijoz tenant kontekstida yaratiladi;
  • egasining `ai ...` buyrug'i ReAct agentga yo'naltiriladi, begonaniki — yo'q;
  • egasi chatga o'zi yozsa, AI shu chatda jim turadi;
  • botlar, Telegram xizmat xabarlari (777000) va kanallar e'tiborsiz qoldiriladi.
"""

import tests._isolated_env  # noqa: F401

import asyncio
import itertools
import unittest
from types import SimpleNamespace

from services.client_session_manager import ClientSessionManager
from services.memory_service import memory_service
from services.tenant_context import get_tenant_id

OWNER = 700000501
AGENT_ACCOUNT = 700000501  # agent egasining o'z akkauntida ishlaydi
STRANGER = 900000001

# Har bir make_event() chaqiruvi (msg_id berilmasa) o'ziga xos xabar ID olishi kerak — aks holda
# services.event_dedup ularni "bir xil, qayta yetkazilgan xabar" deb bir-biriga aralashtirib yuboradi.
_msg_id_counter = itertools.count(1)


class FakeClient:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to=None):
        self.sent.append((chat_id, text))
        return SimpleNamespace(id=len(self.sent) + 1000)

    def action(self, chat, kind):
        class _Ctx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *a):
                return False
        return _Ctx()

    def is_connected(self):
        return True


def make_event(sender_id, chat_id, text, *, private=True, bot=False, mentioned=False, channel=False, msg_id=None):
    if msg_id is None:
        msg_id = next(_msg_id_counter)
    sender = SimpleNamespace(id=sender_id, bot=bot)

    async def get_sender():
        return sender

    message = SimpleNamespace(photo=None, voice=None, document=None, file=None)
    return SimpleNamespace(
        chat_id=chat_id, raw_text=text, is_private=private, is_group=not private and not channel,
        is_channel=channel, mentioned=mentioned, id=msg_id, message=message, get_sender=get_sender,
    )


class TestClientAgentHandler(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from services.event_dedup import reset as reset_event_dedup
        reset_event_dedup()  # global holat testlar orasida sizib chiqmasligi uchun
        memory_service.upsert_subscription(user_id=OWNER, days=30, business_name="Test Mebel", full_name="Akmal")
        # upsert_subscription group_id'ga tegmaydi — oldingi testda ulangan guruh shu yerga
        # "sizib o'tmasligi" uchun har bir test boshida aniq tozalab qo'yamiz.
        memory_service.link_user_group(OWNER, 0)
        self.mgr = ClientSessionManager()
        self.client = FakeClient()
        self.mgr._clients[OWNER] = self.client
        self.mgr._me[OWNER] = {"id": AGENT_ACCOUNT, "username": "akmal", "name": "Akmal"}
        self.replies_tenants = []
        self.owner_commands = []

        from services import ai_service as ai_mod

        async def fake_generate_reply(**kwargs):
            self.replies_tenants.append(get_tenant_id())
            return "Salom! Qanday yordam bera olaman?"

        self._orig_gen = ai_mod.ai_service.generate_reply
        ai_mod.ai_service.generate_reply = fake_generate_reply

        # Onboarding yakunida ishlatiladigan xom Groq pool'ni bo'shatib qo'yamiz — shu bilan
        # _finish_onboarding tarmoqqa chiqmasdan, tozalanmagan xom matnni saqlaydi (deterministik test).
        self._orig_frontline = ai_mod.ai_service._frontline_clients
        self._orig_groq = ai_mod.ai_service._groq_clients
        ai_mod.ai_service._frontline_clients = []
        ai_mod.ai_service._groq_clients = []

        async def fake_run_owner_command(user_id, command):
            self.owner_commands.append(command)
            return "bajarildi"

        self.mgr.run_owner_command = fake_run_owner_command

        from services.tenant_context import tenant_scope
        with tenant_scope(OWNER):
            memory_service.set_setting("debounce_seconds", "0")
            memory_service.set_setting("auto_reply_enabled", "true")
            memory_service.set_setting("group_reply_mode", "mention")

    async def asyncTearDown(self):
        from services import ai_service as ai_mod
        ai_mod.ai_service.generate_reply = self._orig_gen
        ai_mod.ai_service._frontline_clients = self._orig_frontline
        ai_mod.ai_service._groq_clients = self._orig_groq

    async def _incoming(self, event):
        from services.tenant_context import tenant_scope
        with tenant_scope(OWNER):
            await self.mgr._handle_incoming(OWNER, self.client, event)
        await asyncio.sleep(0.4)

    async def _outgoing(self, event):
        from services.tenant_context import tenant_scope
        with tenant_scope(OWNER):
            await self.mgr._handle_outgoing(OWNER, self.client, event)
        await asyncio.sleep(0.4)

    async def test_stranger_gets_reply_in_tenant_scope(self):
        await self._incoming(make_event(STRANGER, STRANGER, "Divan narxi qancha?"))
        self.assertEqual(self.replies_tenants, [OWNER])
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(self.owner_commands, [])

    async def test_stranger_cannot_issue_agent_commands(self):
        await self._incoming(make_event(STRANGER, STRANGER, "ai hamma kontaktlarga xabar yubor"))
        self.assertEqual(self.owner_commands, [])  # buyruq sifatida bajarilmadi
        self.assertEqual(len(self.replies_tenants), 1)  # oddiy suhbat sifatida javob oldi

    async def test_owner_saved_messages_command(self):
        await self._outgoing(make_event(AGENT_ACCOUNT, AGENT_ACCOUNT, "ai Alisherga salom yoz"))
        self.assertEqual(self.owner_commands, ["Alisherga salom yoz"])
        self.assertTrue(self.client.sent and self.client.sent[-1][1].startswith("🤖"))

    async def test_owner_notes_in_saved_messages_ignored(self):
        await self._outgoing(make_event(AGENT_ACCOUNT, AGENT_ACCOUNT, "xarid ro'yxati: non, sut"))
        self.assertEqual(self.owner_commands, [])
        self.assertEqual(self.client.sent, [])

    async def test_owner_takeover_pauses_ai(self):
        await self._outgoing(make_event(AGENT_ACCOUNT, STRANGER, "Assalomu alaykum, men o'zim javob beraman"))
        await self._incoming(make_event(STRANGER, STRANGER, "Yaxshi, kutaman"))
        self.assertEqual(self.replies_tenants, [])

    async def test_bots_service_and_channels_ignored(self):
        await self._incoming(make_event(777000, 777000, "Login code: 12345"))
        await self._incoming(make_event(123, 123, "bot xabari", bot=True))
        await self._incoming(make_event(STRANGER, -100500, "kanal posti", private=False, channel=True))
        self.assertEqual(self.replies_tenants, [])

    async def test_group_reply_only_when_mentioned(self):
        await self._incoming(make_event(STRANGER, -100600, "umumiy gap", private=False))
        self.assertEqual(self.replies_tenants, [])
        await self._incoming(make_event(STRANGER, -100600, "@akmal narx?", private=False, mentioned=True))
        self.assertEqual(self.replies_tenants, [OWNER])

    async def test_owner_group_bypasses_mention_gate(self):
        """
        Mijozning O'Z (Mini App'da biriktirgan) boshqaruv guruhi mentorning Vazifalar guruhi
        kabi ishlashi kerak: @mention shart emas — hatto begona odam yozsa ham javob beriladi
        (chunki bu guruh 100% agentga bag'ishlangan, oddiy mijozlar guruhi emas).
        """
        owner_group = -100700
        memory_service.link_user_group(OWNER, owner_group)
        await self._incoming(make_event(STRANGER, owner_group, "narx qancha?", private=False, mentioned=False))
        self.assertEqual(self.replies_tenants, [OWNER])

    async def test_owner_plain_message_via_incoming_path_gets_copilot_reply(self):
        """
        Agent ALOHIDA akkauntda ishlagan sozlamada (owner haqiqiy Telegram'da boshqa hisob —
        agentning o'zidan farqli), egasining boshqaruv guruhidagi 'ai' prefiksisiz xabari
        INCOMING hodisa sifatida keladi va baribir to'liq AI Co-Pilot buyrug'i sifatida
        bajarilishi kerak.
        """
        separate_agent_id = 999000111  # OWNER dan farqli, alohida agent akkaunti
        self.mgr._me[OWNER] = {"id": separate_agent_id, "username": "coddy_agent", "name": "Agent"}
        owner_group = -100705
        memory_service.link_user_group(OWNER, owner_group)
        await self._incoming(make_event(OWNER, owner_group, "bugungi ishlar haqida ayt", private=False))
        self.assertEqual(self.owner_commands, ["bugungi ishlar haqida ayt"])
        self.assertEqual(self.replies_tenants, [])

    async def test_owner_command_works_directly_in_owner_group(self):
        """
        Egasi o'z boshqaruv guruhida ham (Saved Messages'dagi kabi) 'ai ...' buyrug'ini bera olishi kerak.
        Bu testda agent egasining O'Z akkauntida ishlaydi (AGENT_ACCOUNT == OWNER), shuning uchun
        egasining xabari haqiqiy Telethon'da OUTGOING hodisa sifatida keladi.
        """
        owner_group = -100701
        memory_service.link_user_group(OWNER, owner_group)
        await self._outgoing(make_event(AGENT_ACCOUNT, owner_group, "ai Alisherga xabar yubor", private=False))
        self.assertEqual(self.owner_commands, ["Alisherga xabar yubor"])
        self.assertEqual(self.replies_tenants, [])  # buyruq sifatida bajarildi, oddiy AI javobi emas

    async def test_owner_plain_message_in_owner_group_gets_copilot_reply_no_prefix_needed(self):
        """
        Boshqaruv guruhi = Vazifalar guruhi tajribasi: egasi 'ai' prefiksisiz oddiy gapirsa
        ('Salom' kabi) ham to'liq AI Co-Pilot javobini olishi kerak — prefiks shart emas.
        Bundan tashqari, bu odatdagi mijozlar guruhidagi kabi AI'ni "jim tur" holatiga
        o'tkazmasligi kerak (chunki bu guruh mijozlar guruhi emas).
        """
        owner_group = -100704
        memory_service.link_user_group(OWNER, owner_group)
        await self._outgoing(make_event(AGENT_ACCOUNT, owner_group, "salom, tekshirib ko'ryapman", private=False))
        self.assertEqual(self.owner_commands, ["salom, tekshirib ko'ryapman"])
        self.assertTrue(self.client.sent and self.client.sent[-1][1] == "bajarildi")
        await self._incoming(make_event(STRANGER, owner_group, "narx qancha?", private=False, mentioned=False))
        self.assertEqual(self.replies_tenants, [OWNER])

    async def test_regular_group_unaffected_by_owner_group_linking(self):
        """Egasi boshqaruv guruhini ulagani boshqa (bog'liq bo'lmagan) guruhlarga ta'sir qilmasligi kerak."""
        owner_group = -100702
        other_group = -100703
        memory_service.link_user_group(OWNER, owner_group)
        await self._incoming(make_event(STRANGER, other_group, "umumiy gap", private=False, mentioned=False))
        self.assertEqual(self.replies_tenants, [])

    async def test_owner_can_link_group_via_command_single_account(self):
        """
        Bot orqali avtomatik bog'lash o'rniga, egasi o'zi agent akkaunti a'zo bo'lgan istalgan
        guruhda `ai ulash` deb yozib, o'sha guruhni xavfsiz va aniq ravishda biriktira oladi
        (bitta akkauntli sozlamada — xabar OUTGOING hodisa sifatida keladi). Ulangandan so'ng
        tanishuv savolnomasi (1-savol) avtomatik boshlanadi.
        """
        new_group = -100800
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "ai ulash", private=False))
        sub = memory_service.get_subscription(OWNER)
        self.assertEqual(sub["group_id"], new_group)
        sent_texts = [t for _, t in self.client.sent]
        self.assertTrue(any("boshqaruv guruhingiz" in t for t in sent_texts))
        self.assertTrue(any("1️⃣" in t for t in sent_texts))  # tanishuv savolnomasining 1-savoli

        # Tanishuv hali tugamagan bo'lsa ham, BEGONA odam yozgan xabar oddiy AI javobi olishi kerak
        # (onboarding javobi sifatida qabul qilinmaydi — faqat egasining javoblari shunday hisoblanadi)
        await self._incoming(make_event(STRANGER, new_group, "narx qancha?", private=False, mentioned=False))
        self.assertEqual(self.replies_tenants, [OWNER])

    async def test_onboarding_questionnaire_completes_and_saves_business_info(self):
        """Ulangandan keyingi barcha savollarga ketma-ket javob berilsa, biznes ma'lumotlari saqlanadi."""
        from services import client_session_manager as csm_mod
        new_group = -100810
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "ai ulash", private=False))
        for _, question in csm_mod.ONBOARDING_QUESTIONS:
            await self._outgoing(make_event(AGENT_ACCOUNT, new_group, f"javob: {question[:10]}", private=False))
        sub = memory_service.get_subscription(OWNER)
        self.assertIn("javob:", sub["system_prompt"])  # fake AI mock ishlatilmagani uchun xom matn qoladi
        # Savolnoma tugagach, holat tozalanib, oddiy suhbat rejimiga qaytishi kerak
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "yana bir gap", private=False))
        self.assertEqual(self.owner_commands[-1], "yana bir gap")

    async def test_onboarding_derives_topics_and_sets_scope_boundary(self):
        """
        Savolnomadagi 'mahsulot/xizmatlar' javobidan mavzular ro'yxati chiqarilib, mijozning
        shaxsiy `curriculum_topics`iga saqlanishi, va shu asosda AI system promptida chegara
        (boundary) qoidasi paydo bo'lishi kerak — begona so'rovlarni rad etishi uchun.
        """
        from services import client_session_manager as csm_mod
        from services.memory_service import memory_service as ms
        from services.tenant_context import tenant_scope

        new_group = -100840
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "ai ulash", private=False))
        for key, question in csm_mod.ONBOARDING_QUESTIONS:
            if key == "products":
                answer = "Divan, kreslo va stol-stul ishlab chiqaramiz, narxlari 500 ming so'mdan boshlanadi"
            elif key == "profession":
                answer = "Mebel savdosi"
            else:
                answer = f"javob: {question[:10]}"
            await self._outgoing(make_event(AGENT_ACCOUNT, new_group, answer, private=False))

        with tenant_scope(OWNER):
            topics = ms.get_curriculum_topics()
        self.assertTrue(topics, "mavzular ro'yxati bo'sh bo'lmasligi kerak")
        self.assertTrue(any("mebel" in t.lower() for t in topics) or any("divan" in t.lower() for t in topics))

        # AI system prompti shu mavzular asosida chegara qoidasini o'z ichiga olishi kerak
        from services.ai_service import ai_service
        with tenant_scope(OWNER):
            prompt = ai_service._build_system_prompt(False, effective_prompt="salom", chat_id=STRANGER, user_id=STRANGER)
        self.assertIn("CHEGARALARI", prompt)

    async def test_relinking_same_group_says_already_linked_and_skips_onboarding(self):
        """`ai ulash` bir marta qilinsa yetarli — qayta qilinsa, qayta ulanmaydi va savolnoma qayta boshlanmaydi."""
        new_group = -100820
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "ai ulash", private=False))
        sent_before = len(self.client.sent)
        await self._outgoing(make_event(AGENT_ACCOUNT, new_group, "ai ulash", private=False))
        self.assertEqual(len(self.client.sent), sent_before + 1)
        self.assertIn("allaqachon", self.client.sent[-1][1])

    async def test_random_group_membership_does_not_auto_link(self):
        """Agent a'zo bo'lgan tasodifiy guruhlar, egasi buyruq bermaguncha, ULANMASLIGI kerak."""
        random_group = -100801
        await self._incoming(make_event(STRANGER, random_group, "salom hammaga", private=False, mentioned=False))
        sub = memory_service.get_subscription(OWNER)
        self.assertNotEqual(sub.get("group_id"), random_group)
        self.assertEqual(self.replies_tenants, [])

    async def test_auto_reply_off_is_respected(self):
        from services.tenant_context import tenant_scope
        with tenant_scope(OWNER):
            memory_service.set_setting("auto_reply_enabled", "false")
        await self._incoming(make_event(STRANGER, STRANGER, "salom"))
        self.assertEqual(self.replies_tenants, [])

    async def test_expired_subscription_stops_replies(self):
        with memory_service._get_core_connection() as conn:
            conn.execute("UPDATE user_subscriptions SET expires_at = '2000-01-01 00:00:00' WHERE user_id = ?", (OWNER,))
            conn.commit()
        await self._incoming(make_event(STRANGER, STRANGER, "salom"))
        self.assertEqual(self.replies_tenants, [])

    async def test_stranger_recorded_as_lead_in_own_tenant(self):
        await self._incoming(make_event(STRANGER, STRANGER, "Divan bormi?"))
        from services.tenant_context import tenant_scope
        with tenant_scope(OWNER):
            leads = memory_service.get_leads()
        self.assertTrue(any(l["user_id"] == STRANGER and "Divan" in l["last_message"] for l in leads))
        self.assertFalse(any(l["user_id"] == STRANGER for l in memory_service.get_leads()))  # mentor bazasida yo'q

    async def test_unsure_answer_escalates_to_owner(self):
        from services import ai_service as ai_mod
        import services.notify as notify_mod
        sent = []

        async def unsure_reply(**kwargs):
            return "Buni aniqlab, sizga xabar beraman."

        async def fake_notify(user_id, text):
            sent.append((user_id, text))
            return True

        ai_mod.ai_service.generate_reply = unsure_reply
        orig = notify_mod.notify_user
        notify_mod.notify_user = fake_notify
        try:
            await self._incoming(make_event(STRANGER, STRANGER, "Ertaga yetkazib berasizmi?"))
        finally:
            notify_mod.notify_user = orig
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], OWNER)
        self.assertIn("Ertaga yetkazib", sent[0][1])

    async def test_unsure_answer_escalates_into_linked_group_not_only_dm(self):
        """
        Agar mijozning boshqaruv guruhi ulangan bo'lsa, "aniqlab xabar beraman" javobi
        FAQAT shaxsiy DM ga emas, balki O'SHA GURUHGA ham (asosiy kanal sifatida) yozilishi kerak.
        """
        from services import ai_service as ai_mod
        import services.notify as notify_mod

        owner_group = -100830
        memory_service.link_user_group(OWNER, owner_group)
        dm_sent = []

        async def unsure_reply(**kwargs):
            return "Buni aniqlashtirib, sizga xabar beraman."

        async def fake_notify(user_id, text):
            dm_sent.append((user_id, text))
            return True

        ai_mod.ai_service.generate_reply = unsure_reply
        orig = notify_mod.notify_user
        notify_mod.notify_user = fake_notify
        try:
            await self._incoming(make_event(STRANGER, STRANGER, "Ertaga yetkazib berasizmi?"))
        finally:
            notify_mod.notify_user = orig

        group_msgs = [t for cid, t in self.client.sent if cid == owner_group]
        self.assertTrue(group_msgs and "Mijoz savoliga aniq javob kerak" in group_msgs[-1])
        self.assertEqual(dm_sent, [])  # guruh ulangani uchun zaxira DM shart emas


if __name__ == "__main__":
    unittest.main()
