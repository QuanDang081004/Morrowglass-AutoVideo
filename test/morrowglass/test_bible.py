import json
import unittest

from app.morrowglass.bible import enrich_visual_bible
from app.morrowglass.models import VisualBible


class VisualBibleTests(unittest.TestCase):
    def test_fills_missing_fields(self):
        payload = {
            "period": "13th century",
            "location": "Japan",
            "characters": {
                "elder": "elderly parent in simple period clothing",
            },
            "historical_constraints": [
                "no modern technology",
            ],
        }
        result = enrich_visual_bible(
            "The story takes place in medieval Japan.",
            VisualBible(),
            llm_call=lambda _: json.dumps(payload),
        )
        self.assertEqual(result.period, "13th century")
        self.assertEqual(result.location, "Japan")
        self.assertIn("elder", result.characters)
        self.assertIn(
            "no modern technology",
            result.historical_constraints,
        )

    def test_user_fields_override_generated_fields(self):
        payload = {
            "period": "wrong generated period",
            "location": "wrong generated location",
            "characters": {
                "elder": "generated description",
            },
            "historical_constraints": ["generated constraint"],
        }
        result = enrich_visual_bible(
            "Narration.",
            VisualBible(
                period="user period",
                location="user location",
                characters={"elder": "user description"},
                historical_constraints=["user constraint"],
            ),
            llm_call=lambda _: json.dumps(payload),
        )
        self.assertEqual(result.period, "user period")
        self.assertEqual(result.location, "user location")
        self.assertEqual(
            result.characters["elder"],
            "user description",
        )
        self.assertEqual(
            result.historical_constraints[0],
            "user constraint",
        )

    def test_invalid_llm_response_keeps_original(self):
        original = VisualBible(period="known period")
        result = enrich_visual_bible(
            "Narration.",
            original,
            llm_call=lambda _: "not-json",
        )
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()
