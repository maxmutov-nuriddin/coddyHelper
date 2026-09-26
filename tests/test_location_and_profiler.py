"""
- Lokatsiya so'rovini tushunish: "Barcha ... ber" ro'yxat so'ramoqda (bitta nomga aylanmasin),
  imlo xatoli/qo'shimcha so'zli so'rovlar ("Ish ni ... ber") saqlangan nomga to'g'ri moslanishi kerak.
- Profil razvedkasi: AI da'vo qilgan ishonch foizi haqiqiy signal kuchidan oshib ketmasligi kerak
  (signal yo'q bo'lsa past ishonch bilan "Aniq emas", signal kuchli bo'lsa yuqori ishonch saqlanadi).
"""

import tests._isolated_env  # noqa: F401

import unittest

from services.location_memory_service import ALL_LOCATIONS_SENTINEL, extract_location_query
from services.memory_service import memory_service
from services.profile_intelligence_service import profile_intelligence_service


class TestLocationQueryUnderstanding(unittest.TestCase):
    def test_all_locations_request_is_not_treated_as_a_name(self):
        for text in (
            "Barcha joylashuvlar lokatsiyasini ber",
            "hammasini ko'rsat lokatsiya",
            "barchasini yubor manzil",
        ):
            self.assertEqual(extract_location_query(text), ALL_LOCATIONS_SENTINEL, text)

    def test_stray_particle_and_typo_stripped_from_query(self):
        self.assertEqual(extract_location_query("Ish ni lokatsiyaisni ber"), "ish")
        self.assertEqual(extract_location_query("ishxona lokatsiyasini tashla"), "ishxona")
        self.assertEqual(extract_location_query("uy manzilini ber"), "uy")

    def test_unrelated_requests_still_ignored(self):
        self.assertIsNone(extract_location_query("ustozning raqamini ber"))
        self.assertIsNone(extract_location_query("o'quvchi qayerda xato qilgan?"))


class TestLocationFuzzyMatch(unittest.TestCase):
    def setUp(self):
        memory_service.add_saved_location(name="Ish", lat=41.123456, long=69.456789, address="")
        memory_service.add_saved_location(name="Uy", lat=41.111111, long=69.222222, address="")

    def test_exact_and_typo_and_extra_word_match(self):
        self.assertEqual(memory_service.get_saved_location("ish")["name"], "Ish")
        self.assertEqual(memory_service.get_saved_location("ish ni")["name"], "Ish")
        self.assertEqual(memory_service.get_saved_location("ishh")["name"], "Ish")
        self.assertEqual(memory_service.get_saved_location("uyi")["name"], "Uy")

    def test_no_match_for_unrelated_query(self):
        self.assertIsNone(memory_service.get_saved_location("mutlaqo_bogliqemas_soz"))


class TestProfilerConfidenceGrounding(unittest.TestCase):
    def test_overconfident_ai_claim_is_clamped_down_without_signal(self):
        ai_claim = {
            "role": "Ota-ona", "role_confidence": 95,
            "age_range": "35-45", "age_confidence": 90,
            "profession": "ishbilarmon", "communication_style": "rasmiy",
            "summary": "AI xulosasi", "overall_confidence": 92,
        }
        profile = {
            "own_msg_count": 0,
            "role_clues": "Ochiq rol belgisi topilmadi",
            "age_clues": "Ishonchli yosh belgisi topilmadi",
        }
        text = profile_intelligence_service._render_dossier_analysis(ai_claim, profile)
        self.assertIn("Aniq emas", text)
        self.assertNotIn("95%", text)
        self.assertNotIn("90%", text)
        self.assertNotIn("92%", text)

    def test_strong_signal_keeps_high_confidence(self):
        ai_claim = {
            "role": "Ota-ona", "role_confidence": 95,
            "age_range": "35-45", "age_confidence": 85,
            "profession": "ishbilarmon", "communication_style": "rasmiy",
            "summary": "AI xulosasi", "overall_confidence": 92,
        }
        profile = {
            "own_msg_count": 15,
            "role_clues": "KUCHLI: Ota-onalar guruhida a'zo; KUCHLI: O'z farzandi haqida gapirgan (Ota-ona)",
            "age_clues": "KUCHLI: O'zi yoshini aytgan — 38 yosh",
        }
        text = profile_intelligence_service._render_dossier_analysis(ai_claim, profile)
        self.assertIn("Ota-ona", text)
        self.assertIn("🟢", text)

    def test_signal_ceiling_levels(self):
        self.assertEqual(profile_intelligence_service._signal_ceiling(""), (25, False))
        self.assertEqual(profile_intelligence_service._signal_ceiling("Ochiq rol belgisi topilmadi"), (25, False))
        ceiling, has_signal = profile_intelligence_service._signal_ceiling("ZAIF: Username oxirida '05'")
        self.assertTrue(has_signal)
        self.assertEqual(ceiling, 40)
        ceiling, has_signal = profile_intelligence_service._signal_ceiling("KUCHLI: Ota-onalar guruhida a'zo")
        self.assertTrue(has_signal)
        self.assertGreaterEqual(ceiling, 80)


if __name__ == "__main__":
    unittest.main()
