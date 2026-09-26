"""
- Bir xil (chat, matn, vaqt) uchun eslatma ikkinchi marta yaratilmasligi kerak (Telethon/Bot API
  ulanish qayta tiklanganda bir xil xabar ikki marta yetkazilishi natijasida "har renderda eslatma
  qo'shilib qolish" muammosining oldini oladi).
- services.event_dedup: bir xil (chat_id, msg_id) juftligi faqat bir marta ishlanadi, turli
  scope (masalan turli mijoz egalari) mustaqil hisoblanadi.
- config._clean_env_value: Render kabi panelga ".env" uslubida ("KEY=\"qiymat\"") joylashtirilgan
  tashqi tirnoqlarni avtomatik tozalaydi (aks holda MONGODB_URI/TELEGRAM_STRING_SESSION butunlay
  yaroqsiz bo'lib qoladi va ma'lumotlar restartlar orasida saqlanmaydi).
"""

import tests._isolated_env  # noqa: F401

import unittest

from config import _clean_env_value
from services.event_dedup import is_duplicate_event, reset as reset_event_dedup
from services.memory_service import memory_service

CHAT = 800000001


class TestReminderDedup(unittest.TestCase):
    def test_identical_reminder_is_not_duplicated(self):
        id1 = memory_service.add_reminder(chat_id=CHAT, reminder_text="Darsni eslatib qo'y", remind_at="2099-01-01 10:00:00", creator_id=CHAT)
        id2 = memory_service.add_reminder(chat_id=CHAT, reminder_text="Darsni eslatib qo'y", remind_at="2099-01-01 10:00:00", creator_id=CHAT)
        self.assertEqual(id1, id2)
        matches = [
            r for r in memory_service.get_active_reminders(50, creator_id=CHAT)
            if r["text"] == "Darsni eslatib qo'y" and r["remind_at"] == "2099-01-01 10:00:00"
        ]
        self.assertEqual(len(matches), 1)

    def test_different_time_creates_separate_reminder(self):
        id1 = memory_service.add_reminder(chat_id=CHAT, reminder_text="Boshqa vazifa", remind_at="2099-02-01 09:00:00", creator_id=CHAT)
        id2 = memory_service.add_reminder(chat_id=CHAT, reminder_text="Boshqa vazifa", remind_at="2099-02-02 09:00:00", creator_id=CHAT)
        self.assertNotEqual(id1, id2)


class TestEventDedup(unittest.TestCase):
    def setUp(self):
        reset_event_dedup()

    def test_same_message_id_treated_as_duplicate(self):
        self.assertFalse(is_duplicate_event(chat_id=123, msg_id=555))
        self.assertTrue(is_duplicate_event(chat_id=123, msg_id=555))

    def test_different_scopes_are_independent(self):
        self.assertFalse(is_duplicate_event(chat_id=123, msg_id=555, scope=1001))
        # Boshqa mijoz (owner) uchun bir xil (chat_id, msg_id) mustaqil hisoblanishi kerak
        self.assertFalse(is_duplicate_event(chat_id=123, msg_id=555, scope=1002))
        self.assertTrue(is_duplicate_event(chat_id=123, msg_id=555, scope=1001))

    def test_zero_msg_id_never_blocks(self):
        self.assertFalse(is_duplicate_event(chat_id=123, msg_id=0))
        self.assertFalse(is_duplicate_event(chat_id=123, msg_id=0))


class TestConfigQuoteStripping(unittest.TestCase):
    def test_strips_matching_double_quotes(self):
        self.assertEqual(
            _clean_env_value('"mongodb+srv://user:pass@host/?appName=Agent"'),
            "mongodb+srv://user:pass@host/?appName=Agent",
        )

    def test_strips_matching_single_quotes(self):
        self.assertEqual(_clean_env_value("'abc123'"), "abc123")

    def test_leaves_unquoted_value_untouched(self):
        self.assertEqual(_clean_env_value("plain-value"), "plain-value")

    def test_leaves_mismatched_quotes_untouched(self):
        self.assertEqual(_clean_env_value('"unclosed'), '"unclosed')

    def test_empty_and_none_safe(self):
        self.assertEqual(_clean_env_value(""), "")
        self.assertEqual(_clean_env_value(None), "")


if __name__ == "__main__":
    unittest.main()
