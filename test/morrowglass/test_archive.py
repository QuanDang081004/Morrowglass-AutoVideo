import unittest

from app.morrowglass.archive import (
    ArchiveAsset,
    rank_archive_assets,
    relevance_score,
)


class ArchiveTests(unittest.TestCase):
    def test_ranking_prefers_scene_relevant_metadata(self):
        relevant = ArchiveAsset(
            title="Stone chamber entrance",
            image_url="https://example.com/a.jpg",
            source_page="https://example.com/a",
            license_name="Public domain",
            license_url="",
            artist="",
            description=(
                "historic stone chamber with brick entrance"
            ),
        )
        generic = ArchiveAsset(
            title="Mountain landscape",
            image_url="https://example.com/b.jpg",
            source_page="https://example.com/b",
            license_name="CC BY 4.0",
            license_url="",
            artist="",
            description="mountain valley and trees",
        )

        ranked = rank_archive_assets(
            [generic, relevant],
            query="stone chamber brick entrance",
            visual_description=(
                "a child places a brick at a stone chamber entrance"
            ),
        )
        self.assertIs(
            ranked[0],
            relevant,
        )
        self.assertGreater(
            relevance_score(
                relevant,
                "stone chamber entrance",
            ),
            relevance_score(
                generic,
                "stone chamber entrance",
            ),
        )


if __name__ == "__main__":
    unittest.main()
