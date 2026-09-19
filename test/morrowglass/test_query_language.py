import unittest

from app.morrowglass.query_language import (
    build_archive_query,
    likely_vietnamese,
)


SCRIPT = (
    "Ở La Mã cổ đại, cái chết không phải lúc nào cũng là dấu chấm "
    "hết cho câu chuyện của một con người. Một số gia đình giàu có "
    "lưu giữ những chiếc mặt nạ sáp có hình dáng giống tổ tiên đã "
    "qua đời. Trong các tang lễ quan trọng, diễn viên có thể đeo "
    "những chiếc mặt nạ này để đại diện cho nhiều thế hệ người đã "
    "khuất. Vì vậy, một đám tang có thể trở thành màn tái hiện sống "
    "động về lịch sử của cả một gia đình."
)


class QueryLanguageTests(unittest.TestCase):
    def test_detects_vietnamese(self):
        self.assertTrue(
            likely_vietnamese(
                SCRIPT
            )
        )

    def test_roman_wax_mask_scene_gets_english_archive_query(self):
        query = build_archive_query(
            (
                "Một số gia đình giàu có lưu giữ những chiếc mặt nạ "
                "sáp có hình dáng giống tổ tiên đã qua đời."
            ),
            script=SCRIPT,
        )
        self.assertIn(
            "Ancient Rome",
            query,
        )
        self.assertIn(
            "wax mask",
            query,
        )
        self.assertIn(
            "ancestors",
            query,
        )

    def test_funeral_scene_keeps_global_roman_context(self):
        query = build_archive_query(
            (
                "Vì vậy, một đám tang có thể trở thành màn tái hiện "
                "sống động về lịch sử của cả một gia đình."
            ),
            script=SCRIPT,
        )
        self.assertIn(
            "Ancient Rome",
            query,
        )
        self.assertIn(
            "funeral procession",
            query,
        )

    def test_english_query_is_not_rewritten(self):
        original = (
            "Ancient Rome wax ancestor masks"
        )
        self.assertEqual(
            build_archive_query(
                original,
                existing_query=original,
            ),
            original,
        )


if __name__ == "__main__":
    unittest.main()
